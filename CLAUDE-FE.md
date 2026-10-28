# Awan — Frontend

Tugas 1 Keamanan Informasi (ITS). Kamu mengerjakan **FRONTEND saja**. Backend (auth, database, enkripsi AES/RC4/DES, semua endpoint API) dikerjakan Yae secara paralel di repo yang sama.
Deadline: **hari ini, siang**. Utamakan semua halaman lengkap dan bisa diklik di atas tampilan yang sempurna.

Sumber kebenaran: **PRD Gabungan** (`docs/PRD.md` kalau sudah ditaruh di repo; versi online https://claude.ai/code/artifact/8d06c96a-3976-4510-a8ef-bf9d3ac193df). Kalau dokumen ini dan PRD bertentangan soal API, **PRD yang menang**.

## Batas wilayah (wajib)

Repo tim: https://github.com/ilyas-r27/awan-security-project. Kamu bekerja di branch **`fe`**. Backend belum ada; Yae membangunnya paralel di branch **`be`** dengan struktur folder di `README.md`.

Karena repo masih kosong, kamu juga membuat **kerangka aplikasi** yang nanti dipakai bersama:
- `app/__init__.py`, `app/routes/__init__.py`
- `app/main.py` minimal: buat `FastAPI()`, mount `app/static` di `/static`, siapkan `Jinja2Templates("app/templates")`, include router `pages`. Tambahkan komentar `# BE: include router API di sini (auth, profile, packages, files, claims, stats)` di tempat Yae akan menambahkan routernya.
- `requirements.txt` berisi hanya yang dibutuhkan FE: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`. Yae menambahkan sisanya.
- `.env.example` kosong dengan komentar `# BE mengisi: MASTER_SECRET, JWT_SECRET`.

Selain kerangka itu, kamu **hanya** boleh membuat atau mengubah:
- `app/templates/**`, `app/static/**`
- `app/routes/pages.py` (route `GET` yang hanya me-render template, tanpa akses database)

**Jangan** membuat model, database, auth, endpoint API, atau modul enkripsi, walaupun halaman membutuhkannya. Semua data lewat mock (di bawah). Kalau butuh sesuatu dari backend, tulis di `docs/FE-NEEDS.md`.

Commit kecil per langkah dengan pesan yang jelas (mis. `fe: halaman brankas + mock packages`). Jangan push; saya yang push.

## Cara FE bicara dengan BE

- Semua data diambil lewat `fetch` dari JS ke endpoint API (cookie HttpOnly, `credentials: 'same-origin'`). Template hanya berisi kerangka halaman dan state loading.
- Satu modul **`app/static/js/api.js`** untuk semua panggilan:
  - `api.get(path)`, `api.post(path, body)`, `api.patch(path, body)`, `api.del(path)`, `api.upload(path, formData, onProgress)`
  - `upload` memakai `XMLHttpRequest` (fetch tidak punya progress upload).
  - Error: baca `{"detail": "..."}`, tampilkan ke user. Status **401** → redirect ke `/masuk?next=<halaman sekarang>` dengan pesan "Sesi berakhir, silakan masuk lagi".
- **Mode mock**: aktif kalau URL berisi `?mock=1` atau `localStorage.awanMock === '1'` (bungkus akses localStorage dengan try/catch). Di mode mock, `api.js` mengembalikan isi `app/static/mock/*.json` dengan jeda 300 ms, menyimulasikan progress upload, dan menyimpan perubahan (paket baru, klaim baru, status) di memori. **Bentuk JSON mock harus persis kontrak di bawah.** Saat BE siap, cukup matikan mock; tidak ada kode halaman yang berubah.
- Banner tipis di atas halaman "Mode mock aktif" kalau mock menyala, supaya tidak tertukar saat demo.
- Media: video `<video controls src="/files/{id}/download?alg=aes">`, foto KTP `<img src="/files/{id}/download?alg=aes">`, dokumen = link unduh. Di mode mock pakai `app/static/mock/sample.mp4` (buat video pendek dengan ffmpeg kalau tersedia, kalau tidak tampilkan placeholder) dan `app/static/mock/ktp-contoh.png` (gambar placeholder buatan sendiri bertuliskan "CONTOH", **bukan KTP asli**).

## Kontrak API (dari PRD, jangan diubah sepihak)

| Method | Path | Dipakai di halaman |
| --- | --- | --- |
| POST | `/auth/register` body `{username, password}` | Daftar |
| POST | `/auth/login` body `{username, password}` → bentuk `/auth/me` | Masuk |
| POST | `/auth/logout` | Menu akun |
| GET | `/auth/me` | Semua halaman (nama, peran, navigasi) |
| GET | `/profile?alg=aes` · PUT `/profile` body `{data:{...11 field}}` | Profil & KTP |
| GET | `/packages` · POST `/packages` body `{item_name, store, order_no}` · GET `/packages/{id}` | Brankas, Simpan unboxing, Detail paket |
| POST | `/files` multipart `file`, `category` (`id_card`/`document`/`video`), `package_id`? | Simpan unboxing, Profil |
| GET | `/files?category=` · GET `/files/{id}/download?alg=` · DELETE `/files/{id}` | Detail paket, Profil |
| GET | `/stats` | Statistik |
| GET | `/stores` | Ajukan klaim |
| POST | `/claims` body `{package_id, store_user_id, message}` → `{id, status}` | Ajukan klaim |
| GET | `/claims` · GET `/claims/{id}` · PATCH `/claims/{id}` body `{status, reply}` · POST `/claims/{id}/replies` body `{body}` | Detail paket, sisi toko |

Status klaim: `diajukan`, `ditinjau`, `diterima`, `ditolak`. Parameter `alg`: `aes` (default), `rc4`, `des`. File yang bukan haknya → 404.

### Bentuk JSON (salin ke `app/static/mock/`)

`auth-me.json`
```json
{"id": 1, "username": "dzaky", "role": "buyer", "store_name": null}
```
Akun toko di mock: `{"id": 21, "username": "elektra", "role": "store", "store_name": "Toko Elektra"}`. Mode mock bisa pindah peran lewat `?mock=1&role=store`.

`profile.json`
```json
{"algorithm": "aes", "decrypt_ms": 0.42, "updated_at": "2026-10-14T10:12:00+07:00",
 "data": {"full_name": "Dzaky A.", "nik": "3578xxxxxxxxxxxx", "birth_date": "2004-05-12", "gender": "Laki-laki",
          "nationality": "WNI", "marital_status": "Belum kawin", "address": "Jl. Contoh No. 12, Surabaya",
          "phone": "0812xxxxxxxx", "bank_account": "BCA 1234xxxxxx", "religion": null, "health_notes": null},
 "id_card_file_id": 7}
```

`packages.json`
```json
{"items": [{"id": 3, "item_name": "Monitor 24 inci", "store": "Toko Elektra", "order_no": "INV/2026/10/0412",
            "created_at": "2026-10-11T16:45:00+07:00", "video_file_id": 12, "document_count": 2, "total_size_bytes": 190840112}]}
```
Tambahkan 2–3 paket lagi (mis. Sepatu lari ukuran 42 / Sportiva, Kabel data USB-C / Toko Elektra), satu tanpa dokumen.

`package-3.json` (bentuk `GET /packages/{id}`)
```json
{"id": 3, "item_name": "Monitor 24 inci", "store": "Toko Elektra", "order_no": "INV/2026/10/0412", "created_at": "2026-10-11T16:45:00+07:00",
 "files": [
  {"id": 12, "package_id": 3, "category": "video", "name": "unboxing-monitor.mp4", "mime_type": "video/mp4", "size_bytes": 190601216, "created_at": "2026-10-11T16:45:00+07:00", "algorithms": ["aes","rc4","des"]},
  {"id": 13, "package_id": 3, "category": "document", "name": "invoice-elektra.pdf", "mime_type": "application/pdf", "size_bytes": 2888, "created_at": "2026-10-11T16:46:00+07:00", "algorithms": ["aes","rc4","des"]}],
 "claim": {"id": 5, "status": "ditinjau"}}
```
`claim` bernilai `null` kalau belum pernah diajukan.

`files.json` (bentuk `GET /files`, satu objek file sama seperti di atas): `{"items": [ ... ]}`

`stats.json`
```json
{"per_algorithm": [
  {"algorithm": "aes", "avg_enc_ms_per_mb": 4.1, "avg_dec_ms_per_mb": 3.9, "total_cipher_bytes": 191004672},
  {"algorithm": "rc4", "avg_enc_ms_per_mb": 2.7, "avg_dec_ms_per_mb": 2.6, "total_cipher_bytes": 190601216},
  {"algorithm": "des", "avg_enc_ms_per_mb": 21.8, "avg_dec_ms_per_mb": 21.2, "total_cipher_bytes": 191004680}],
 "per_category": [{"category": "video", "algorithm": "aes", "avg_enc_ms_per_mb": 4.0}]}
```
Angka mock hanya ilustrasi; halaman Statistik di mode mock menampilkan label "Data contoh".

`stores.json`
```json
{"items": [{"id": 21, "store_name": "Toko Elektra"}, {"id": 22, "store_name": "Sportiva"}]}
```

`claims.json` (bentuk `GET /claims`)
```json
{"items": [{"id": 5, "package_id": 3, "item_name": "Monitor 24 inci", "order_no": "INV/2026/10/0412", "buyer_name": "Dzaky A.",
            "store_name": "Toko Elektra", "status": "ditinjau", "video_file_id": 12, "created_at": "2026-10-12T14:20:00+07:00"}]}
```

`claim-5.json` (bentuk `GET /claims/{id}` dan response `PATCH`)
```json
{"id": 5, "status": "ditinjau", "message": "Layar retak di pojok kanan bawah", "created_at": "2026-10-12T14:20:00+07:00",
 "package": {"id": 3, "item_name": "Monitor 24 inci", "order_no": "INV/2026/10/0412"},
 "buyer": {"name": "Dzaky A.", "ktp_verified": true},
 "store": {"id": 21, "store_name": "Toko Elektra"},
 "files": [{"id": 12, "category": "video", "name": "unboxing-monitor.mp4", "mime_type": "video/mp4", "size_bytes": 190601216}],
 "replies": [{"id": 1, "author_role": "store", "author_name": "Toko Elektra", "body": "Video sudah kami terima, kami cek ke kurir dulu.", "created_at": "2026-10-13T09:05:00+07:00"}]}
```

## Halaman

Route halaman di `pages.py` (semua `GET`, hanya render template). Halaman pembeli dan toko mengecek `/auth/me` di JS: belum login → `/masuk`; peran salah → arahkan ke beranda perannya.

| Route | Halaman | Peran | Isi utama |
| --- | --- | --- | --- |
| `/masuk` | Masuk | publik | Kiri panel gradasi langit + awan + maskot + "Bukti unboxing kamu, terkunci sampai dibutuhkan." Kanan form username/password, tombol Masuk, link Daftar. Pesan error di atas form tanpa menyebut field mana yang salah |
| `/daftar` | Daftar | publik | Username, password, konfirmasi password. Catatan "Datamu akan dienkripsi". Sukses → masuk otomatis → `/profil?baru=1` |
| `/brankas` | Brankas saya | pembeli | Stat tile: PAKET, DOKUMEN, UKURAN TERENKRIPSI, ALGORITMA (`AES · RC4 · DES`). Tabel paket: thumbnail gradasi + ikon play, nama barang, no. pesanan (mono), toko, tanggal, jumlah dokumen, badge status klaim kalau ada, link Lihat. Tombol utama **+ Simpan unboxing**. Empty state: maskot + "Belum ada unboxing tersimpan" |
| `/unboxing/baru` | Simpan unboxing | pembeli | Panel Video: drop zone + pratinjau video lokal + nama/ukuran. Panel Info paket (baris label/kontrol): nama barang, toko (teks), no. pesanan. Panel Dokumen: tambah PDF/DOC/DOCX/XLS/XLSX (boleh banyak). Footer Batal · **Simpan ke brankas**. Urutan: `POST /packages` → `POST /files` video → `POST /files` tiap dokumen, progress per file, lalu toast "Tersimpan dan terenkripsi" → `/paket/{id}`. Validasi di klien: video ≤ 100 MB (mp4/mkv/mov), dokumen ≤ 20 MB |
| `/paket/{id}` | Detail paket | pembeli | Kiri: player video, panel Dokumen (ikon jenis, nama, ukuran mono, Unduh, Hapus dengan dialog konfirmasi). Kanan: panel Klaim (belum ada → tombol **Ajukan klaim**; sudah ada → status timeline + percakapan + kotak balas). Panel **Mode demo** yang bisa dilipat: pilih AES / RC4 / DES untuk pemutar dan tombol unduh, dengan catatan "Ketiganya menghasilkan file yang sama" |
| `/paket/{id}/klaim` | Ajukan klaim | pembeli | Alur fokus tanpa rail. Kotak pemberitahuan di atas: "Tenang, toko hanya melihat video dan dokumen paket ini. Tidak ada yang terkirim sebelum kamu menekan Kirim." Pilih toko (`GET /stores`), tulis keluhan, ringkasan file yang akan dibuka toko (kartu kecil per file), panel hijau "NIK, nomor HP, dan rekeningmu tidak ikut dibagikan." Tombol Kembali · **Kirim ke {toko}** → `POST /claims` → kembali ke `/paket/{id}` |
| `/profil` | Profil & KTP | pembeli | Sidebar sub-menu (DATA PRIBADI · Identitas · Foto KTP). Panel 11 field (label kiri, input kanan); agama dan riwayat kesehatan bertanda "Opsional, boleh dikosongkan". NIK dan rekening disamarkan dengan tombol tampilkan. Panel Foto KTP: pratinjau + ganti (`POST /files` category `id_card`, ≤ 5 MB JPG/PNG). Footer Batal · Simpan (`PUT /profile`). Mode demo: dropdown algoritma untuk `GET /profile?alg=` + tampilkan `decrypt_ms` |
| `/statistik` | Statistik enkripsi | pembeli | Tabel + grafik batang (Chart.js) waktu enkripsi/dekripsi per MB dan ukuran ciphertext per algoritma, dari `GET /stats`. Satu kalimat penjelasan: "RC4 dan DES dipakai karena syarat tugas; keduanya sudah tidak dianggap aman." |
| `/toko` | Klaim masuk | toko | Chip filter status, grid kartu klaim (thumbnail, badge status, nama barang, no. pesanan mono, nama pembeli, tombol Tinjau). Empty state "Belum ada klaim masuk" |
| `/toko/klaim/{id}` | Tinjau klaim | toko | Player video besar, panel Dokumen (Unduh), panel Pembeli (nama + "KTP terverifikasi", **tanpa** NIK/HP/rekening), panel Keputusan (radio Terima / Tolak / Minta bukti tambahan → `diterima` / `ditolak` / `ditinjau`) + balasan, footer **Simpan keputusan** (`PATCH /claims/{id}`). Percakapan di bawah |

Navigasi:
- **Pembeli** (icon rail kiri): Brankas · Simpan unboxing · Profil & KTP · Statistik. Top bar: logo + `Awan / {username}`, menu akun dengan Keluar.
- **Toko** (tanpa rail, top bar saja): logo + label kapital "TOKO" + nama toko, tab Klaim masuk, menu akun.

## State yang wajib ada

| Situasi | Tampilan |
| --- | --- |
| Memuat data | Skeleton abu di posisi konten (bukan spinner di tengah layar) |
| Daftar kosong | Maskot + kalimat + tombol aksi utama |
| Upload berjalan | Progress bar per file, tombol simpan nonaktif, peringatan kalau user mencoba menutup halaman |
| Sukses simpan | Toast kanan bawah, 3 detik |
| Error validasi / dari server | Pesan merah kecil di bawah field atau di atas form, isi dari `detail` |
| Sesi habis (401) | Redirect ke `/masuk` dengan pesan |
| Hapus | Dialog konfirmasi |
| 404 | Halaman "Data tidak ditemukan" dengan tombol kembali ke beranda peran |

## Desain: baseline UI Supabase, tema terang, warna langit

Acuan struktur: dashboard **Supabase** di Figma, halaman "Idea Dump":
https://www.figma.com/design/hE8Oo6WJlXG3gXBmG1mVXo/Brankas-Unboxing-%E2%80%94-Foundations?node-id=19-1629
Kalau Figma MCP tersedia, buka frame acuannya untuk mengukur. Brankas → `19:1630` (Project home), Profil & Simpan unboxing → `19:4120` (Organization Settings), Klaim masuk toko → `19:8091` (Organizations), tabel/badge → `19:4658`, `19:7301`. Supabase gelap dan hijau; kita **terang** dan **biru langit**. Jangan meniru logo atau nama Supabase.

**Tipografi** (Google Fonts: Inter 400/500/600, Manrope 600, Source Code Pro 400/500)
| Peran | Font | Ukuran / line-height |
| --- | --- | --- |
| Judul halaman | Manrope SemiBold | 22 / 29, tracking −0.55px |
| Judul bagian | Manrope SemiBold | 18 / 25 |
| Judul sidebar | Manrope SemiBold | 16 / 25 |
| Teks UI | Inter Medium | 13 / 19.5 |
| Tombol, link kecil | Inter Medium | 12 / 16 |
| Penjelasan | Inter Regular | 13 / 19.5, warna muted |
| Label | Source Code Pro Medium | 11 / 16, KAPITAL, tracking +0.06em |
| Data teknis | Source Code Pro Regular | 12 / 16 |
| Nilai stat | Inter Medium | 15 / 22 |

**Layout**: top bar 48 px berborder bawah; icon rail 48 px (ikon Lucide 18 px dalam kotak 32 px, aktif berlatar `--surface-hover`, tooltip nama); sidebar sub-menu 256 px hanya di Profil; konten maks. 1120 px di tengah, padding atas 48 px; antarbagian 40 px; kelipatan 4 untuk jarak.
**Panel**: putih, border 1 px, radius 8. Panel form = baris label kiri (±45%) dan kontrol kanan, pembatas 1 px, footer kanan Batal + Simpan.
**Stat tile**: kotak ikon 40×40 radius 8 berborder + label mono kapital + nilai 15 px.
**Tombol**: tinggi 26 (default) atau 32 (besar), radius 6, Inter Medium 12. Primary `--brand-600` teks putih border `--brand-500`; default putih border `--border-strong`; ghost transparan; bahaya teks `--bad`.
**Input**: tinggi 32, radius 6, latar `--surface-input`, border `--border-strong`, fokus ring 2 px `--brand-200`.
**Badge**: pill tinggi 18, Source Code Pro 10 kapital. DIAJUKAN (brand), DITINJAU (warn), DITERIMA (ok), DITOLAK (bad).
**Ikon**: Lucide via CDN `https://unpkg.com/lucide@0.469.0/dist/umd/lucide.min.js`, stroke 1.5.
**Grafik**: Chart.js `https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js`, batang warna `--brand-600`, `--brand-400`, `--brand-200` untuk AES/RC4/DES.
**Tailwind** boleh via CDN untuk utilitas, tapi token warna dan font wajib dari `app/static/css/app.css`:

```css
:root{
  --brand-700:#003A93; --brand-600:#004CBC; --brand-500:#1A66C6; --brand-400:#3986D6;
  --brand-300:#5BACE4; --brand-200:#74C7F1; --brand-100:#A9DCF9; --brand-50:#DEF1FF; --brand-25:#EEF8FF;
  --bg:#F7F9FB; --surface:#FFFFFF; --surface-hover:#EFF3F7; --surface-input:#FAFBFC;
  --border:#E3E8EE; --border-strong:#CBD3DC;
  --ink:#11181F; --ink-2:#3C4651; --muted:#6B7684;
  --ok:#1A7F4B; --ok-soft:#E3F4EA; --warn:#A15C00; --warn-soft:#FFF1D6; --bad:#C0392B; --bad-soft:#FDE6E3;
  --radius-sm:6px; --radius-md:8px; --radius-pill:999px;
  --sky:linear-gradient(180deg,#004CBC 0%,#1A66C6 30%,#5BACE4 60%,#A9DCF9 80%,#E9FDFE 100%);
}
```
- Aplikasi datar seperti Supabase. Gradasi `--sky` hanya di panel kiri Masuk/Daftar dan thumbnail video; boleh 2–3 awan putih lembut (elips blur).
- Maskot `app/static/img/logo.svg` (sudah disediakan) di top bar, halaman masuk, dan empty state.
- Bahasa Indonesia santai dan menenangkan. Tombol 1–3 kata diawali kata kerja. Judul maks. 6 kata.

## Komponen Jinja (buat dulu, pakai di semua halaman)

`app/templates/components/`: `button`, `input`, `select`, `textarea`, `badge`, `panel` (dengan slot header/footer), `form_row`, `stat_tile`, `nav_rail`, `top_bar`, `empty_state`, `toast` (JS), `dialog` (JS), `file_row`, `skeleton`. `base.html` memuat font, `app.css`, Lucide, `api.js`, dan `app.js` (toast, dialog, guard login).

## Urutan kerja

1. `app.css` (token + font), `base.html`, komponen, `api.js` dengan mode mock + semua file mock, `pages.py`
2. Masuk, Daftar
3. Brankas, Simpan unboxing (dengan upload + progress)
4. Detail paket, Ajukan klaim
5. Profil & KTP
6. Sisi toko: Klaim masuk, Tinjau klaim
7. Statistik
8. `docs/FE-NOTES.md`: cara menyalakan/mematikan mock, daftar halaman, dan apa yang butuh dicek bersama Yae saat sambung

Setelah tiap langkah, jalankan server dan buka halamannya dengan `?mock=1` di browser (Playwright boleh) untuk memastikan tampil dan bisa diklik. Bandingkan kepadatan, ukuran font, radius, dan border dengan frame Figma acuannya.

## Di luar scope

Logika backend apa pun, rekam kamera langsung, chat real-time, email, dark mode, tampilan mobile, deploy.
