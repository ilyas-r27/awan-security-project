"""Assignment 2: pembeli meminta melihat data pribadi pembeli lain.

Saat pemilik menyetujui, server membuat kunci berbagi acak (AES-256) atas nama pemilik. Data dalam
cakupan (snapshot profil + daftar file) dienkripsi dengan kunci itu, dan kunci file dibungkus ulang
dengan kunci itu. Kunci berbagi dienkripsi RSA-OAEP dengan public key peminta menjadi kode akses yang
dikirim pemilik lewat WA/email. Peminta baru bisa membuka data setelah menempelkan kode akses.
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from Crypto.Random import get_random_bytes
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto import rsa
from app.crypto.keys import Algorithm, derive_user_keys
from app.crypto.vault import decrypt_bytes, encrypt_bytes, unwrap_key, wrap_key
from app.models import AccessFileKey, AccessRequest, File, FileCiphertext, FileKey, User
from app.services import keypairs
from app.services.files import Download, _abs, _decrypt_stream, file_name
from app.services.profile import latest_id_card_id, read_profile
from app.timeutil import to_wib_iso, utcnow

log = logging.getLogger("awan.access")

SHARE_KEY_BYTES = 32
CODE_ALGORITHM = "RSA-2048 OAEP-SHA256"


class AccessError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _aes_key(user: User) -> bytes:
    return derive_user_keys(user.key_salt)["aes"]


def _aware(dt: datetime) -> datetime:
    """SQLite mengembalikan datetime tanpa zona; nilainya UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def display_status(req: AccessRequest) -> str:
    if req.status == "disetujui" and req.expires_at and _aware(req.expires_at) <= utcnow():
        return "kedaluwarsa"
    return req.status


def _purge_keys(req: AccessRequest) -> None:
    """Hapus semua bahan kunci: setelah ini data tidak bisa dibuka siapa pun lewat permintaan ini."""
    for col in ("key_sha256", "owner_nonce", "owner_wrapped", "owner_tag", "req_nonce", "req_wrapped",
                "req_tag", "access_code", "snapshot_iv", "snapshot_ciphertext"):
        setattr(req, col, None)
    req.file_keys.clear()


def _expire_if_needed(db: Session, req: AccessRequest) -> None:
    if display_status(req) == "kedaluwarsa" and req.key_sha256 is not None:
        _purge_keys(req)
        db.commit()
        log.info("akses kedaluwarsa, kunci dihapus request_id=%s", req.id)


def _user_ref(db: Session, user_id: int) -> dict:
    u = db.get(User, user_id)
    return {"id": u.id, "username": u.username}


def request_out(db: Session, req: AccessRequest) -> dict:
    return {
        "id": req.id,
        "requester": _user_ref(db, req.requester_id),
        "owner": _user_ref(db, req.owner_id),
        "scope": {"profile": req.scope_profile, "id_card": req.scope_id_card, "documents": req.scope_documents},
        "status": display_status(req),
        "created_at": to_wib_iso(req.created_at),
        "decided_at": to_wib_iso(req.decided_at),
        "expires_at": to_wib_iso(req.expires_at),
        "redeemed": req.redeemed_at is not None and req.req_wrapped is not None,
    }


# --- Peminta ---

def create_request(db: Session, requester: User, username: str, scope: dict) -> AccessRequest:
    if not any(scope.values()):
        raise AccessError(400, "Pilih minimal satu data yang diminta")
    owner = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if owner is None or owner.role != "buyer":
        raise AccessError(404, "Pembeli tidak ditemukan")
    if owner.id == requester.id:
        raise AccessError(400, "Tidak bisa meminta data sendiri")
    for req in db.scalars(select(AccessRequest).where(
        AccessRequest.requester_id == requester.id, AccessRequest.owner_id == owner.id,
        AccessRequest.status.in_(("menunggu", "disetujui")),
    )):
        if display_status(req) in ("menunggu", "disetujui"):
            raise AccessError(400, "Masih ada permintaan yang menunggu atau aktif ke pembeli ini")

    keypairs.ensure_keypair(db, requester)  # pemilik butuh public key peminta saat menyetujui
    req = AccessRequest(
        requester_id=requester.id, owner_id=owner.id, status="menunggu",
        scope_profile=scope["profile"], scope_id_card=scope["id_card"], scope_documents=scope["documents"],
    )
    db.add(req)
    db.commit()
    log.info("permintaan akses request_id=%s requester_id=%s owner_id=%s", req.id, requester.id, owner.id)
    return req


def list_requests(db: Session, user: User, box: str) -> list[dict]:
    column = AccessRequest.owner_id if box == "incoming" else AccessRequest.requester_id
    items = []
    for req in db.scalars(select(AccessRequest).where(column == user.id).order_by(AccessRequest.id.desc())):
        _expire_if_needed(db, req)
        items.append(request_out(db, req))
    return items


def _get(db: Session, request_id: int, user: User, role: str | None = None) -> AccessRequest:
    """role: 'owner', 'requester', atau None (salah satu). Bukan pihaknya -> 404."""
    req = db.get(AccessRequest, request_id)
    if req is None:
        raise AccessError(404, "Permintaan tidak ditemukan")
    ids = {"owner": (req.owner_id,), "requester": (req.requester_id,)}.get(role, (req.owner_id, req.requester_id))
    if user.id not in ids:
        raise AccessError(404, "Permintaan tidak ditemukan")
    _expire_if_needed(db, req)
    return req


def get_request(db: Session, request_id: int, user: User) -> dict:
    return request_out(db, _get(db, request_id, user))


def _require_active(req: AccessRequest) -> None:
    status = display_status(req)
    if status == "kedaluwarsa":
        raise AccessError(400, "Akses sudah kedaluwarsa")
    if status == "dicabut":
        raise AccessError(400, "Akses sudah dicabut pemilik")
    if status != "disetujui":
        raise AccessError(400, "Permintaan belum disetujui")


def redeem(db: Session, requester: User, request_id: int, access_code: str) -> dict:
    req = _get(db, request_id, requester, "requester")
    _require_active(req)
    try:
        blob = base64.b64decode("".join(access_code.split()), validate=True)
        share_key = rsa.decrypt_with(keypairs.load_private_key(db, requester), blob)
    except (binascii.Error, ValueError, TypeError):
        raise AccessError(400, "Kode akses tidak valid") from None
    if not hmac.compare_digest(hashlib.sha256(share_key).digest(), req.key_sha256):
        raise AccessError(400, "Kode akses tidak valid")
    req.req_nonce, req.req_wrapped, req.req_tag = wrap_key(_aes_key(requester), share_key)
    req.redeemed_at = utcnow()
    db.commit()
    log.info("kode akses dipakai request_id=%s", req.id)
    return request_out(db, req)


def _share_key_for_requester(db: Session, req: AccessRequest, requester: User) -> bytes:
    _require_active(req)
    if req.req_wrapped is None:
        raise AccessError(400, "Tempelkan kode akses dari pemilik terlebih dahulu")
    return unwrap_key(_aes_key(requester), req.req_nonce, req.req_wrapped, req.req_tag)


def _snapshot(req: AccessRequest, share_key: bytes) -> dict:
    return json.loads(decrypt_bytes("aes", share_key, req.snapshot_iv, req.snapshot_ciphertext))


def view_data(db: Session, requester: User, request_id: int) -> dict:
    req = _get(db, request_id, requester, "requester")
    snap = _snapshot(req, _share_key_for_requester(db, req, requester))
    log.info("data dibuka request_id=%s", req.id)
    return {
        "request_id": req.id,
        "owner": _user_ref(db, req.owner_id),
        "expires_at": to_wib_iso(req.expires_at),
        "profile": snap["profile"],
        "files": snap["files"],
    }


def open_shared_download(db: Session, requester: User, request_id: int, file_id: int, alg: Algorithm) -> Download:
    req = _get(db, request_id, requester, "requester")
    share_key = _share_key_for_requester(db, req, requester)
    afk = db.scalar(select(AccessFileKey).where(
        AccessFileKey.request_id == req.id, AccessFileKey.file_id == file_id, AccessFileKey.algorithm == alg,
    ))
    ct = db.scalar(select(FileCiphertext).where(FileCiphertext.file_id == file_id, FileCiphertext.algorithm == alg))
    f = db.get(File, file_id)
    if afk is None or ct is None or f is None:
        raise AccessError(404, "File tidak ditemukan")
    path = _abs(ct.storage_path)
    if not path.is_file():
        raise AccessError(404, "File tidak ditemukan")
    meta = next((x for x in _snapshot(req, share_key)["files"] if x["id"] == file_id), None)
    if meta is None:
        raise AccessError(404, "File tidak ditemukan")
    file_key = unwrap_key(share_key, afk.wrap_nonce, afk.wrapped_key, afk.wrap_tag)
    log.info("unduh file bersama request_id=%s file_id=%s alg=%s", req.id, file_id, alg)
    chunks = _decrypt_stream(path, alg, file_key, ct.iv, f.id, requester.id, f.size_bytes)
    return Download(meta["name"], f.mime_type, f.size_bytes, chunks)


# --- Pemilik ---

def _files_in_scope(db: Session, req: AccessRequest, owner: User) -> list[File]:
    files: list[File] = []
    if req.scope_id_card:
        ktp = latest_id_card_id(db, owner.id)
        if ktp:
            files.append(db.get(File, ktp))
    if req.scope_documents:
        files.extend(db.scalars(
            select(File).where(File.user_id == owner.id, File.category == "document").order_by(File.id)
        ))
    return files


def approve(db: Session, owner: User, request_id: int, valid_days: int) -> dict:
    req = _get(db, request_id, owner, "owner")
    if req.status != "menunggu":
        raise AccessError(400, "Permintaan ini sudah diproses")
    requester = db.get(User, req.requester_id)
    public_pem = keypairs.ensure_keypair(db, requester).public_pem

    share_key = get_random_bytes(SHARE_KEY_BYTES)
    owner_aes = _aes_key(owner)
    files = _files_in_scope(db, req, owner)
    for f in files:
        for fk in db.scalars(select(FileKey).where(FileKey.file_id == f.id, FileKey.user_id == owner.id)):
            file_key = unwrap_key(owner_aes, fk.wrap_nonce, fk.wrapped_key, fk.wrap_tag)
            nonce, wrapped, tag = wrap_key(share_key, file_key)
            req.file_keys.append(AccessFileKey(file_id=f.id, algorithm=fk.algorithm,
                                               wrap_nonce=nonce, wrapped_key=wrapped, wrap_tag=tag))
    snapshot = {
        "profile": read_profile(db, owner, "aes")["data"] if req.scope_profile else None,
        "files": [{"id": f.id, "category": f.category, "name": file_name(f, owner_aes),
                   "mime_type": f.mime_type, "size_bytes": f.size_bytes} for f in files],
    }
    req.snapshot_iv, req.snapshot_ciphertext = encrypt_bytes(
        "aes", share_key, json.dumps(snapshot, ensure_ascii=False).encode())
    req.owner_nonce, req.owner_wrapped, req.owner_tag = wrap_key(owner_aes, share_key)
    req.key_sha256 = hashlib.sha256(share_key).digest()
    req.access_code = rsa.encrypt_for(public_pem, share_key)

    now = utcnow()
    req.status, req.decided_at, req.expires_at = "disetujui", now, now + timedelta(days=valid_days)
    db.commit()
    log.info("akses disetujui request_id=%s files=%d hari=%d", req.id, len(files), valid_days)
    return {**request_out(db, req), **_code_out(req, public_pem)}


def _code_out(req: AccessRequest, requester_pem: str) -> dict:
    return {
        "access_code": base64.b64encode(req.access_code).decode(),
        "code_algorithm": CODE_ALGORITHM,
        "requester_fingerprint": rsa.fingerprint(requester_pem),
    }


def get_code(db: Session, owner: User, request_id: int) -> dict:
    req = _get(db, request_id, owner, "owner")
    _require_active(req)
    pem = keypairs.get_public_pem(db, req.requester_id)
    return {"request_id": req.id, "expires_at": to_wib_iso(req.expires_at), **_code_out(req, pem)}


def reject(db: Session, owner: User, request_id: int) -> dict:
    req = _get(db, request_id, owner, "owner")
    if req.status != "menunggu":
        raise AccessError(400, "Permintaan ini sudah diproses")
    req.status, req.decided_at = "ditolak", utcnow()
    db.commit()
    log.info("akses ditolak request_id=%s", req.id)
    return request_out(db, req)


def revoke(db: Session, owner: User, request_id: int) -> dict:
    req = _get(db, request_id, owner, "owner")
    if req.status != "disetujui":
        raise AccessError(400, "Hanya akses yang sudah disetujui yang bisa dicabut")
    _purge_keys(req)
    req.status = "dicabut"
    db.commit()
    log.info("akses dicabut request_id=%s", req.id)
    return request_out(db, req)
