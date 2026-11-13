from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crypto import rsa
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import KeypairOut, PublicKeyOut
from app.services import keypairs
from app.timeutil import to_wib_iso

router = APIRouter(prefix="/keys", tags=["keys"])


def _out(row) -> dict:
    if row is None:
        return {"has_keypair": False, "public_key_pem": None, "fingerprint": None, "created_at": None}
    return {"has_keypair": True, "public_key_pem": row.public_pem,
            "fingerprint": rsa.fingerprint(row.public_pem), "created_at": to_wib_iso(row.created_at)}


@router.get("/me", response_model=KeypairOut)
def my_keypair(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(keypairs.get_keypair_row(db, user.id))


@router.post("/generate", response_model=KeypairOut)
def generate_keypair(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Buat pasangan kunci kalau belum ada; kalau sudah ada, kembalikan yang lama (tidak menimpa)."""
    return _out(keypairs.ensure_keypair(db, user))


@router.get("/{user_id}/public", response_model=PublicKeyOut)
def public_key(user_id: int, _user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    pem = keypairs.get_public_pem(db, user_id) if target else None
    if pem is None:
        raise HTTPException(404, "Public key tidak ditemukan")
    return {"user_id": target.id, "username": target.username,
            "public_key_pem": pem, "fingerprint": rsa.fingerprint(pem)}
