from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Algorithm = Literal["aes", "rc4", "des"]
Category = Literal["id_card", "document", "video"]
Role = Literal["buyer", "store"]
ClaimStatus = Literal["diajukan", "ditinjau", "diterima", "ditolak"]


# --- Auth ---

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    # Tanpa aturan format: login salah selalu 401 generik, bukan 400.
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    store_name: str | None


class OkOut(BaseModel):
    ok: bool = True


# --- Profil ---

class ProfileData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    nik: str = Field(pattern=r"^[0-9]{16}$")
    birth_date: str = Field(min_length=1, max_length=10)
    gender: str = Field(min_length=1, max_length=32)
    nationality: str = Field(min_length=1, max_length=64)
    marital_status: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=500)
    phone: str = Field(min_length=1, max_length=32)
    bank_account: str = Field(min_length=1, max_length=100)
    religion: str | None = Field(default=None, max_length=64)
    health_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("religion", "health_notes", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("birth_date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        try:
            parsed = date.fromisoformat(v)
        except ValueError:
            raise ValueError("format tanggal YYYY-MM-DD") from None
        if len(v) != 10 or parsed > date.today():
            raise ValueError("tanggal tidak valid")
        return v


class ProfileDataOut(BaseModel):
    full_name: str | None = None
    nik: str | None = None
    birth_date: str | None = None
    gender: str | None = None
    nationality: str | None = None
    marital_status: str | None = None
    address: str | None = None
    phone: str | None = None
    bank_account: str | None = None
    religion: str | None = None
    health_notes: str | None = None


class ProfileOut(BaseModel):
    algorithm: Algorithm
    decrypt_ms: float | None
    updated_at: str | None
    data: ProfileDataOut
    id_card_file_id: int | None


class ProfileUpdate(BaseModel):
    data: ProfileData


class ProfileSaved(BaseModel):
    updated_at: str
    enc_ms: dict[Algorithm, float]


# --- File ---

class FileOut(BaseModel):
    id: int
    package_id: int | None
    category: Category
    name: str
    mime_type: str
    size_bytes: int
    created_at: str
    algorithms: list[Algorithm]


class FileList(BaseModel):
    items: list[FileOut]


# --- Paket ---

class PackageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_name: str = Field(min_length=1, max_length=200)
    store: str = Field(min_length=1, max_length=200)
    order_no: str = Field(min_length=1, max_length=100)


class PackageOut(BaseModel):
    id: int
    item_name: str
    store: str
    order_no: str
    created_at: str
    video_file_id: int | None
    document_count: int
    total_size_bytes: int


class PackageList(BaseModel):
    items: list[PackageOut]


class PackageClaim(BaseModel):
    id: int
    status: ClaimStatus


class PackageDetail(BaseModel):
    id: int
    item_name: str
    store: str
    order_no: str
    created_at: str
    files: list[FileOut]
    claim: PackageClaim | None


# --- Toko ---

class StoreOut(BaseModel):
    id: int
    store_name: str


class StoreList(BaseModel):
    items: list[StoreOut]


# --- Klaim ---

class ClaimCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    package_id: int
    store_user_id: int
    message: str = Field(min_length=1, max_length=2000)


class ClaimUpdate(BaseModel):
    status: ClaimStatus
    reply: str | None = Field(default=None, max_length=2000)


class ReplyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=2000)


class ClaimCreated(BaseModel):
    id: int
    status: ClaimStatus


class ReplyOut(BaseModel):
    id: int
    author_role: Role
    author_name: str
    body: str
    created_at: str


class ClaimOut(BaseModel):
    id: int
    package_id: int
    item_name: str
    order_no: str
    buyer_name: str
    store_name: str
    status: ClaimStatus
    video_file_id: int | None
    created_at: str


class ClaimList(BaseModel):
    items: list[ClaimOut]


class ClaimPackage(BaseModel):
    id: int
    item_name: str
    order_no: str


class ClaimBuyer(BaseModel):
    name: str
    ktp_verified: bool


class ClaimFile(BaseModel):
    id: int
    category: Category
    name: str
    mime_type: str
    size_bytes: int


class ClaimDetail(BaseModel):
    id: int
    status: ClaimStatus
    message: str
    created_at: str
    package: ClaimPackage
    buyer: ClaimBuyer
    store: StoreOut
    files: list[ClaimFile]
    replies: list[ReplyOut]


# --- Stats ---

class AlgorithmStat(BaseModel):
    algorithm: Algorithm
    avg_enc_ms_per_mb: float | None
    avg_dec_ms_per_mb: float | None
    total_cipher_bytes: int


class CategoryStat(BaseModel):
    category: Category
    algorithm: Algorithm
    avg_enc_ms_per_mb: float | None


class StatsOut(BaseModel):
    per_algorithm: list[AlgorithmStat]
    per_category: list[CategoryStat]


class ErrorOut(BaseModel):
    detail: str


class KeypairOut(BaseModel):
    has_keypair: bool
    algorithm: str = "RSA-2048"
    public_key_pem: str | None
    fingerprint: str | None
    created_at: str | None


class PublicKeyOut(BaseModel):
    user_id: int
    username: str
    algorithm: str = "RSA-2048"
    public_key_pem: str
    fingerprint: str
