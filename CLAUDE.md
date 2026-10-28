# Awan: Brankas Bukti Unboxing (Backend)

Tugas kuliah Keamanan Informasi, Assignment 1. Aku (Yae) pegang backend. Kamu bantu aku mengerjakan **backend saja**. Sumber kebenaran: `docs/PRD.md` (PRD gabungan versi tim). Struktur folder dan nama branch mengikuti `README.md` tim. Kalau ada yang bertentangan antara file ini dan PRD, tanya dulu sebelum menulis kode.

Inti penilaian: data user disimpan terenkripsi dengan AES, RC4, dan DES, bisa diambil lagi dalam bentuk asli, dan hanya bisa diakses setelah login username + password. Tampilan tidak dinilai.

## Batasan kerja

- Jangan ubah `app/templates/` dan `app/static/`. Itu milik Dzaky (frontend). Kalau butuh perubahan di sana, tulis catatan untukku.
- Jangan ubah bentuk JSON di bagian "Kontrak API". Frontend sudah membuat mock dengan bentuk persis itu. Kalau memang harus berubah, berhenti dan tanya.
- Semua gratis dan jalan di localhost. Jangan tambah layanan cloud, Docker, Redis, Postgres, atau dependency berbayar.
- Jangan tambah fitur di luar scope (lupa password, verifikasi email, chat real-time, notifikasi, registrasi toko, deploy).
- Jangan pernah menulis plaintext data user atau file ke disk, termasuk file temporary dan log.
- Jangan log isi data pribadi, key, IV, atau password. Log cukup id dan ukuran.
- Komentar kode seperlunya saja.

## Stack

Python 3.11+, FastAPI, SQLAlchemy 2.x, SQLite, PyCryptodome, passlib[bcrypt], PyJWT, python-multipart, Jinja2, pydantic-settings. Test pakai pytest + httpx (TestClient).

## Struktur folder

```
app/
  main.py            # buat app, mount static, include router
  config.py          # Settings dari .env
  db.py              # engine, SessionLocal, Base, get_db
  models.py          # semua tabel SQLAlchemy
  schemas.py         # Pydantic request/response, ikut kontrak
  deps.py            # get_current_user, require_buyer, require_store
  security/
    passwords.py     # hash dan verify bcrypt
    sessions.py      # buat/baca JWT, set/hapus cookie
  crypto/            # modul enkripsi (bagian Anggota 2, lihat "Modul enkripsi")
    aes.py rc4.py des.py   # implementasi per algoritma
    _cbc.py          # streaming CBC + PKCS7, dipakai aes.py dan des.py
    keys.py
    vault.py
  services/
    profile.py
    files.py
    packages.py
    claims.py
    stats.py
  routes/
    auth.py profile.py packages.py files.py claims.py stores.py stats.py
    pages.py         # MILIK FE (branch fe), jangan dibuat/diubah di sini
  templates/         # JANGAN DIUBAH (frontend)
  static/            # JANGAN DIUBAH (frontend)
scripts/seed.py      # buat akun toko dan pembeli demo
tests/
storage/             # ciphertext file, di .gitignore
.env.example
requirements.txt
```

`.gitignore` wajib memuat: `.env`, `storage/`, `*.db`, `__pycache__/`, `.venv/`, `lab-session-information-security-main/` (materi mentor, hanya referensi).

## Konfigurasi (.env)

```
MASTER_SECRET=          # 32 byte acak, base64. Generate: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
JWT_SECRET=             # string acak, terpisah dari MASTER_SECRET
DATABASE_URL=sqlite:///./awan.db
STORAGE_DIR=./storage
SESSION_MINUTES=60
```

Aplikasi harus gagal start dengan pesan jelas kalau `MASTER_SECRET` atau `JWT_SECRET` kosong.

## Desain enkripsi

### Algoritma

| Algoritma | Mode | Key | IV / nonce | Padding |
| --- | --- | --- | --- | --- |
| AES | CBC | 32 byte | IV acak 16 byte | PKCS7 |
| DES | CBC | 8 byte | IV acak 8 byte | PKCS7 |
| RC4 (ARC4) | stream | 16 byte | nonce acak 16 byte | tidak ada |

Setiap data dienkripsi **terpisah** dengan ketiga algoritma: satu data menghasilkan tiga ciphertext. Bukan enkripsi berlapis.

RC4: key yang dipakai untuk satu ciphertext = 16 byte pertama `HMAC-SHA256(rc4_key, nonce)`. Jangan pernah pakai key RC4 yang sama dua kali.

### Key user

- Tiap user punya `key_salt` acak 16 byte, dibuat saat register.
- `HKDF-SHA256(MASTER_SECRET, salt=key_salt, info=b"awan-user-v1")`, panjang 56 byte, dipotong jadi AES 32 | RC4 16 | DES 8.
- Key user tidak pernah disimpan. Selalu diturunkan ulang saat dibutuhkan.
- Key user dipakai untuk: profil (`profile_ciphertexts`), metadata paket (`packages.meta_ciphertext`, AES saja), nama file (`files.name_ciphertext`, AES saja), dan membungkus kunci file.

### Kunci file terbungkus per penerima

1. Saat upload, buat kunci file acak per algoritma (AES 32, RC4 16, DES 8). Isi file dienkripsi dengan kunci ini.
2. Tiap kunci file dibungkus dengan AES-256-GCM memakai key AES pemilik, simpan di `file_keys` (satu baris per file x penerima x algoritma). Simpan `wrap_nonce` (12 byte), `wrapped_key`, `wrap_tag`.
3. Saat klaim diajukan: buka bungkus dengan key pemilik, bungkus ulang dengan key AES admin toko tujuan (HKDF dari `key_salt` toko), tambah baris `file_keys` untuk toko itu. Lakukan untuk semua file di paket yang diklaim, kecuali `id_card`.
4. Saat unduh: cari baris `file_keys` untuk (file, user login, algoritma). Tidak ada baris = 404.

Profil (NIK, HP, alamat, rekening) **tidak pernah** dibungkus untuk toko.

### Streaming file besar

- Baca upload per potongan 64 KB, enkripsi langsung ke tiga file ciphertext di `storage/` secara bersamaan. Jangan muat file utuh ke RAM.
- CBC: pakai satu objek cipher per file, sisakan byte yang belum kelipatan block, padding hanya di potongan terakhir. Saat dekripsi, tahan block terakhir sampai akhir stream lalu unpad.
- Nama file di disk: UUID4 + akhiran algoritma, mis. `storage/ab/abcd...-aes.bin`. Nama asli ikut dienkripsi di database.
- Tegakkan batas ukuran saat streaming (bukan setelah selesai): KTP 5 MB, dokumen 20 MB, video 100 MB. Lewat batas: hapus file parsial, balas 413.
- Validasi ekstensi dan MIME: `id_card` jpg/jpeg/png, `document` pdf/doc/docx/xls/xlsx, `video` mp4/mkv/mov. Salah format: 400.
- Catat `enc_time_ms` per algoritma per file.
- Kalau upload gagal di tengah, hapus semua file ciphertext parsial dan rollback baris database.

### Modul enkripsi (bagian Anggota 2)

Modul `app/crypto/` dikerjakan Anggota 2. Backend hanya memakai interface ini. Kalau modulnya belum ada di repo, buat implementasi sementara yang memenuhi interface dan test yang sama, lalu beri tahu aku supaya bisa diganti.

```python
Algorithm = Literal["aes", "rc4", "des"]

# keys.py
def new_key_salt() -> bytes                                                  # 16 byte, saat register
def derive_user_keys(key_salt: bytes, master_secret: bytes | None = None) -> dict[Algorithm, bytes]   # default MASTER_SECRET dari .env
def new_file_keys() -> dict[Algorithm, bytes]

# vault.py (memanggil aes.py / rc4.py / des.py sesuai alg)
def encrypt_bytes(alg, key, plaintext: bytes) -> tuple[bytes, bytes]          # (iv_or_nonce, ciphertext)
def decrypt_bytes(alg, key, iv: bytes, ciphertext: bytes) -> bytes
class StreamEncryptor:   # __init__(alg, key) -> .iv ; .update(chunk) -> bytes ; .finalize() -> bytes
class StreamDecryptor:   # __init__(alg, key, iv) ; .update(chunk) -> bytes ; .finalize() -> bytes
def wrap_key(kek: bytes, key: bytes) -> tuple[bytes, bytes, bytes]             # (nonce, wrapped, tag)
def unwrap_key(kek: bytes, nonce: bytes, wrapped: bytes, tag: bytes) -> bytes
```

## Skema database

| Tabel | Kolom |
| --- | --- |
| users | id, username (unik), password_hash, key_salt, role (`buyer`/`store`), store_name (nullable), created_at |
| profile_ciphertexts | id, user_id, algorithm, iv, ciphertext, enc_time_ms, updated_at (3 baris per user, unik per user+algorithm) |
| packages | id, user_id, meta_iv, meta_ciphertext, created_at (meta = JSON `{item_name, store, order_no}` dienkripsi AES) |
| files | id, user_id, package_id (nullable), category (`id_card`/`document`/`video`), name_iv, name_ciphertext, mime_type, size_bytes, created_at |
| file_ciphertexts | id, file_id, algorithm, iv, storage_path, enc_time_ms |
| file_keys | id, file_id, user_id, algorithm, wrap_nonce, wrapped_key, wrap_tag (unik per file+user+algorithm) |
| claims | id, package_id, buyer_id, store_user_id, status (`diajukan`/`ditinjau`/`diterima`/`ditolak`), message_iv, message_ciphertext, summary_iv, summary_ciphertext, created_at, updated_at |
| claim_replies | id, claim_id, author_id, body_iv, body_ciphertext, created_at |
| claim_keys | id, claim_id, user_id, wrap_nonce, wrapped_key, wrap_tag (unik per claim+user) |
| decrypt_logs | id, file_id, user_id (yang mengunduh), algorithm, dec_time_ms, size_bytes, created_at |

Pesan, balasan, dan `summary` klaim (JSON `{buyer_name, item_name, order_no}`, salinan saat klaim dibuat) dienkripsi AES dengan **kunci klaim** acak 32 byte, yang dibungkus AES-GCM untuk pembeli dan toko di `claim_keys`.

Profil disimpan sebagai JSON 11 field, dienkripsi 3 kali. `religion` dan `health_notes` opsional (boleh `null`), sisanya wajib.

Hapus file = hapus baris `files`, `file_ciphertexts`, `file_keys`, dan tiga file di disk.

## Auth dan sesi

- Register: username 3 sampai 32 karakter `[a-zA-Z0-9_]`, password minimal 8 karakter. Username sudah dipakai: 400.
- Login salah: 401 dengan `{"detail": "Username atau password salah"}`, tanpa menyebut mana yang salah.
- JWT (HS256) berisi `sub` = user id dan `role`, disimpan di cookie `session` dengan `HttpOnly`, `SameSite=Lax`, `Path=/`, umur `SESSION_MINUTES`.
- Sesi geser: setiap request yang lolos auth mengeluarkan cookie baru dengan masa berlaku diperpanjang, supaya upload besar tidak memutus sesi.
- Endpoint API tanpa sesi valid: 401. Route halaman milik FE; FE mengecek sesi lewat `GET /auth/me` dan mengarahkan ke `/masuk` saat 401.
- Pembeli tidak bisa memakai endpoint khusus toko dan sebaliknya: 403. Tapi akses ke resource milik orang lain selalu 404, bukan 403.

## Kontrak API

Error selalu `{"detail": "pesan untuk user"}` dengan status 400, 401, 403, 404, atau 413. Waktu memakai ISO 8601 dengan offset `+07:00`. Parameter `alg` default `aes`; nilai selain `aes`/`rc4`/`des`: 400.

| Method | Path | Siapa | Fungsi |
| --- | --- | --- | --- |
| POST | /auth/register | publik | Buat akun pembeli |
| POST | /auth/login | publik | Verifikasi, set cookie |
| POST | /auth/logout | login | Hapus cookie |
| GET | /auth/me | login | User login: `{id, username, role, store_name}` (juga bentuk response login dan register) |
| GET | /profile?alg=aes | pembeli | Profil terdekripsi |
| PUT | /profile | pembeli | Body `{"data": {...11 field}}`, simpan profil, enkripsi 3 kali |
| POST | /packages | pembeli | Buat paket |
| GET | /packages | pembeli | Daftar paket + jumlah file |
| GET | /packages/{id} | pembeli | Detail paket + daftar file |
| POST | /files | pembeli | Upload multipart: `file`, `category`, `package_id` (opsional) |
| GET | /files?category=video | pembeli | Daftar file milik user |
| GET | /files/{id}/download?alg=des | pemilik atau toko yang punya `file_keys` | Unduh file terdekripsi (streaming, `Content-Disposition` dengan nama asli) |
| DELETE | /files/{id} | pemilik | Hapus file + 3 ciphertext |
| GET | /stats | pembeli | Waktu dan ukuran per algoritma |
| GET | /stores | pembeli | Daftar toko |
| POST | /claims | pembeli | Ajukan klaim: `package_id`, `store_user_id`, `message` |
| GET | /claims | keduanya | Pembeli: klaim miliknya. Toko: klaim ke tokonya |
| GET | /claims/{id} | keduanya | Detail klaim, file, balasan |
| PATCH | /claims/{id} | toko | Ubah status + balasan |
| POST | /claims/{id}/replies | keduanya | Tambah balasan |

Contoh bentuk yang sudah disepakati dengan frontend (angka hanya ilustrasi):

`GET /profile?alg=aes`
```json
{
  "algorithm": "aes",
  "decrypt_ms": 0.42,
  "updated_at": "2026-10-14T10:12:00+07:00",
  "data": {
    "full_name": "Dzaky A.", "nik": "3578xxxxxxxxxxxx", "birth_date": "2004-05-12",
    "gender": "Laki-laki", "nationality": "WNI", "marital_status": "Belum kawin",
    "address": "Jl. Contoh No. 12, Surabaya", "phone": "0812xxxxxxxx",
    "bank_account": "BCA 1234xxxxxx", "religion": null, "health_notes": null
  },
  "id_card_file_id": 7
}
```
Profil belum pernah diisi: `data` berisi semua field `null`, `updated_at` dan `id_card_file_id` `null`.

`GET /packages`
```json
{"items": [{"id": 3, "item_name": "Monitor 24 inci", "store": "Toko Elektra",
  "order_no": "INV/2026/10/0412", "created_at": "2026-10-11T16:45:00+07:00",
  "video_file_id": 12, "document_count": 2, "total_size_bytes": 190840112}]}
```

`GET /files?category=video`
```json
{"items": [{"id": 12, "package_id": 3, "category": "video", "name": "unboxing-monitor.mp4",
  "mime_type": "video/mp4", "size_bytes": 190601216, "created_at": "2026-10-11T16:45:00+07:00",
  "algorithms": ["aes", "rc4", "des"]}]}
```

`GET /stats`
```json
{"per_algorithm": [
   {"algorithm": "aes", "avg_enc_ms_per_mb": 4.1, "avg_dec_ms_per_mb": 3.9, "total_cipher_bytes": 191004672},
   {"algorithm": "rc4", "avg_enc_ms_per_mb": 2.7, "avg_dec_ms_per_mb": 2.6, "total_cipher_bytes": 190601216},
   {"algorithm": "des", "avg_enc_ms_per_mb": 21.8, "avg_dec_ms_per_mb": 21.2, "total_cipher_bytes": 191004680}],
 "per_category": [{"category": "video", "algorithm": "aes", "avg_enc_ms_per_mb": 4.0}]}
```

Contoh `/auth/me`, `/packages/{id}`, `/stores`, `POST /claims`, `/claims`, `/claims/{id}` ada di `docs/PRD.md` (bagian "Contoh JSON response") dan di CLAUDE.md branch `fe`; ikuti persis. Yang belum dicontohkan di PRD ditulis di `docs/api-contract.md`.

## Route halaman

Route halaman (`/masuk`, `/daftar`, `/brankas`, `/unboxing/baru`, `/paket/{id}`, `/paket/{id}/klaim`, `/profil`, `/statistik`, `/toko`, `/toko/klaim/{id}`) dan `app/routes/pages.py` dikerjakan Dzaky di branch `fe`. `app/main.py` meng-include `pages` kalau modulnya ada. Path API tidak boleh bentrok dengan path halaman.

## Hal yang PRD belum jelaskan (tanya aku sebelum memutuskan)

1. **Pesan klaim dan balasan.** DIPUTUSKAN: kunci klaim acak, dibungkus untuk pembeli dan toko di `claim_keys`.
2. **Nama pembeli untuk toko.** DIPUTUSKAN: salinan nama pembeli (nama lengkap profil, atau username kalau profil kosong), nama barang, dan no. pesanan dienkripsi dengan kunci klaim. "KTP terverifikasi" = pembeli punya file `id_card`. Toko tidak pernah menerima NIK, HP, alamat, rekening, atau foto KTP.
3. **`avg_dec_ms_per_mb`.** DIPUTUSKAN: `decrypt_logs` diisi setiap unduhan yang selesai (unduhan terputus tidak dicatat). Hanya waktu dekripsi yang diukur. Rata-rata per MB di `/stats` tertimbang (total ms / total MB) atas file milik pembeli, termasuk unduhan oleh toko.
4. **Seek video.** Download streaming tanpa dukungan HTTP Range membuat video bisa diputar tapi tidak bisa dimajukan. Cukup untuk demo kecuali aku minta lebih.

Ditunda (setelah Assignment 1): fitur chat pembeli dan toko di web. Sementara percakapan memakai balasan klaim.

## Urutan kerja

Kerjakan satu fase, jalankan test, lalu commit sebelum lanjut. Di akhir tiap fase, ringkas apa yang selesai dan apa yang perlu aku cek.

1. **Skeleton**: struktur folder, config, db, `.env.example`, `.gitignore`, `requirements.txt`, README cara jalan. Semua endpoint ada sebagai stub yang mengembalikan contoh JSON kontrak, supaya frontend bisa langsung pakai `/docs`.
2. **Modul enkripsi + test**: interface di atas, round-trip ketiga algoritma.
3. **Auth**: register, login, logout, sesi, dependency role.
4. **Profil**: PUT dan GET dengan pilihan algoritma.
5. **Paket dan file**: upload streaming, list, download, delete, batas ukuran.
6. **Klaim dan toko**: `file_keys` dibungkus ulang, endpoint klaim, seed akun toko.
7. **Stats**.
8. **Pengujian akhir**: semua test hijau, skenario demo dari awal sampai akhir.

## Seed

`python scripts/seed.py` membuat dua akun toko (`elektra` / Toko Elektra, `gadgetin` / Toko Gadgetin) dan satu pembeli demo (`dzaky`). Password diambil dari argumen atau dicetak ke terminal, tidak di-hardcode di repo. Seed aman dijalankan dua kali.

## Test wajib

- Round-trip encrypt/decrypt tiap algoritma untuk ukuran 0 byte, 1 byte, 15/16/17 byte, tepat 64 KB, 64 KB + 1, dan 1 MB. Hasil dekripsi harus identik byte per byte.
- Ciphertext tidak sama dengan plaintext, dan dua enkripsi data yang sama menghasilkan ciphertext berbeda.
- Upload satu file menghasilkan tepat 3 baris `file_ciphertexts`, 3 file di disk, dan 3 baris `file_keys` milik pemilik.
- Unduh dengan `alg=aes`, `rc4`, dan `des` menghasilkan file yang sama dengan aslinya.
- User lain mengakses file, paket, atau klaim yang bukan miliknya: 404.
- Toko tanpa klaim mengakses file: 404. Setelah klaim ke Toko Elektra: Toko Elektra bisa unduh (200), Toko Gadgetin tetap 404.
- Klaim tidak pernah membuat baris `file_keys` untuk file `id_card`.
- File melebihi batas: 413 dan tidak ada file parsial tersisa di `storage/`.
- Endpoint tanpa cookie: 401. Login salah: 401 dengan pesan generik.
- Tidak ada plaintext tersimpan: setelah upload file berisi string penanda, string itu tidak muncul di `storage/` maupun file database.

## Perintah

```
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # lalu isi secret
python scripts/seed.py
uvicorn app.main:app --reload
pytest -q
```

## Git

Repo tim: https://github.com/ilyas-r27/awan-security-project. Kerja di branch `be` (FE di `fe`). Commit kecil per fase dengan pesan singkat bahasa Inggris (`feat: streaming file encryption`). Gabung ke `main` lewat PR, jangan push ke `main` langsung. Jangan commit `.env`, `storage/`, atau `*.db`.
