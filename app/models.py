from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.timeutil import utcnow

ALG_CHECK = "algorithm IN ('aes', 'rc4', 'des')"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('buyer', 'store')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    key_salt: Mapped[bytes] = mapped_column(LargeBinary(16))
    role: Mapped[str] = mapped_column(String(8), default="buyer")
    store_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProfileCiphertext(Base):
    __tablename__ = "profile_ciphertexts"
    __table_args__ = (
        UniqueConstraint("user_id", "algorithm", name="uq_profile_user_alg"),
        CheckConstraint(ALG_CHECK, name="ck_profile_alg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(3))
    iv: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    enc_time_ms: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meta_iv: Mapped[bytes] = mapped_column(LargeBinary)
    meta_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    files: Mapped[list["File"]] = relationship(back_populates="package")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint("category IN ('id_card', 'document', 'video')", name="ck_files_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(10))
    name_iv: Mapped[bytes] = mapped_column(LargeBinary)
    name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    package: Mapped[Package | None] = relationship(back_populates="files")
    ciphertexts: Mapped[list["FileCiphertext"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    keys: Mapped[list["FileKey"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    decrypt_logs: Mapped[list["DecryptLog"]] = relationship(cascade="all, delete-orphan")


class FileCiphertext(Base):
    __tablename__ = "file_ciphertexts"
    __table_args__ = (
        UniqueConstraint("file_id", "algorithm", name="uq_filect_file_alg"),
        CheckConstraint(ALG_CHECK, name="ck_filect_alg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(3))
    iv: Mapped[bytes] = mapped_column(LargeBinary)
    storage_path: Mapped[str] = mapped_column(String(255))
    enc_time_ms: Mapped[float] = mapped_column(Float)

    file: Mapped[File] = relationship(back_populates="ciphertexts")


class FileKey(Base):
    __tablename__ = "file_keys"
    __table_args__ = (
        UniqueConstraint("file_id", "user_id", "algorithm", name="uq_filekey_file_user_alg"),
        CheckConstraint(ALG_CHECK, name="ck_filekey_alg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(3))
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    wrap_tag: Mapped[bytes] = mapped_column(LargeBinary(16))

    file: Mapped[File] = relationship(back_populates="keys")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "status IN ('diajukan', 'ditinjau', 'diterima', 'ditolak')", name="ck_claims_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    store_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="diajukan")
    message_iv: Mapped[bytes] = mapped_column(LargeBinary)
    message_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    summary_iv: Mapped[bytes] = mapped_column(LargeBinary)
    summary_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    replies: Mapped[list["ClaimReply"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimReply.id"
    )
    keys: Mapped[list["ClaimKey"]] = relationship(cascade="all, delete-orphan")


class ClaimReply(Base):
    __tablename__ = "claim_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    body_iv: Mapped[bytes] = mapped_column(LargeBinary)
    body_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    claim: Mapped[Claim] = relationship(back_populates="replies")


class ClaimKey(Base):
    __tablename__ = "claim_keys"
    __table_args__ = (UniqueConstraint("claim_id", "user_id", name="uq_claimkey_claim_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    wrap_tag: Mapped[bytes] = mapped_column(LargeBinary(16))


class DecryptLog(Base):
    """Satu baris per unduhan yang selesai; dipakai /stats untuk avg_dec_ms_per_mb."""

    __tablename__ = "decrypt_logs"
    __table_args__ = (CheckConstraint(ALG_CHECK, name="ck_declog_alg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    algorithm: Mapped[str] = mapped_column(String(3))
    dec_time_ms: Mapped[float] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserKeypair(Base):
    """Pasangan kunci RSA per user. Private key hanya tersimpan terbungkus AES-GCM (key AES user)."""

    __tablename__ = "user_keypairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    public_pem: Mapped[str] = mapped_column(String(1024))
    priv_nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    priv_wrapped: Mapped[bytes] = mapped_column(LargeBinary)
    priv_tag: Mapped[bytes] = mapped_column(LargeBinary(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
