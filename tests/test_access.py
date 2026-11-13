import base64
import hashlib
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.crypto import rsa
from app.db import SessionLocal
from app.models import AccessRequest, User
from app.services import keypairs
from app.timeutil import utcnow
from tests.conftest import create_user, login_client
from tests.test_files import content, upload
from tests.test_profile import NIK_PENANDA, sample

KB = 1024
ALL = {"profile": True, "id_card": True, "documents": True}


class Pair:
    """Dzaky (pemilik data: profil, 2 KTP, 2 dokumen, 1 video) dan Budi (peminta)."""

    def __init__(self):
        self.owner_user = create_user("buyer")
        self.req_user = create_user("buyer")
        self.owner = login_client(self.owner_user)
        self.budi = login_client(self.req_user)
        self.profile = sample(full_name="Dzaky A.", religion="Islam")
        self.owner.put("/profile", json={"data": self.profile})
        upload(self.owner, "id_card", "ktp-lama.png", content("png", 1 * KB))
        self.ktp_bytes = content("png", 3 * KB)
        self.ktp = upload(self.owner, "id_card", "ktp-baru.png", self.ktp_bytes).json()
        self.doc_bytes = content("pdf", 70 * KB)
        self.doc = upload(self.owner, "document", "slip-gaji.pdf", self.doc_bytes).json()
        self.doc2 = upload(self.owner, "document", "rekap.xlsx", content("xlsx", 2 * KB)).json()
        self.video = upload(self.owner, "video", "unboxing.mp4", content("mp4", 5 * KB)).json()

    def ask(self, scope=None, client=None, username=None):
        return (client or self.budi).post("/access-requests", json={
            "username": username or self.owner_user.username, "scope": scope or ALL,
        })

    def approved(self, scope=None, days=None):
        req_id = self.ask(scope).json()["id"]
        body = {"valid_days": days} if days else None
        r = self.owner.post(f"/access-requests/{req_id}/approve", json=body)
        assert r.status_code == 200, r.text
        return req_id, r.json()["access_code"]

    def redeemed(self, scope=None):
        req_id, code = self.approved(scope)
        assert self.budi.post(f"/access-requests/{req_id}/redeem", json={"access_code": code}).status_code == 200
        return req_id

    def close(self):
        self.owner.__exit__(None, None, None)
        self.budi.__exit__(None, None, None)


@pytest.fixture
def p():
    pair = Pair()
    yield pair
    pair.close()


def _row(req_id: int) -> AccessRequest:
    with SessionLocal() as db:
        row = db.get(AccessRequest, req_id)
        row.file_keys  # muat relasi sebelum sesi ditutup
        return row


def _share_key(p: Pair, code: str) -> bytes:
    with SessionLocal() as db:
        priv = keypairs.load_private_key(db, db.get(User, p.req_user.id))
    return rsa.decrypt_with(priv, base64.b64decode(code))


# --- Alur utama ---

def test_alur_lengkap(p):
    r = p.ask()
    assert r.status_code == 201
    req = r.json()
    assert req["status"] == "menunggu"
    assert req["scope"] == ALL
    assert req["owner"]["username"] == p.owner_user.username
    assert req["redeemed"] is False

    incoming = p.owner.get("/access-requests", params={"box": "incoming"}).json()["items"]
    assert [x["id"] for x in incoming] == [req["id"]]
    assert p.budi.get("/access-requests", params={"box": "outgoing"}).json()["items"][0]["id"] == req["id"]

    approved = p.owner.post(f"/access-requests/{req['id']}/approve").json()
    assert approved["status"] == "disetujui"
    assert approved["code_algorithm"] == "RSA-2048 OAEP-SHA256"
    assert approved["expires_at"].endswith("+07:00")
    with SessionLocal() as db:
        budi_pem = keypairs.get_public_pem(db, p.req_user.id)
    assert approved["requester_fingerprint"] == rsa.fingerprint(budi_pem)

    # Sebelum kode ditempel, data belum bisa dibuka.
    r = p.budi.get(f"/access-requests/{req['id']}/data")
    assert r.status_code == 400
    assert "kode akses" in r.json()["detail"]

    r = p.budi.post(f"/access-requests/{req['id']}/redeem", json={"access_code": approved["access_code"]})
    assert r.status_code == 200
    assert r.json()["redeemed"] is True

    data = p.budi.get(f"/access-requests/{req['id']}/data").json()
    assert data["profile"] == p.profile
    assert data["owner"]["username"] == p.owner_user.username
    names = [f["name"] for f in data["files"]]
    assert names == ["ktp-baru.png", "slip-gaji.pdf", "rekap.xlsx"]
    assert set(data["files"][0]) == {"id", "category", "name", "mime_type", "size_bytes"}


@pytest.mark.parametrize("alg", ["aes", "rc4", "des"])
def test_unduh_file_bersama_identik(p, alg):
    req_id = p.redeemed()
    for f, original in ((p.ktp, p.ktp_bytes), (p.doc, p.doc_bytes)):
        r = p.budi.get(f"/access-requests/{req_id}/files/{f['id']}/download", params={"alg": alg})
        assert r.status_code == 200
        assert r.content == original
        assert f'filename="{f["name"]}"' in r.headers["content-disposition"]


def test_kode_akses_tetap_berlaku_tanpa_tempel_ulang(p):
    req_id = p.redeemed()
    for _ in range(2):
        assert p.budi.get(f"/access-requests/{req_id}/data").status_code == 200


def test_jalur_unduh_biasa_tetap_404_untuk_peminta(p):
    p.redeemed()
    for f in (p.ktp, p.doc):
        assert p.budi.get(f"/files/{f['id']}/download").status_code == 404


def test_video_dan_ktp_lama_tidak_ikut(p):
    req_id = p.redeemed()
    data = p.budi.get(f"/access-requests/{req_id}/data").json()
    ids = {f["id"] for f in data["files"]}
    assert p.video["id"] not in ids
    r = p.budi.get(f"/access-requests/{req_id}/files/{p.video['id']}/download")
    assert r.status_code == 404


# --- Cakupan ---

def test_hanya_profil(p):
    req_id = p.redeemed({"profile": True, "id_card": False, "documents": False})
    data = p.budi.get(f"/access-requests/{req_id}/data").json()
    assert data["profile"] == p.profile
    assert data["files"] == []
    r = p.budi.get(f"/access-requests/{req_id}/files/{p.doc['id']}/download")
    assert r.status_code == 404


def test_hanya_dokumen(p):
    req_id = p.redeemed({"profile": False, "id_card": False, "documents": True})
    data = p.budi.get(f"/access-requests/{req_id}/data").json()
    assert data["profile"] is None
    assert {f["category"] for f in data["files"]} == {"document"}


# --- Kode akses (enkripsi asimetris) ---

def test_kode_akses_adalah_rsa_untuk_peminta(p):
    req_id, code = p.approved()
    blob = base64.b64decode(code)
    assert len(blob) == 256  # RSA-2048
    share_key = _share_key(p, code)
    assert len(share_key) == 32
    assert share_key not in blob
    assert hashlib.sha256(share_key).digest() == _row(req_id).key_sha256
    # Private key pemilik tidak bisa membuka kode untuk Budi.
    with SessionLocal() as db:
        owner_priv = keypairs.load_private_key(db, db.get(User, p.owner_user.id))
    with pytest.raises(ValueError):
        rsa.decrypt_with(owner_priv, blob)


@pytest.mark.parametrize("bad", ["bukan-base64!!", base64.b64encode(b"x" * 256).decode(), "   "])
def test_kode_akses_salah_400(p, bad):
    req_id, _ = p.approved()
    r = p.budi.post(f"/access-requests/{req_id}/redeem", json={"access_code": bad})
    assert r.status_code == 400
    assert _row(req_id).req_wrapped is None


def test_kode_akses_diubah_400(p):
    req_id, code = p.approved()
    blob = bytearray(base64.b64decode(code))
    blob[10] ^= 1
    r = p.budi.post(f"/access-requests/{req_id}/redeem", json={"access_code": base64.b64encode(bytes(blob)).decode()})
    assert r.status_code == 400


def test_kode_permintaan_lain_tidak_bisa_dipakai(p):
    first, code_first = p.approved({"profile": True, "id_card": False, "documents": False})
    p.owner.post(f"/access-requests/{first}/revoke")
    second, _ = p.approved()
    r = p.budi.post(f"/access-requests/{second}/redeem", json={"access_code": code_first})
    assert r.status_code == 400


def test_kode_dengan_spasi_dan_baris_baru_tetap_diterima(p):
    req_id, code = p.approved()
    messy = "\n".join(code[i:i + 60] for i in range(0, len(code), 60)) + "  \n"
    assert p.budi.post(f"/access-requests/{req_id}/redeem", json={"access_code": messy}).status_code == 200


def test_pemilik_bisa_lihat_kode_lagi(p):
    req_id, code = p.approved()
    r = p.owner.get(f"/access-requests/{req_id}/code")
    assert r.status_code == 200
    assert r.json()["access_code"] == code
    assert p.budi.get(f"/access-requests/{req_id}/code").status_code == 404


# --- Penyimpanan aman ---

def test_kunci_berbagi_tidak_tersimpan_polos(p):
    req_id = p.redeemed()
    row = _row(req_id)
    code = p.owner.get(f"/access-requests/{req_id}/code").json()["access_code"]
    share_key = _share_key(p, code)
    raw = Path(get_settings().database_url.removeprefix("sqlite:///")).read_bytes()
    assert share_key not in raw
    assert row.owner_wrapped and row.req_wrapped and share_key not in (row.owner_wrapped + row.req_wrapped)
    assert NIK_PENANDA.encode() not in row.snapshot_ciphertext
    assert len(row.file_keys) == 3 * 3  # KTP + 2 dokumen, masing-masing 3 algoritma


# --- Kedaluwarsa, cabut, tolak ---

def _expire(req_id: int) -> None:
    with SessionLocal() as db:
        db.get(AccessRequest, req_id).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()


def test_kedaluwarsa_menghapus_kunci(p):
    req_id = p.redeemed()
    _expire(req_id)
    item = p.budi.get(f"/access-requests/{req_id}").json()
    assert item["status"] == "kedaluwarsa"
    r = p.budi.get(f"/access-requests/{req_id}/data")
    assert r.status_code == 400
    assert r.json()["detail"] == "Akses sudah kedaluwarsa"
    assert p.budi.get(f"/access-requests/{req_id}/files/{p.doc['id']}/download").status_code == 400
    row = _row(req_id)
    assert row.req_wrapped is None and row.owner_wrapped is None and row.snapshot_ciphertext is None
    assert row.file_keys == []
    assert p.owner.get(f"/access-requests/{req_id}/code").status_code == 400


def test_kedaluwarsa_sebelum_ditempel(p):
    req_id, code = p.approved()
    _expire(req_id)
    r = p.budi.post(f"/access-requests/{req_id}/redeem", json={"access_code": code})
    assert r.status_code == 400
    assert r.json()["detail"] == "Akses sudah kedaluwarsa"


def test_masa_berlaku_bisa_dipilih(p):
    req_id, _ = p.approved(days=1)
    row = _row(req_id)
    remaining = row.expires_at.replace(tzinfo=None) - row.decided_at.replace(tzinfo=None)
    assert remaining == timedelta(days=1)


@pytest.mark.parametrize("days", [0, 31])
def test_masa_berlaku_di_luar_batas_400(p, days):
    req_id = p.ask().json()["id"]
    assert p.owner.post(f"/access-requests/{req_id}/approve", json={"valid_days": days}).status_code == 400


def test_cabut_akses(p):
    req_id = p.redeemed()
    r = p.owner.post(f"/access-requests/{req_id}/revoke")
    assert r.status_code == 200
    assert r.json()["status"] == "dicabut"
    assert p.budi.get(f"/access-requests/{req_id}/data").json()["detail"] == "Akses sudah dicabut pemilik"
    assert _row(req_id).file_keys == []


def test_tolak(p):
    req_id = p.ask().json()["id"]
    assert p.owner.post(f"/access-requests/{req_id}/reject").json()["status"] == "ditolak"
    assert p.owner.post(f"/access-requests/{req_id}/approve").status_code == 400
    assert p.budi.get(f"/access-requests/{req_id}/data").status_code == 400
    assert p.ask().status_code == 201  # boleh meminta lagi setelah ditolak


def test_file_dihapus_pemilik_tidak_bisa_diunduh(p):
    req_id = p.redeemed()
    p.owner.delete(f"/files/{p.doc['id']}")
    assert p.budi.get(f"/access-requests/{req_id}/files/{p.doc['id']}/download").status_code == 404


# --- Validasi dan hak akses ---

def test_validasi_permintaan(p):
    assert p.ask(scope={"profile": False, "id_card": False, "documents": False}).status_code == 400
    assert p.ask(username=p.req_user.username).status_code == 400
    assert p.ask(username="tidak_ada_orangnya").status_code == 404
    store = create_user("store", store_name="Toko Q")
    assert p.ask(username=store.username).status_code == 404
    assert p.ask().status_code == 201
    r = p.ask()
    assert r.status_code == 400
    assert "menunggu atau aktif" in r.json()["detail"]


def test_username_tidak_peka_huruf_besar(p):
    assert p.ask(username=p.owner_user.username.upper()).status_code == 201


def test_pihak_lain_404(p):
    req_id, code = p.approved()
    other = login_client(create_user("buyer"))
    try:
        for path in ("", "/data", "/code"):
            assert other.get(f"/access-requests/{req_id}{path}").status_code == 404
        assert other.post(f"/access-requests/{req_id}/redeem", json={"access_code": code}).status_code == 404
        assert other.post(f"/access-requests/{req_id}/revoke").status_code == 404
    finally:
        other.__exit__(None, None, None)


def test_peran_dalam_permintaan_dipisah(p):
    req_id = p.ask().json()["id"]
    assert p.budi.post(f"/access-requests/{req_id}/approve").status_code == 404
    assert p.budi.post(f"/access-requests/{req_id}/reject").status_code == 404
    assert p.owner.post(f"/access-requests/{req_id}/redeem", json={"access_code": "x"}).status_code == 404


def test_toko_403(store):
    assert store.get("/access-requests").status_code == 403
    assert store.post("/access-requests", json={"username": "a", "scope": ALL}).status_code == 403


def test_tanpa_login_401(client):
    assert client.get("/access-requests").status_code == 401
    assert client.get("/access-requests/1/data").status_code == 401
