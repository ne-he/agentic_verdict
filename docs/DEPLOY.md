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
> **GPU-nya tidak dipakai.** Beban kerja proyek ini murni CPU (pandas, scipy, duckdb)
> plus panggilan jaringan ke Gemini. Tidak ada fungsi yang didekorasi `@spaces.GPU`,
> jadi kuota GPU harian (5 menit untuk akun gratis) tidak pernah tersentuh. Pola yang
> sama sudah dipakai di Space `ne-he/phisguard-api`.
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
| [`space_app.py`](../space_app.py) | Entry point. Menaruh `backend/` di `sys.path`, set env setara Dockerfile, mount gradio ke FastAPI, jalankan uvicorn di 7860 |
| [`requirements.txt`](../requirements.txt) | Space install dari root; isinya cuma `-r backend/requirements.txt` supaya versi tidak kembar |
| [`packages.txt`](../packages.txt) | `libgomp1` (runtime OpenMP untuk scipy), pengganti `apt-get` di Dockerfile |

Entry point-nya **bukan** `app.py` dengan sengaja: backend punya package bernama `app`
(`backend/app/`), dan `app.py` di root akan menabraknya saat `import app.main`.

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
| `DATABASE_URL` | Secret | connection string Neon (langkah 1) |
| `ALLOWED_ORIGINS` | Variable | `https://<domain-vercel>` (diisi setelah langkah 3) |

`USE_DOCKER=false`, `GEMINI_MODEL`, dan `MPLCONFIGDIR` sudah di-`setdefault` di
`space_app.py`, jadi tidak perlu diisi. Kalau mau override, isi sebagai Variable dan
nilainya akan menang.

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
6. **Balik ke Settings Space**, set `ALLOWED_ORIGINS` = domain Vercel itu → Space
   otomatis restart supaya CORS lolos.

---

## 4) Urutan dan verifikasi

1. Neon → dapat `DATABASE_URL`.
2. HF Space (buat + push + secrets) → dapat URL → cek `/health`.
3. Vercel frontend (`NEXT_PUBLIC_API_URL` = URL Space) → dapat domain.
4. Space: set `ALLOWED_ORIGINS` = domain Vercel → restart.
5. Buka domain Vercel → tanya 1 pertanyaan → pastikan SSE mengalir dan jawaban +
   verification muncul.

Langkah 4 tidak bisa ditukar dengan langkah 3. Sebelum domain Vercel ada, tidak ada nilai
yang bisa diisikan ke `ALLOWED_ORIGINS`, dan selama itu kosong browser akan menolak semua
request lintas origin.

### Checklist env (ringkas)
- **HF Space:** `GEMINI_API_KEY` · `DATABASE_URL` · `ALLOWED_ORIGINS`
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
- **Belum pernah dibangun di Linux.** `requirements.txt` belum pernah di-`pip install`
  bersih di Python 3.12 Linux dari mesin ini (tidak ada Docker di sini). Kalau build
  pertama gagal, kemungkinan besar di resolusi versi scipy/pandas: ambil log build dari
  tab **Logs** Space.
