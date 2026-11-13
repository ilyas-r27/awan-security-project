from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import Base, engine
from app import models  # noqa: F401  (daftarkan tabel ke Base.metadata)
from app.security.sessions import response_sets_session, set_session_cookie
from app.routes import auth, claims, files, keys, packages, profile, stats, stores

try:
    import app.routes.pages as pages  # milik FE (branch fe)
except ModuleNotFoundError as exc:
    if exc.name != "app.routes.pages":
        raise
    pages = None

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"

GENERIC_MESSAGES = {
    401: "Silakan masuk terlebih dahulu",
    403: "Akses tidak diizinkan",
    404: "Tidak ditemukan",
    405: "Metode tidak diizinkan",
}

FIELD_LABELS = {
    "alg": "Algoritma harus aes, rc4, atau des",
    "category": "Kategori harus id_card, document, atau video",
    "username": "Username 3 sampai 32 karakter, hanya huruf, angka, dan _",
    "password": "Password minimal 8 karakter",
    "file": "File wajib dipilih",
    "data": "Data profil wajib dikirim dalam field data",
    "full_name": "Nama lengkap wajib diisi",
    "nik": "NIK wajib 16 digit angka",
    "birth_date": "Tanggal lahir wajib diisi dengan format YYYY-MM-DD",
    "gender": "Jenis kelamin wajib diisi",
    "nationality": "Kewarganegaraan wajib diisi",
    "marital_status": "Status perkawinan wajib diisi",
    "address": "Alamat wajib diisi",
    "phone": "Nomor telepon wajib diisi",
    "bank_account": "Nomor rekening wajib diisi",
    "religion": "Agama terlalu panjang",
    "health_notes": "Riwayat kesehatan terlalu panjang",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Awan: Brankas Bukti Unboxing", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def sliding_session(request: Request, call_next):
    response = await call_next(request)
    token = getattr(request.state, "refreshed_session", None)
    # Jangan timpa cookie yang sengaja dipasang/dihapus endpoint (login, logout).
    if token and not response_sets_session(response):
        set_session_cookie(response, token)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    # Kontrak hanya mengenal 400; pesan diambil dari error pertama tanpa menggemakan input user.
    err = exc.errors()[0] if exc.errors() else {}
    loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "form")]
    field = loc[-1] if loc else ""
    if field in FIELD_LABELS:
        message = FIELD_LABELS[field]
    elif field:
        message = f"Input tidak valid: {'.'.join(loc)} ({err.get('msg', 'tidak valid')})"
    else:
        message = "Input tidak valid"
    return JSONResponse(status_code=400, content={"detail": message})


@app.exception_handler(StarletteHTTPException)
async def http_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if not isinstance(detail, str) or detail in ("Not Found", "Method Not Allowed", "Unauthorized", "Forbidden"):
        detail = GENERIC_MESSAGES.get(exc.status_code, "Permintaan gagal")
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)


for r in (auth, profile, packages, files, stores, claims, stats, keys):
    app.include_router(r.router)
if pages is not None:
    app.include_router(pages.router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
