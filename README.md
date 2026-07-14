---
title: VERDICT ANALYST Causal Analytics Agent
emoji: ⚖️
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# VERDICT ANALYST — Causal Analytics Agent

> *Ask anything. When you ask WHY, get a defensible answer.*
>
> Frontmatter di atas dipakai **Hugging Face Spaces** (backend di-deploy sebagai Docker Space,
> port 7860). Frontend di Vercel. Lihat [`docs/DEPLOY.md`](docs/DEPLOY.md).

Merge dua sistem jadi satu flagship: **ANALYST** (agentic data analyst — nulis kodenya
sendiri, Docker sandbox, verifikasi 2 metode, computed confidence, eval harness) ×
**VERDICT** (causal inference — method router transparan, A/B engine tervalidasi
ground-truth, assumption checks bahasa bisnis, decision rule ship/hold).

Hasilnya: agent yang jawab **"APA"** (deskriptif, jalur ANALYST) *dan* **"KENAPA"**
(kausal, jalur VERDICT) — dan tahu sendiri kapan sebuah pertanyaan butuh causal treatment.

## 5 pembeda vs "chat with CSV"

1. **Agent nulis & jalanin kodenya sendiri** di Docker sandbox terkunci (no network, non-root, resource limit).
2. **Tiap angka deskriptif dihitung ulang 2 metode independen** (pandas sandbox vs DuckDB SQL) → computed confidence, bukan tebakan LLM.
3. **Pertanyaan kausal TIDAK dijawab LLM.** Intent classifier mendeteksi pertanyaan sebab-akibat → engine statistik deterministik (z-test/Welch + CI + CUPED + power/MDE + SRM) yang **lolos test recover-ground-truth** di data sintetik. Narasi LLM dicek **number-grounding**: angka yang tak ada di hasil engine → jawaban diganti template deterministik.
4. **Method router transparan + human gate.** Router memilih metode dengan `reasons[]` + `assumptions_required[]`, bisa di-override; analisis kausal tidak pernah jalan sebelum user **mengonfirmasi mapping kolom** (treatment/outcome/covariates).
5. **Eval harness** menilai agent-nya sendiri (gold questions, hallucination flag, failure dashboard).

## Arsitektur

```
NEXT.JS 14 (Vercel) ── SSE ──▶ FASTAPI
  tabs: Summary·Evidence·Code·          │
  Charts·Verify·CAUSAL                  ▼
  + RoleMappingModal          AGENT LOOP (ReAct + Gemini)
                                intent: descriptive ─▶ write_and_execute ─▶ DOCKER SANDBOX
                                                        + self-verify 2 metode (DuckDB)
                                intent: causal ──────▶ causal_route ─▶ causal_analyze
                                                        └─ app/causal/ (deterministik):
                                                           router ▶ ab_test engine ▶
                                                           assumptions ▶ decision rule
                              EVAL HARNESS · SQLITE (runs/scorecards/gold)
```

## Jalur kausal — kontrak kejujuran

- **P1** — LLM tidak pernah menghitung angka kausal. Python hitung; Gemini narasi; number-grounding check menjaga.
- **P2** — Tidak ada engine tanpa test recover ground-truth (`tests/causal_synthetic/` — DGP dengan true effect diketahui; `datasets/ab_marketing.meta.json` menyimpan ground-truth dataset demo sebagai bukti).
- **P3** — Router selalu surface alasan + asumsi + boleh override. SRM check duluan: rasio sampel meleset = hasil busuk, di-flag merah sebelum apa pun.

Confidence kausal (computed, breakdown tampil di UI):
```
final = 0.30·router_confidence + 0.30·assumption_health
      + 0.25·verification_agreement + 0.15·tool_execution_success
```

## Status roadmap

| Milestone | Isi | Status |
|---|---|---|
| M1 | Fondasi + causal A/B path end-to-end (engine, router, tools, intent, grounding, tests) | ✅ |
| M2 | UI Causal (tab + RoleMappingModal + confidence) · **deploy publik** | UI ✅ · deploy ⏳ |
| M3 | Observational path (DoWhy + PSM + refutation, Docker) | ⏳ |
| M4 | Causal eval set + README final + launch | ⏳ |

## Stack

Python · FastAPI + SSE · **Gemini** (`gemini-2.0-flash`) · DuckDB · Docker sandbox ·
SQLAlchemy 2.0 + SQLite · scipy/statsmodels · **Next.js 14** (App Router) + Tailwind.

## Run Locally

Butuh 2 terminal. Prasyarat: **Python 3.11/3.12**, **Node 18+**, **Gemini API key**
(aistudio.google.com). Docker opsional (`USE_DOCKER=false` → fallback subprocess).

`/.env` (root — dibaca backend):
```ini
GEMINI_API_KEY=<key-kamu>
GEMINI_MODEL=gemini-2.0-flash
DATABASE_URL=sqlite:///./backend/analyst.db
USE_DOCKER=false
```

`frontend/.env.local`:
```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Terminal A — backend:
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/generate_demo_dataset.py     # dataset demo A/B + ground-truth
pytest                                       # semua wajib hijau
uvicorn app.main:app --reload --port 8000
```

Terminal B — frontend:
```bash
cd frontend
npm install
npm run dev                                  # http://localhost:3000
```

**Demo money-shot:** pilih dataset `ab_marketing`, tanya
*"Apakah kampanye ini menaikkan konversi?"* → agent deteksi intent kausal → router usulkan
mapping → konfirmasi lewat modal → efek ~+0.02 (true lift, lihat `datasets/ab_marketing.meta.json`)
dalam CI, asumsi dicek, keputusan DEPLOY — semua angka dari engine, bukan LLM.

## What this can NOT tell you (jujur soal batas)

- Jalur observational/timeseries/CATE belum aktif (M3) — router tetap jujur menolak, tidak mengarang hasil.
- Multi-arm (>2 grup) belum didukung.
- Unconfoundedness tidak pernah bisa dibuktikan dari data — hanya diasumsikan & diuji sensitivitasnya (M3).
