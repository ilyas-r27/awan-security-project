"""Kelola pasangan kunci RSA user. Dipakai juga oleh fitur Assignment 2 (request data) dan 3 (tanda tangan PDF)."""

from Crypto.PublicKey.RSA import RsaKey
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crypto import rsa
from app.crypto.keys import derive_user_keys
from app.models import User, UserKeypair


def get_keypair_row(db: Session, user_id: int) -> UserKeypair | None:
    return db.scalar(select(UserKeypair).where(UserKeypair.user_id == user_id))


def ensure_keypair(db: Session, user: User) -> UserKeypair:
    """Buat pasangan kunci kalau user belum punya. Aman dipanggil berkali-kali."""
    row = get_keypair_row(db, user.id)
    if row is not None:
        return row
    key = rsa.generate_keypair()
    nonce, wrapped, tag = rsa.wrap_private(derive_user_keys(user.key_salt)["aes"], key)
    row = UserKeypair(user_id=user.id, public_pem=rsa.public_pem(key),
                      priv_nonce=nonce, priv_wrapped=wrapped, priv_tag=tag)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:  # request lain sudah membuatnya lebih dulu
        db.rollback()
        row = get_keypair_row(db, user.id)
    db.refresh(row)
    return row


def load_private_key(db: Session, user: User) -> RsaKey:
    """Private key user (membuat pasangan baru kalau belum ada). Jangan pernah dikirim ke client atau di-log."""
    row = ensure_keypair(db, user)
    return rsa.unwrap_private(derive_user_keys(user.key_salt)["aes"], row.priv_nonce, row.priv_wrapped, row.priv_tag)


def get_or_create_keypair(db: Session, user: User) -> tuple[str, RsaKey]:
    """(public_pem, private_key) milik user."""
    row = ensure_keypair(db, user)
    return row.public_pem, load_private_key(db, user)


def get_public_pem(db: Session, user_id: int) -> str | None:
    row = get_keypair_row(db, user_id)
    return row.public_pem if row else None
