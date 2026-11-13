# Kontrak API: pelengkap PRD

Bentuk JSON utama ada di [`docs/PRD.md`](PRD.md) bagian "Contoh JSON response". File ini hanya berisi yang **belum** dicontohkan di sana. Kalau ada yang bertentangan, PRD yang menang. Semua endpoint bisa dicoba lewat `http://localhost:8000/docs`.

## Aturan umum

- Error selalu `{"detail": "pesan untuk user"}`, langsung bisa ditampilkan.
- Status error: **400** input salah (termasuk `alg` selain `aes`/`rc4`/`des`), **401** belum login atau sesi habis, **403** salah peran, **404** tidak ada atau bukan haknya, **413** file terlalu besar.
- **403 (tambahan dari PRD)**: pembeli memanggil endpoint khusus toko (`PATCH /claims/{id}`), atau toko memanggil endpoint khusus pembeli (`/profile`, `/packages`, `POST /files`, `/stats`, `/stores`, `POST /claims`). Saran: arahkan ke beranda perannya.

## Auth

`POST /auth/register` body `{"username": "dzaky", "password": "minimal8"}` → **201**, bentuk sama dengan `/auth/me`, dan cookie sesi langsung dipasang (masuk otomatis, tidak perlu memanggil login lagi).

- Username 3 sampai 32 karakter `[a-zA-Z0-9_]`, password minimal 8 karakter. Salah format → 400.
- Username sudah dipakai → 400 `{"detail": "Username sudah dipakai"}`.

`POST /auth/login` salah → **401** `{"detail": "Username atau password salah"}`.

`POST /auth/logout` → **200** `{"ok": true}`.

## Profil

`PUT /profile` body `{"data": {...11 field}}`. `religion` dan `health_notes` boleh `null`, field lain wajib diisi. → **200**

```json
{"updated_at": "2026-10-14T10:12:00+07:00", "enc_ms": {"aes": 0.31, "rc4": 0.12, "des": 0.55}}
```

`enc_ms` = waktu enkripsi profil per algoritma (ms), bisa ditampilkan di mode demo.

Aturan isi (salah → 400 dengan pesan per field, mis. `{"detail": "NIK wajib 16 digit angka"}`):
- `nik` tepat 16 digit angka (tanpa spasi/tanda hubung di tengah).
- `birth_date` format `YYYY-MM-DD` (nilai dari `<input type="date">`), tidak boleh di masa depan.
- Spasi di awal/akhir dibuang. `religion`/`health_notes` berisi `""` disimpan sebagai `null`.
- Batas panjang: alamat 500, riwayat kesehatan 1000, nama 200 karakter.

`GET /profile` sebelum profil pernah disimpan: `data` semua `null`, `decrypt_ms` dan `updated_at` `null`. `id_card_file_id` tetap terisi kalau foto KTP sudah diunggah lebih dulu.

## Paket dan file

`POST /packages` → **201**, bentuk sama dengan satu item `GET /packages` (`video_file_id` `null`, `document_count` 0, `total_size_bytes` 0).

`POST /files`: **urutan field penting**. `category` (dan `package_id` kalau ada) harus di-`append` ke `FormData` **sebelum** `file`, karena server mengenkripsi file sambil menerimanya dan perlu tahu batas ukuran sejak awal.

```js
const fd = new FormData();
fd.append("category", "video");
fd.append("package_id", "3");     // opsional; jangan untuk id_card
fd.append("file", input.files[0]); // terakhir
```

Gagal:
- format, kategori, atau isi file tidak cocok dengan ekstensinya → **400**, mis. `{"detail": "Format video yang diterima: mkv, mov, mp4"}`
- terlalu besar → **413**, mis. `{"detail": "Ukuran video maksimal 100 MB"}` (KTP 5 MB, dokumen 20 MB)
- `category` dikirim setelah `file` → **400** `{"detail": "Field category harus dikirim sebelum file"}`
- `package_id` bukan milik user → **404**; `package_id` untuk `id_card` → **400**
- file kosong → **400**

`GET /files/{id}/download?alg=aes` → **200** isi file asli dengan `Content-Type` sesuai file dan `Content-Disposition` berisi nama asli. Bisa dipakai langsung sebagai `src` `<video>`/`<img>`. Untuk video: bisa diputar, tapi belum bisa dimajukan (seek) karena belum mendukung HTTP Range.

`DELETE /files/{id}` → **204** tanpa body.

## Klaim

Yang dilihat toko pada klaim ke tokonya: video dan dokumen paket itu, nama barang, no. pesanan, nama pembeli, status "KTP terverifikasi" (ya/tidak), pesan, dan balasan. Toko **tidak** menerima NIK, HP, alamat, rekening, atau foto KTP.

`POST /claims` gagal:
- paket bukan milik pembeli, atau `store_user_id` bukan toko → **404**
- paket masih punya klaim berstatus `diajukan`/`ditinjau` → **400** `{"detail": "Paket ini masih punya klaim yang berjalan"}`
- paket belum punya video/dokumen → **400**

File yang ditambahkan ke paket selama klaim masih `diajukan`/`ditinjau` (mis. setelah toko memilih "Minta bukti tambahan") otomatis ikut terbuka untuk toko itu.

`video_file_id` di `GET /claims` dan `files` di `GET /claims/{id}` hanya berisi file yang boleh dibuka oleh user yang sedang login.

`POST /claims/{id}/replies` body `{"body": "..."}` → **201**, bentuk satu item `replies` di `GET /claims/{id}`:

```json
{"id": 2, "author_role": "buyer", "author_name": "Dzaky A.", "body": "Baik, saya tunggu.", "created_at": "2026-10-13T10:00:00+07:00"}
```

`PATCH /claims/{id}`: `reply` boleh dikosongkan atau tidak dikirim.

## Statistik

`GET /stats` hanya menghitung file milik pembeli yang login.

- `avg_enc_ms_per_mb` / `avg_dec_ms_per_mb`: total waktu ÷ total MB (tertimbang). Bernilai `null` kalau belum ada data; `avg_dec_ms_per_mb` baru terisi setelah file pernah diunduh sampai selesai dengan algoritma itu.
- `total_cipher_bytes`: ukuran ciphertext di disk. AES/DES sedikit lebih besar dari aslinya karena padding; RC4 sama persis.
- `per_category` hanya berisi kategori yang punya file, urutan video → document → id_card.

## Assignment 2: permintaan akses data (`/access-requests`)

Pembeli meminta melihat data pribadi pembeli lain. Semua endpoint khusus pembeli (toko → 403). Bukan pihak dalam permintaan → 404.

Alur: peminta mengajukan → pemilik menyetujui dan mendapat **kode akses** → pemilik mengirim kode lewat WA/email (di luar aplikasi) → peminta menempel kode → peminta bisa melihat data sampai kedaluwarsa atau dicabut.

Bentuk satu permintaan (dipakai di semua respons di bawah):

```json
{"id": 1, "requester": {"id": 5, "username": "budi"}, "owner": {"id": 3, "username": "dzaky"},
 "scope": {"profile": true, "id_card": true, "documents": true},
 "status": "disetujui", "created_at": "2026-11-13T14:00:00+07:00", "decided_at": "2026-11-13T14:05:00+07:00",
 "expires_at": "2026-11-20T14:05:00+07:00", "redeemed": false}
```

`status`: `menunggu`, `disetujui`, `ditolak`, `dicabut`, `kedaluwarsa`.

| Method | Path | Siapa | Body | Respons |
| --- | --- | --- | --- | --- |
| POST | `/access-requests` | peminta | `{"username": "dzaky", "scope": {"profile": true, "id_card": true, "documents": false}}` | 201, satu permintaan |
| GET | `/access-requests?box=incoming` | pemilik | | `{"items": [...]}` permintaan yang masuk |
| GET | `/access-requests?box=outgoing` | peminta | | `{"items": [...]}` permintaan yang dikirim |
| GET | `/access-requests/{id}` | keduanya | | satu permintaan |
| POST | `/access-requests/{id}/approve` | pemilik | `{"valid_days": 7}` (opsional, 1–30) | satu permintaan + `access_code`, `code_algorithm`, `requester_fingerprint` |
| GET | `/access-requests/{id}/code` | pemilik | | `{"request_id", "expires_at", "access_code", "code_algorithm", "requester_fingerprint"}` untuk menyalin ulang |
| POST | `/access-requests/{id}/reject` | pemilik | | satu permintaan (`ditolak`) |
| POST | `/access-requests/{id}/revoke` | pemilik | | satu permintaan (`dicabut`) |
| POST | `/access-requests/{id}/redeem` | peminta | `{"access_code": "<teks dari WA>"}` | satu permintaan (`redeemed: true`) |
| GET | `/access-requests/{id}/data` | peminta | | lihat di bawah |
| GET | `/access-requests/{id}/files/{file_id}/download?alg=aes` | peminta | | isi file asli (sama seperti `/files/{id}/download`) |

`GET /access-requests/{id}/data`:

```json
{"request_id": 1, "owner": {"id": 3, "username": "dzaky"}, "expires_at": "2026-11-20T14:05:00+07:00",
 "profile": {"full_name": "Dzaky A.", "nik": "3578…", "...": "11 field seperti GET /profile"},
 "files": [{"id": 7, "category": "id_card", "name": "ktp.png", "mime_type": "image/png", "size_bytes": 1234},
           {"id": 9, "category": "document", "name": "slip-gaji.pdf", "mime_type": "application/pdf", "size_bytes": 5678}]}
```

`profile` bernilai `null` kalau tidak diminta. Video tidak pernah ikut.

Error penting (semua 400, `detail` bisa langsung ditampilkan):
- "Pilih minimal satu data yang diminta", "Tidak bisa meminta data sendiri", "Masih ada permintaan yang menunggu atau aktif ke pembeli ini"
- username bukan pembeli atau tidak ada → 404 "Pembeli tidak ditemukan"
- "Kode akses tidak valid", "Tempelkan kode akses dari pemilik terlebih dahulu"
- "Akses sudah kedaluwarsa", "Akses sudah dicabut pemilik", "Permintaan belum disetujui", "Permintaan ini sudah diproses"

Saran tampilan:
- `access_code` panjangnya sekitar 344 karakter base64. Sediakan tombol **Salin** dan tautan **Kirim lewat WhatsApp** (`https://wa.me/?text=` + kode yang di-URL-encode). Spasi dan baris baru saat ditempel tetap diterima.
- Tampilkan `requester_fingerprint` ke pemilik supaya bisa dicocokkan dengan peminta.
