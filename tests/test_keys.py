import pytest
from Crypto.Random import get_random_bytes
from sqlalchemy import func, select

from app.config import get_settings
from app.crypto import rsa
from app.db import SessionLocal
from app.models import User, UserKeypair
from app.services import keypairs
from tests.conftest import create_user


# ---------- modul crypto/rsa.py ----------

@pytest.fixture(scope="module")
def key():
    return rsa.generate_keypair()


def test_ukuran_kunci_2048(key):
    assert key.size_in_bits() == 2048


def test_kunci_simetris_roundtrip(key):
    for n in (8, 16, 32, rsa.OAEP_MAX_BYTES):
        data = get_random_bytes(n)
        assert rsa.decrypt_with(key, rsa.encrypt_for(rsa.public_pem(key), data)) == data


def test_oaep_acak_dan_bukan_plaintext(key):
    data = get_random_bytes(32)
    c1, c2 = rsa.encrypt_for(key, data), rsa.encrypt_for(key, data)
    assert c1 != c2 and data not in c1


def test_private_key_lain_gagal(key):
    ct = rsa.encrypt_for(key, b"rahasia")
    with pytest.raises(ValueError):
        rsa.decrypt_with(rsa.generate_keypair(), ct)


def test_data_terlalu_besar_ditolak(key):
    with pytest.raises(ValueError):
        rsa.encrypt_for(key, b"x" * (rsa.OAEP_MAX_BYTES + 1))


def test_load_public_menolak_private_key(key):
    with pytest.raises(ValueError):
        rsa.load_public(key.export_key("PEM"))


def test_wrap_private_roundtrip_dan_kek_salah(key):
    kek = get_random_bytes(32)
    n, w, t = rsa.wrap_private(kek, key)
    assert rsa.unwrap_private(kek, n, w, t) == key
    with pytest.raises(ValueError):
        rsa.unwrap_private(get_random_bytes(32), n, w, t)


# ---------- service + endpoint ----------

def test_belum_punya_kunci(buyer):
    r = buyer.get("/keys/me")
    assert r.status_code == 200
    assert r.json() == {"has_keypair": False, "algorithm": "RSA-2048", "public_key_pem": None,
                        "fingerprint": None, "created_at": None}


def test_generate_lalu_me(buyer):
    r = buyer.post("/keys/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["has_keypair"] and body["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
    assert "PRIVATE" not in r.text
    assert body["created_at"].endswith("+07:00")
    assert buyer.get("/keys/me").json() == body


def test_generate_dua_kali_tidak_menimpa(buyer):
    a = buyer.post("/keys/generate").json()
    b = buyer.post("/keys/generate").json()
    assert a == b
    with SessionLocal() as db:
        uid = db.scalar(select(UserKeypair.user_id).where(UserKeypair.public_pem == a["public_key_pem"]))
        assert db.scalar(select(func.count()).select_from(UserKeypair).where(UserKeypair.user_id == uid)) == 1


def test_toko_juga_bisa_punya_kunci(store):
    assert store.post("/keys/generate").json()["has_keypair"]


def test_public_key_user_lain(buyer):
    other = create_user("buyer")
    assert buyer.get(f"/keys/{other.id}/public").status_code == 404  # belum punya kunci
    with SessionLocal() as db:
        pem = keypairs.ensure_keypair(db, db.get(User, other.id)).public_pem
    r = buyer.get(f"/keys/{other.id}/public")
    assert r.status_code == 200
    assert r.json()["public_key_pem"] == pem and r.json()["username"] == other.username
    assert "PRIVATE" not in r.text
    assert buyer.get("/keys/999999/public").status_code == 404


def test_tanpa_login_401(client):
    for method, path in (("get", "/keys/me"), ("post", "/keys/generate"), ("get", "/keys/1/public")):
        assert getattr(client, method)(path).status_code == 401


def test_private_key_tersimpan_terenkripsi_dan_cocok():
    user = create_user("buyer")
    with SessionLocal() as db:
        u = db.get(User, user.id)
        pub_pem, priv = keypairs.get_or_create_keypair(db, u)
        row = keypairs.get_keypair_row(db, u.id)
        der = priv.export_key("DER")
        assert der not in row.priv_wrapped
        assert rsa.public_pem(priv) == pub_pem
        # Kunci simetris yang dienkripsi dengan public key bisa dibuka lagi oleh pemilik.
        sym = get_random_bytes(32)
        assert rsa.decrypt_with(keypairs.load_private_key(db, u), rsa.encrypt_for(pub_pem, sym)) == sym

    db_file = get_settings().database_url.split("sqlite:///", 1)[1]
    with open(db_file, "rb") as fh:
        raw = fh.read()
    assert der not in raw and b"PRIVATE KEY" not in raw
