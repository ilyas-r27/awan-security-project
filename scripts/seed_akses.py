"""Contoh demo Assignment 2: dua permintaan akses ke data `dzaky`.

    python scripts/seed.py --password demo12345        # akun dasar dulu
    python scripts/seed_akses.py --password demo12345

Membuat pembeli `budi` dan `citra`, lalu:
- budi  -> dzaky: DISETUJUI, berlaku 7 hari, kode akses dicetak (belum ditempel, untuk didemokan)
- citra -> dzaky: DISETUJUI 8 hari lalu dengan masa 7 hari, jadi sudah KEDALUWARSA

Kalau `dzaky` belum punya profil, foto KTP, atau dokumen, dibuatkan data contoh (bukan data asli)
lewat jalur enkripsi yang sama dengan upload biasa. Aman dijalankan berulang.
"""

import argparse
import secrets
import struct
import sys
import zlib
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app import models  # noqa: E402,F401
from app.crypto.keys import new_key_salt  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import AccessRequest, File, ProfileCiphertext, User  # noqa: E402
from app.schemas import ProfileData  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.services import access  # noqa: E402
from app.services.files import EncryptedUpload, save_upload  # noqa: E402
from app.services.profile import save_profile  # noqa: E402
from app.timeutil import utcnow  # noqa: E402

DEMO_PROFILE = {
    "full_name": "Dzaky Contoh", "nik": "3578000011112222", "birth_date": "2004-05-12",
    "gender": "Laki-laki", "nationality": "WNI", "marital_status": "Belum kawin",
    "address": "Jl. Contoh No. 12, Surabaya", "phone": "081200001111",
    "bank_account": "BCA 0000111122", "religion": None, "health_notes": None,
}
ALL_SCOPE = {"profile": True, "id_card": True, "documents": True}


def png_contoh(width: int = 320, height: int = 200) -> bytes:
    """PNG polos biru muda (pengganti foto KTP, bukan KTP asli)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    row = b"\x00" + bytes((169, 220, 249)) * width
    raw = zlib.compress(row * height)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def pdf_contoh(text: str) -> bytes:
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def upload_bytes(db, user: User, category: str, name: str, mime: str, data: bytes) -> None:
    boundary = "seedAwan" + secrets.token_hex(8)
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"category\"\r\n\r\n{category}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    up = EncryptedUpload(db, user, boundary.encode())
    try:
        up.feed(body)
        save_upload(db, user, up.finish())
    except BaseException:
        up.cleanup()
        db.rollback()
        raise


def get_or_create_buyer(db, username: str, password: str | None) -> User:
    user = db.scalar(select(User).where(func.lower(User.username) == username))
    if user:
        print(f"  {username:<8} sudah ada")
        return user
    pw = password or secrets.token_urlsafe(9)
    user = User(username=username, password_hash=hash_password(pw), key_salt=new_key_salt(), role="buyer")
    db.add(user)
    db.commit()
    print(f"+ {username:<8} pembeli        password: {'(dari --password)' if password else pw}")
    return user


def prepare_owner_data(db, dzaky: User) -> None:
    if not db.scalar(select(ProfileCiphertext.id).where(ProfileCiphertext.user_id == dzaky.id).limit(1)):
        save_profile(db, dzaky, ProfileData(**DEMO_PROFILE))
        print("+ profil contoh untuk dzaky")
    has = {c for (c,) in db.execute(select(File.category).where(File.user_id == dzaky.id))}
    if "id_card" not in has:
        upload_bytes(db, dzaky, "id_card", "ktp-contoh.png", "image/png", png_contoh())
        print("+ foto KTP contoh untuk dzaky (gambar polos, bukan KTP asli)")
    if "document" not in has:
        upload_bytes(db, dzaky, "document", "slip-gaji-contoh.pdf", "application/pdf",
                     pdf_contoh("Slip gaji CONTOH - data dummy untuk demo"))
        print("+ dokumen contoh untuk dzaky")


def latest_request(db, requester: User, owner: User) -> AccessRequest | None:
    return db.scalar(select(AccessRequest).where(
        AccessRequest.requester_id == requester.id, AccessRequest.owner_id == owner.id,
    ).order_by(AccessRequest.id.desc()).limit(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--password", help="Password untuk akun budi/citra yang baru (minimal 8 karakter)")
    args = parser.parse_args()
    if args.password is not None and len(args.password) < 8:
        parser.error("password minimal 8 karakter")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        dzaky = db.scalar(select(User).where(User.username == "dzaky"))
        if dzaky is None:
            print("Akun dzaky belum ada. Jalankan dulu: python scripts/seed.py")
            return 1
        budi = get_or_create_buyer(db, "budi", args.password)
        citra = get_or_create_buyer(db, "citra", args.password)
        prepare_owner_data(db, dzaky)

        # Contoh 1: aktif.
        req = latest_request(db, budi, dzaky)
        if req is None or access.display_status(req) not in ("disetujui",):
            req = access.create_request(db, budi, "dzaky", ALL_SCOPE)
            access.approve(db, dzaky, req.id, 7)
            print(f"+ permintaan #{req.id} budi -> dzaky DISETUJUI (7 hari)")
        else:
            print(f"  permintaan #{req.id} budi -> dzaky sudah aktif")
        code = access.get_code(db, dzaky, req.id)

        # Contoh 2: kedaluwarsa (disetujui 8 hari lalu, berlaku 7 hari).
        old = latest_request(db, citra, dzaky)
        if old is None or access.display_status(old) != "kedaluwarsa":
            old = access.create_request(db, citra, "dzaky", ALL_SCOPE)
            access.approve(db, dzaky, old.id, 7)
            past = utcnow() - timedelta(days=8)
            old.created_at, old.decided_at, old.expires_at = past, past, past + timedelta(days=7)
            db.commit()
            print(f"+ permintaan #{old.id} citra -> dzaky KEDALUWARSA (berakhir 1 hari lalu)")
        else:
            print(f"  permintaan #{old.id} citra -> dzaky sudah kedaluwarsa")

    print()
    print(f"Kode akses untuk budi (permintaan #{req.id}), kirim seolah lewat WA lalu tempel di akun budi:")
    print(code["access_code"])
    print(f"Fingerprint public key budi: {code['requester_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
