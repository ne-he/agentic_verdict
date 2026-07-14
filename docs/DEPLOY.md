# DEPLOY — ANALYST

Backend di **Hugging Face Spaces** (Docker Space, gratis tanpa kartu), frontend di **Vercel**,
DB **Neon** (Postgres). File ini = config + langkah. **JANGAN commit secret apa pun** — semua key
diisi di Settings → Secrets HF / env Vercel.

> Catatan sandbox: HF Spaces bukan Docker-in-Docker, jadi backend jalan dengan `USE_DOCKER=false`
> → kode agen dieksekusi via **subprocess** (resource limit POSIX + timeout). Isolasi penuh
> (Docker `--network none`) hanya saat self-host / VPS yang mendukung Docker.

---

## Arsitektur deploy

```
Vercel (Next.js)  ──HTTPS+SSE──►  HF Spaces (FastAPI, Docker)  ──►  Neon Postgres
  NEXT_PUBLIC_API_URL                ALLOWED_ORIGINS                 DATABASE_URL
                                     USE_DOCKER=false
                                     GEMINI_API_KEY
```

---

## 1) Database — Neon (disarankan)

Filesystem HF Spaces **ephemeral** (hilang tiap restart/rebuild). Untuk run history persisten,
pakai Neon:

1. Buat akun di [neon.tech](https://neon.tech) → New Project (Postgres, free tier).
2. Salin **connection string**: `postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`
3. Simpan untuk secret `DATABASE_URL` di HF (langkah 2).

Tabel dibuat **otomatis saat startup** (`create_tables()` di `app/main.py` lifespan —
idempotent, jalan untuk SQLite maupun Postgres). Tidak perlu migrasi manual.

> Tanpa Neon: kosongkan `DATABASE_URL` → app pakai SQLite lokal (jalan, tapi data tidak persisten).

---

## 2) Backend — Hugging Face Spaces (Docker)

Konfigurasi sudah ada di repo: [`Dockerfile`](../Dockerfile) (root) + frontmatter di
[`README.md`](../README.md) (`sdk: docker`, `app_port: 7860`). HF build dari Dockerfile, app
listen di **port 7860**.

### a. Buat Space
1. [huggingface.co](https://huggingface.co) → login → **New → Space**.
2. Owner: akunmu. Space name: mis. `analyst-backend`. **SDK: Docker** → template **Blank**.
   Visibility: Public. Klik **Create Space** (repo Space masih kosong).

### b. Isi Secrets (Settings → Variables and secrets)
**Secrets** (rahasia):

| Key | Nilai |
|---|---|
| `GEMINI_API_KEY` | key dari aistudio.google.com |
| `DATABASE_URL` | connection string Neon (langkah 1) |

**Variables** (non-rahasia):

| Key | Nilai |
|---|---|
| `ALLOWED_ORIGINS` | `https://<domain-vercel>` (diisi setelah langkah 3) |

> `USE_DOCKER=false` & `GEMINI_MODEL` sudah di-set default di `Dockerfile` (boleh override di sini).

### c. Push kode ke Space
Space = repo git terpisah. Tambah sebagai remote lalu push (token write dipakai sebagai password,
atau jalankan `huggingface-cli login` dulu supaya kredensial tersimpan):

```bash
# dari root repo agentic_analyst
git remote add space https://huggingface.co/spaces/<user>/analyst-backend
git push space main
```

HF otomatis build dari `Dockerfile` (3–6 menit). Status "Running" → backend live di:
`https://<user>-analyst-backend.hf.space`

### d. Verifikasi
Buka `https://<user>-analyst-backend.hf.space/health` → `{"status":"ok"}`.

> Free Space "tidur" setelah idle (± 48 jam tanpa traffic) → request pertama setelah tidur lambat
> (rebuild/cold start). Wajar.

---

## 3) Frontend — Vercel

1. Vercel → **Add New → Project** → import repo `agentic_analyst`.
2. **Root Directory:** `frontend`
3. Framework: **Next.js** (auto-detect). Build/Output default.
4. **Environment Variables:**

| Key | Nilai | Catatan |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<user>-analyst-backend.hf.space` | URL backend HF Space (TANPA trailing slash) |

5. Deploy → dapat domain `https://analyst-xxxx.vercel.app`.
6. **Balik ke HF Space** (Settings → Variables), set `ALLOWED_ORIGINS` = domain Vercel itu →
   Space otomatis restart (biar CORS lolos).

---

## 4) Urutan & verifikasi

1. Neon → dapat `DATABASE_URL`.
2. HF Space backend (push kode) → dapat URL → cek `/health`.
3. Vercel frontend (`NEXT_PUBLIC_API_URL` = URL HF Space) → dapat domain.
4. HF Space: set `ALLOWED_ORIGINS` = domain Vercel → restart.
5. Buka domain Vercel → tanya 1 pertanyaan → pastikan SSE mengalir & jawaban + verification muncul.

### Checklist env (ringkas)
- **HF Space (Secrets):** `GEMINI_API_KEY` · `DATABASE_URL`
- **HF Space (Variables):** `ALLOWED_ORIGINS` (`USE_DOCKER`/`GEMINI_MODEL` sudah default di Dockerfile)
- **Vercel:** `NEXT_PUBLIC_API_URL`

---

## 5) Catatan & batasan

- **Chart di subprocess mode:** PNG disimpan ke `ARTIFACTS_ROOT` dan dilayani `GET /artifacts/...`.
  Filesystem HF ephemeral → chart hidup selama instance hidup (cukup untuk demo per sesi).
- **Keamanan subprocess < Docker:** subprocess punya akses network. Untuk isolasi penuh
  (`--network none`, whitelist lib), self-host di VPS/host yang mendukung Docker lalu set
  `USE_DOCKER=true` + build image `backend/app/sandbox/image`.
- **Secret:** tidak ada key di repo. `.env`, `.env.local` di-gitignore; secret diisi di
  **HF Settings → Secrets**, bukan di file.
