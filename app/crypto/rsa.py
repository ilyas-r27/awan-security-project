"""RSA-2048 untuk Assignment 2 (kirim kunci simetris) dan Assignment 3 (tanda tangan PDF).

Private key disimpan sebagai DER yang dibungkus AES-256-GCM (vault.wrap_key) dengan key AES user.
"""

from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.PublicKey.RSA import RsaKey

from app.crypto import vault

KEY_BITS = 2048
# Batas plaintext OAEP-SHA256 untuk RSA-2048: 256 - 2*32 - 2.
OAEP_MAX_BYTES = KEY_BITS // 8 - 2 * SHA256.digest_size - 2


def generate_keypair() -> RsaKey:
    return RSA.generate(KEY_BITS)


def public_pem(key: RsaKey) -> str:
    return key.publickey().export_key("PEM").decode()


def load_public(pem: str | bytes) -> RsaKey:
    key = RSA.import_key(pem)
    if key.has_private():
        raise ValueError("Yang diberikan harus public key")
    return key


def fingerprint(pem: str | bytes) -> str:
    """SHA-256 dari public key (DER), ditampilkan hex berpasangan supaya mudah dicocokkan manual."""
    der = RSA.import_key(pem).publickey().export_key("DER")
    hx = SHA256.new(der).hexdigest()
    return ":".join(hx[i : i + 2] for i in range(0, len(hx), 2))


def wrap_private(kek: bytes, key: RsaKey) -> tuple[bytes, bytes, bytes]:
    return vault.wrap_key(kek, key.export_key("DER"))


def unwrap_private(kek: bytes, nonce: bytes, wrapped: bytes, tag: bytes) -> RsaKey:
    return RSA.import_key(vault.unwrap_key(kek, nonce, wrapped, tag))


def encrypt_for(public: RsaKey | str | bytes, data: bytes) -> bytes:
    """RSA-OAEP (SHA-256). Untuk data kecil seperti kunci simetris."""
    key = public if isinstance(public, RsaKey) else load_public(public)
    if len(data) > OAEP_MAX_BYTES:
        raise ValueError(f"Data maksimal {OAEP_MAX_BYTES} byte")
    return PKCS1_OAEP.new(key.publickey(), hashAlgo=SHA256).encrypt(data)


def decrypt_with(private: RsaKey, ciphertext: bytes) -> bytes:
    """Raise ValueError kalau ciphertext bukan untuk key ini atau sudah diubah."""
    return PKCS1_OAEP.new(private, hashAlgo=SHA256).decrypt(ciphertext)
