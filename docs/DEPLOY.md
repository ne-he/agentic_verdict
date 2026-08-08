# DEPLOY VERDICT ANALYST

Backend di **Hugging Face Space** (SDK `gradio`, hardware **ZeroGPU**, gratis, tanpa
kartu kredit), frontend di **Vercel**, DB **Neon** (Postgres). File ini = config +
langkah. **JANGAN commit secret apa pun**: semua key diisi di Settings Space / Vercel.

> **Kenapa SDK gradio + ZeroGPU, bukan Docker.** Sejak sekitar 8 Juli 2026 pembuatan
> **Docker Space** dan Gradio Space di hardware `cpu-basic` ditaruh di belakang paywall
> PRO. Yang masih gratis: akun personal gratis boleh menghosting **2 ZeroGPU Space**
> (syarat email terverifikasi dan umur akun di atas 30 hari), dan ZeroGPU **hanya
> kompatibel dengan SDK gradio**. Jadi jalurnya gradio, bukan pilihan estetika.
>
> **Dua aturan ZeroGPU yang menentukan bentuk `space_app.py`.** Keduanya bikin Space
> mati waktu dilanggar, dan keduanya sudah dibayar mahal di Space `ne-he/phisguard-api`:
>
> 1. App WAJIB dinyalakan lewat `.launch()` Gradio, **bukan `uvicorn.run()` manual**.
>    Uvicorn manual bikin ZeroGPU tidak pernah aktif.
> 2. WAJIB ada minimal satu fungsi ber-`@spaces.GPU` yang ter-register, kalau tidak
>    runtime menolak start dengan "No @spaces.GPU function detected".
>
> Jembatannya `gradio.Server`, subclass FastAPI resmi milik Gradio yang boleh menerima
> route sendiri tapi tetap dinyalakan lewat `.launch()`. Jadi rute API tetap di root
> (`/health`, `/analyze`, ...) dan ZeroGPU tetap senang.
>
> **GPU-nya tetap tidak dipakai untuk kerja beneran.** Beban proyek ini murni CPU
> (pandas, scipy, duckdb) plus panggilan jaringan ke Gemini. Fungsi `gpu_probe()` cuma
> tiket masuk syarat nomor 2 dan tidak pernah dipanggil frontend, jadi kuota GPU harian
> (5 menit untuk akun gratis) praktis tidak tersentuh.
>
> [`Dockerfile`](../Dockerfile) sengaja **dipertahankan**, tidak dihapus. Kalau
> kebijakan HF berubah atau nanti pindah ke VPS, jalur Docker tinggal dipakai lagi
> apa adanya.

> Catatan sandbox: Space bukan Docker-in-Docker, jadi backend jalan dengan
> `USE_DOCKER=false`, artinya kode agen dieksekusi via **subprocess** (resource limit
> POSIX + timeout). Isolasi penuh (Docker `--network none`) hanya saat self-host atau
> VPS yang mendukung Docker.

---

## Arsitektur deploy

```
Vercel (Next.js)  ──HTTPS+SSE──►  HF Space (FastAPI, gradio SDK)  ──►  Neon Postgres
  NEXT_PUBLIC_API_URL                ALLOWED_ORIGINS                    DATABASE_URL
                                     GEMINI_API_KEY
```

### File yang membuat Space ini jalan

| File | Peran |
|---|---|
| [`README.md`](../README.md) | Frontmatter: `sdk: gradio`, `sdk_version`, `python_version`, `app_file: space_app.py` |
| [`space_app.py`](../space_app.py) | Entry point. Menaruh `backend/` di `sys.path`, set env setara Dockerfile, pasang router API ke `gradio.Server`, sediakan `gpu_probe()`, lalu `.launch()` di 7860 |
| [`requirements.txt`](../requirements.txt) | Daftar dependensi untuk Space. Isinya **kembar** dengan `backend/requirements.txt`, lihat catatan di bawah |
| [`packages.txt`](../packages.txt) | `libgomp1` (runtime OpenMP untuk scipy), pengganti `apt-get` di Dockerfile |

Entry point-nya **bukan** `app.py` dengan sengaja: backend punya package bernama `app`
(`backend/app/`), dan `app.py` di root akan menabraknya saat `import app.main`.

**Kenapa `requirements.txt` di root isinya kembar, bukan `-r backend/requirements.txt`.**
Pada tahap pip install, HF tidak menyalin isi repo. Yang dilakukan cuma me-mount satu
file itu sendirian ke `/tmp/requirements.txt`, jadi `-r backend/requirements.txt`
di-resolve jadi `/tmp/backend/requirements.txt` yang tidak ada dan build mati dengan
`Could not open requirements file`. Duplikasinya dijaga
[`backend/tests/test_requirements_sync.py`](../backend/tests/test_requirements_sync.py):
kalau kedua file beda, test merah. Paritas rute Space vs `app.main` dijaga
[`backend/tests/test_space_app.py`](../backend/tests/test_space_app.py).

---

## 1) Database: Neon

Filesystem Space **ephemeral** (hilang tiap restart/rebuild), jadi run history butuh DB
di luar.

1. Buat akun di [neon.tech](https://neon.tech) → New Project (Postgres, free tier).
2. Salin **connection string**: `postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`
3. Simpan untuk secret `DATABASE_URL` di Space (langkah 2c).

Tabel dibuat **otomatis saat startup** (`create_tables()` di `app/main.py` lifespan,
idempotent, jalan untuk SQLite maupun Postgres). Tidak perlu migrasi manual.

> Tanpa Neon: kosongkan `DATABASE_URL` → app pakai SQLite lokal (jalan, tapi data hilang
> tiap Space restart).

---

## 2) Backend: Hugging Face Space

### a. Buat Space
1. [huggingface.co/new-space](https://huggingface.co/new-space)
2. **Owner** `ne-he` · **Space name** `verdict-analyst` · **License** bebas
3. **SDK: Gradio** (jangan Docker, jangan Static)
4. **Space hardware: `ZeroGPU`** ← ini kuncinya, bukan `CPU basic`
5. **Public**
6. Create Space

> Kalau opsi ZeroGPU tidak muncul atau ditolak: cek email akun sudah terverifikasi.
> Batasnya 2 ZeroGPU Space per akun gratis, dan `ne-he/phisguard-api` sudah memakai 1,
> jadi ini slot terakhir.

### b. Kirim kode
Space adalah repo git sendiri. Tambahkan sebagai remote kedua di repo lokal:

```bash
git remote add space https://huggingface.co/spaces/ne-he/verdict-analyst
git push space main
```

Saat diminta kredensial: username `ne-he`, password = **Access Token** dari
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) dengan izin
**write**, bukan password akun.

Yang ikut ter-push cuma 153 file terlacak (~1,8 MB). Folder referensi `agentic_analyst/`
dan `verdict/` tidak terlacak git, jadi tidak ikut. `frontend/` ikut tapi tidak
mengganggu: Space hanya menjalankan `app_file`.

### c. Secrets dan Variables
Settings Space → **Variables and secrets**:

| Key | Jenis | Nilai |
|---|---|---|
| `GEMINI_API_KEY` | Secret | key dari aistudio.google.com |
| `DATABASE_URL` | Secret | connection string Neon (langkah 1). Boleh dikosongkan dulu, lihat catatan di bawah |

`USE_DOCKER=false`, `GEMINI_MODEL`, dan `MPLCONFIGDIR` sudah di-`setdefault` di
`space_app.py`, jadi tidak perlu diisi. Kalau mau override, isi sebagai Variable dan
nilainya akan menang.

> **`ALLOWED_ORIGINS` tidak dipakai di Space, jadi jangan diisi.** Gradio memasang CORS
> sendiri saat `.launch()`, dan `is_valid_origin`-nya memantulkan Origin apa pun selama
> Host server bukan localhost. Di `*.hf.space` syarat itu otomatis terpenuhi, jadi
> domain Vercel mana pun lolos tanpa dikonfigurasi. Menambah `CORSMiddleware` sendiri di
> `space_app.py` justru merusak: `Access-Control-Allow-Origin` jadi dobel dan browser
> menolak respons yang punya header itu lebih dari satu. `ALLOWED_ORIGINS` tetap
> berlaku kalau self-host lewat [`Dockerfile`](../Dockerfile), karena di sana yang
> jalan `app.main` langsung dengan CORSMiddleware-nya sendiri.

> **Tanpa `DATABASE_URL` Space tetap jalan**, memakai SQLite di dalam Space. Semua fitur
> hidup, tapi filesystem Space ephemeral: riwayat run hilang tiap Space rebuild atau
> bangun dari tidur. Boleh deploy dulu tanpa Neon, isi belakangan, Space restart sendiri.

### d. Verifikasi
Build pertama 6 sampai 12 menit (scipy lama di-install). Status **Running** → cek:

- `https://ne-he-verdict-analyst.hf.space/health` → `{"status":"ok"}`
- `https://ne-he-verdict-analyst.hf.space/space` → halaman status gradio
- `https://ne-he-verdict-analyst.hf.space/docs` → OpenAPI

URL inilah yang dipakai sebagai `NEXT_PUBLIC_API_URL`, **bukan** URL
`huggingface.co/spaces/...` (itu halaman pembungkus, bukan endpoint).

---

## 3) Frontend: Vercel

1. Vercel → **Add New → Project** → import repo GitHub `ne-he/agentic_verdict`.
2. **Root Directory:** `frontend`
3. Framework: **Next.js** (auto-detect). Build/Output default.
4. **Environment Variables:**

| Key | Nilai | Catatan |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://ne-he-verdict-analyst.hf.space` | URL Space, TANPA garis miring di akhir |

5. Deploy → dapat domain `https://agentic-verdict-xxxx.vercel.app`.

Tidak ada langkah balik ke Space setelah ini: CORS ditangani gradio dan sudah menerima
domain Vercel mana pun (lihat catatan `ALLOWED_ORIGINS` di langkah 2c).

---

## 4) Urutan dan verifikasi

1. HF Space (buat + push + `GEMINI_API_KEY`) → dapat URL → cek `/health`.
2. Vercel frontend (`NEXT_PUBLIC_API_URL` = URL Space) → dapat domain.
3. Buka domain Vercel → tanya 1 pertanyaan → pastikan SSE mengalir dan jawaban +
   verification muncul.
4. Neon (opsional, kapan saja) → isi `DATABASE_URL` di Space supaya riwayat run awet.

Neon sengaja ditaruh terakhir: tanpa itu app tetap jalan dengan SQLite, jadi ia bukan
penghalang untuk melihat sistemnya hidup end to end.

### Checklist env (ringkas)
- **HF Space:** `GEMINI_API_KEY` (wajib) · `DATABASE_URL` (opsional, biar riwayat awet)
- **Vercel:** `NEXT_PUBLIC_API_URL`

---

## 5) Anggaran RAM

Backend ini memakai dua proses saat menganalisis: FastAPI induk, plus satu subprocess
sandbox yang menjalankan kode agen. Hasil ukur di mesin ini:

| Proses | RSS |
|---|---|
| `app.main` (FastAPI + SQLAlchemy + Gemini client) | 151,4 MB |
| induk setelah pandas + duckdb + matplotlib ikut termuat | 169,7 MB |
| subprocess sandbox (perkiraan, pandas + matplotlib fresh) | ~150 MB |
| **Puncak saat satu analisis berjalan** | **~320 MB** |

Angka ini dulu menakutkan waktu targetnya instance 512 MB. Di ZeroGPU alokasi CPU/RAM-nya
dinamis dan jauh di atas itu, jadi risiko `Exited with status 137` (SIGKILL karena dua
analisis berbarengan) praktis hilang. Tabelnya tetap disimpan sebagai patokan kalau nanti
pindah ke host berkuota ketat.

---

## 6) Catatan dan batasan

- **Space gratis tidur setelah 48 jam tanpa traffic.** Jauh lebih longgar daripada
  15 menit ala Render, tapi tetap: buka linknya sendiri sebelum meeting.
- **Slot ZeroGPU habis setelah ini.** Kuotanya 2 per akun gratis, `phisguard-api` pakai 1
  dan Space ini pakai 1. Untuk PULSE nanti, jalurnya bukan ZeroGPU melainkan menimpa
  salah satu Docker Space lama (`addictV2`, `feature-store-mvp`, `nem_vision`) yang dibuat
  sebelum paywall dan masih boleh jalan.
- **Menumpang ZeroGPU untuk beban non-GPU itu wilayah abu-abu.** HF tidak melarangnya dan
  Space tetap sah, tapi kalau suatu saat aturannya diketatkan, Space ini dan `phisguard-api`
  kena bersamaan. Mitigasinya `Dockerfile` masih ada di repo.
- **Chart di subprocess mode:** PNG disimpan ke `ARTIFACTS_ROOT` dan dilayani
  `GET /artifacts/...`. Filesystem Space ephemeral, jadi chart hidup selama Space hidup.
- **Keamanan subprocess:** subprocess punya akses network. Untuk isolasi penuh
  (`--network none`, whitelist lib), self-host di VPS yang mendukung Docker lalu set
  `USE_DOCKER=true` + build image `backend/app/sandbox/image`.
- **Secret:** tidak ada key di repo. `.env` dan `.env.local` di-gitignore; secret diisi di
  Settings Space, bukan di file.
- **`fastapi` dan `pydantic` dinaikkan demi gradio.** HF memasang
  `gradio[oauth,mcp]==<sdk_version>` di perintah pip yang sama dengan
  `requirements.txt`, dan gradio 6.15+ menuntut `starlette>=1.0.1` (yang dikunci
  `<0.42` oleh fastapi 0.115) sementara extra `mcp` menuntut `pydantic>=2.11.10`.
  Karena itu pin backend naik: `fastapi 0.115.* → 0.141.*`, `pydantic 2.9.* → 2.12.*`.
  Seluruh test suite hijau di stack baru itu, jadi kenaikannya bukan taruhan.
  Alternatifnya menurunkan `sdk_version` ke gradio ≤5.27 (satu-satunya rentang yang
  masih cocok dengan pydantic 2.9), dan itu jauh lebih tua.
- **Log build ada di tab Logs Space.** Kalau build merah, itu sumber kebenarannya.
  Pesan yang sudah pernah muncul dan artinya:
  `Could not open requirements file: '/tmp/backend/requirements.txt'` berarti
  `requirements.txt` root memakai `-r` ke path repo (lihat §File di atas).
