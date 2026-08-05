# DEPLOY VERDICT ANALYST

Backend di **Render** (Free Web Service, Docker, tanpa kartu kredit), frontend di
**Vercel**, DB **Neon** (Postgres). File ini = config + langkah. **JANGAN commit secret
apa pun**: semua key diisi di Environment Render / Vercel.

> **Kenapa bukan Hugging Face Spaces lagi.** Sejak sekitar 8 Juli 2026, HF memindahkan
> Docker Space ke belakang paywall: pesan errornya berbunyi bahwa Static Space gratis
> untuk semua orang, tapi hosting Gradio dan Docker Space di cpu-basic butuh langganan
> PRO. Tidak ada pengumuman resmi. `README.md` masih menyimpan frontmatter `sdk: docker`
> kalau suatu saat kebijakan itu dibalik, tapi untuk sekarang Render yang dipakai.

> Catatan sandbox: Render bukan Docker-in-Docker, jadi backend jalan dengan
> `USE_DOCKER=false`, artinya kode agen dieksekusi via **subprocess** (resource limit
> POSIX + timeout). Isolasi penuh (Docker `--network none`) hanya saat self-host atau VPS
> yang mendukung Docker. Ini sama persis dengan kondisi di HF dulu, tidak ada yang turun.

---

## Arsitektur deploy

```
Vercel (Next.js)  ──HTTPS+SSE──►  Render (FastAPI, Docker)  ──►  Neon Postgres
  NEXT_PUBLIC_API_URL                ALLOWED_ORIGINS               DATABASE_URL
                                     USE_DOCKER=false
                                     GEMINI_API_KEY
```

---

## 1) Database: Neon

Filesystem Render **ephemeral** (hilang tiap restart/redeploy), jadi run history butuh DB
di luar. Pakai Neon, **bukan** Postgres bawaan Render: **database Postgres gratis Render
kadaluarsa 30 hari setelah dibuat**, dan portofolio yang mati sendiri sebulan lagi itu
lebih buruk daripada tidak deploy sama sekali. Neon free tier tidak punya batas waktu itu.

1. Buat akun di [neon.tech](https://neon.tech) → New Project (Postgres, free tier).
2. Salin **connection string**: `postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`
3. Simpan untuk env `DATABASE_URL` di Render (langkah 2).

Tabel dibuat **otomatis saat startup** (`create_tables()` di `app/main.py` lifespan,
idempotent, jalan untuk SQLite maupun Postgres). Tidak perlu migrasi manual.

> Tanpa Neon: kosongkan `DATABASE_URL` → app pakai SQLite lokal (jalan, tapi data hilang
> tiap service restart).

---

## 2) Backend: Render

Konfigurasi sudah ada di repo: [`Dockerfile`](../Dockerfile) di root. `CMD`-nya memakai
`${PORT:-7860}`, jadi port yang disuntik Render dipakai otomatis dan `docker run` lokal
tetap jatuh ke 7860.

### a. Buat service
1. [render.com](https://render.com) → **Get Started** → login pakai GitHub. Tidak perlu
   kartu kredit.
2. **New → Web Service** → **Build and deploy from a Git repository** → pilih repo
   `ne-he/agentic_verdict`. Kalau reponya belum kelihatan, klik **Configure account** dan
   beri Render akses.

### b. Setelan
| Kolom | Nilai |
|---|---|
| Name | `verdict-backend` |
| Language / Runtime | **Docker** (terdeteksi otomatis dari `Dockerfile` di root) |
| Branch | `main` |
| Instance Type | **Free** |
| Health Check Path | `/health` |

Root Directory dikosongkan, Dockerfile-nya di root repo.

### c. Environment Variables
| Key | Nilai | Rahasia? |
|---|---|---|
| `GEMINI_API_KEY` | key dari aistudio.google.com | ya |
| `DATABASE_URL` | connection string Neon (langkah 1) | ya |
| `ALLOWED_ORIGINS` | `https://<domain-vercel>` (diisi setelah langkah 3) | tidak |

`USE_DOCKER=false` dan `GEMINI_MODEL` sudah di-set default di Dockerfile, boleh
di-override di sini.

### d. Deploy dan verifikasi
Klik **Create Web Service**. Build pertama 6 sampai 12 menit (scipy dan statsmodels lama
di-install). Status **Live** → cek
`https://verdict-backend-xxxx.onrender.com/health` → `{"status":"ok"}`.

---

## 3) Frontend: Vercel

1. Vercel → **Add New → Project** → import repo `ne-he/agentic_verdict`.
2. **Root Directory:** `frontend`
3. Framework: **Next.js** (auto-detect). Build/Output default.
4. **Environment Variables:**

| Key | Nilai | Catatan |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://verdict-backend-xxxx.onrender.com` | URL backend Render, TANPA garis miring di akhir |

5. Deploy → dapat domain `https://agentic-verdict-xxxx.vercel.app`.
6. **Balik ke Render** (Environment), set `ALLOWED_ORIGINS` = domain Vercel itu → service
   otomatis restart supaya CORS lolos.

---

## 4) Urutan dan verifikasi

1. Neon → dapat `DATABASE_URL`.
2. Render backend (push kode) → dapat URL → cek `/health`.
3. Vercel frontend (`NEXT_PUBLIC_API_URL` = URL Render) → dapat domain.
4. Render: set `ALLOWED_ORIGINS` = domain Vercel → restart.
5. Buka domain Vercel → tanya 1 pertanyaan → pastikan SSE mengalir dan jawaban +
   verification muncul.

Langkah 4 tidak bisa ditukar dengan langkah 3. Sebelum domain Vercel ada, tidak ada nilai
yang bisa diisikan ke `ALLOWED_ORIGINS`, dan selama itu kosong browser akan menolak semua
request lintas origin.

### Checklist env (ringkas)
- **Render:** `GEMINI_API_KEY` · `DATABASE_URL` · `ALLOWED_ORIGINS`
- **Vercel:** `NEXT_PUBLIC_API_URL`

---

## 5) Anggaran RAM: sekitar 320 MB dari 512 MB

Instance gratis Render memberi **512 MB RAM dan 0.1 CPU**. Backend ini memakai dua proses
saat menganalisis: FastAPI induk, plus satu subprocess sandbox yang menjalankan kode agen.
Hasil ukur di mesin ini:

| Proses | RSS |
|---|---|
| `app.main` (FastAPI + SQLAlchemy + Gemini client) | 151,4 MB |
| induk setelah pandas + duckdb + matplotlib ikut termuat | 169,7 MB |
| subprocess sandbox (perkiraan, pandas + matplotlib fresh) | ~150 MB |
| **Puncak saat satu analisis berjalan** | **~320 MB** |

Muat dengan sisa sekitar 190 MB. Yang perlu diwaspadai: **dua analisis berbarengan**
menambah satu subprocess lagi dan bisa menembus batas. Untuk demo satu orang ini tidak
masalah, tapi kalau nanti dipakai beberapa orang sekaligus, itu titik yang pertama patah.
Gejalanya `Exited with status 137` di log Render, yaitu SIGKILL dari kernel, bukan bug
kode.

---

## 6) Catatan dan batasan

- **Service gratis tidur setelah 15 menit tanpa traffic**, bangunnya sekitar satu menit.
  Buka linknya sendiri semenit sebelum meeting, jangan mengirim link lalu menyuruh orang
  klik saat itu juga.
- **750 jam instance per bulan per workspace, dibagi semua service.** Kalau PULSE juga
  dideploy di workspace Render yang sama, keduanya berbagi kuota ini. Aman selama
  keduanya tidur waktu tidak dipakai.
- **Chart di subprocess mode:** PNG disimpan ke `ARTIFACTS_ROOT` dan dilayani
  `GET /artifacts/...`. Filesystem Render ephemeral, jadi chart hidup selama instance
  hidup. Cukup untuk demo per sesi, hilang setelah service tidur.
- **Keamanan subprocess di bawah Docker:** subprocess punya akses network. Untuk isolasi
  penuh (`--network none`, whitelist lib), self-host di VPS yang mendukung Docker lalu set
  `USE_DOCKER=true` + build image `backend/app/sandbox/image`.
- **Secret:** tidak ada key di repo. `.env` dan `.env.local` di-gitignore; secret diisi di
  Environment Render, bukan di file.
