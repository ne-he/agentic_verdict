---
title: VERDICT ANALYST Causal Analytics Agent
emoji: ⚖️
colorFrom: gray
colorTo: indigo
sdk: gradio
sdk_version: 6.22.0
python_version: 3.12.12
app_file: space_app.py
pinned: false
---

<!-- LIVE URL: isi setelah deploy. Ganti seluruh baris "Live demo" di bawah dengan URL asli, contoh:
     **Live demo:** https://ne-he-verdict-analyst.hf.space  ·  frontend: https://verdict-analyst.vercel.app
     Slot ini sengaja ditaruh di bawah frontmatter, bukan di baris 1 file, karena baris 1 harus
     tetap `---` supaya Hugging Face Spaces bisa membaca konfigurasi sdk/app_file di atas. -->
**Live demo:** *(belum di-deploy, lihat [`docs/DEPLOY.md`](docs/DEPLOY.md))*

# VERDICT ANALYST — Causal Analytics Agent

[![CI](https://github.com/ne-he/agentic_verdict/actions/workflows/ci.yml/badge.svg)](https://github.com/ne-he/agentic_verdict/actions/workflows/ci.yml)

<!-- DEMO GIF: rekam dulu pakai skenario di docs/DEMO_SHOTLIST.md, simpan ke docs/demo.gif,
     lalu ganti baris di bawah ini dengan: ![Demo VERDICT ANALYST](docs/demo.gif) -->
*(GIF demo 20 detik menyusul, skenario rekamannya sudah disiapkan di [`docs/DEMO_SHOTLIST.md`](docs/DEMO_SHOTLIST.md))*

> *Ask anything. When you ask WHY, get a defensible answer.*
>
> Frontmatter di atas dipakai **Hugging Face Spaces** (backend di-deploy sebagai Docker Space,
> port 7860). Frontend di Vercel. Lihat [`docs/DEPLOY.md`](docs/DEPLOY.md).

Model frontier hari ini sudah rutin diminta memeriksa hasil kerjanya sendiri, dan tetap saja
salah dengan penuh percaya diri. Analisis Snorkel AI terhadap 195 percobaan Opus 5 di
Terminal-Bench menemukan **35% kegagalannya adalah *faulty inference***: model bernalar sampai
ke kesimpulan yang keliru, lalu jalan terus tanpa sadar sampai selesai (Snorkel AI, 2026).
Akar masalahnya bukan model kurang pintar. Self-verification memakai penalaran yang sama dengan
yang melahirkan error tadi, jadi kesalahannya lolos dari pemeriksanya sendiri.

**VERDICT ANALYST** (gabungan **ANALYST** × **VERDICT**) dibangun dari asumsi sebaliknya: jawaban
agent tidak dianggap benar sampai ada yang memverifikasinya dari luar. Setiap angka deskriptif
dihitung ulang lewat dua metode independen, pandas di dalam sandbox versus DuckDB SQL, dan
selisih keduanya jadi confidence yang **dihitung**, bukan diklaim. Setiap pertanyaan kausal tidak
pernah dijawab LLM: angkanya keluar dari engine statistik deterministik yang wajib lolos test
recover ground-truth di data sintetik, sementara narasi LLM di atasnya dicek number-grounding.
Begitu ada angka di narasi yang tidak ada di hasil engine, narasinya diganti template
deterministik.

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

## Eval scorecard

Gold set `superstore`, 20 pertanyaan, dijalankan 1 Agustus 2026. Detail per pertanyaan dan
cara reproduksinya ada di [`docs/EVAL_SCORECARD.md`](docs/EVAL_SCORECARD.md).

| Metrik | Nilai |
|---|---|
| Akurasi vs gold | 0,350 (7 dari 20 tepat) |
| Rata-rata tool call per pertanyaan | 2,55 |
| Hallucination flag rate | 65,0% (13 dari 20) |
| Biaya per query | tidak terinstrumentasi |

**Angka ini batas bawah, bukan performa sistem yang sebenarnya.** Run ini terpaksa memakai
`gemini-flash-lite-latest`, bukan `gemini-2.0-flash` yang dikonfigurasi repo, karena kuota harian
free tier model itu sudah habis. Di lima pertanyaan yang sempat kesentuh sebelum kuota mati,
`gemini-2.5-flash` menjawab benar 5 dari 5 sementara model lite ini cuma 2 dari 5. Run dengan
model produksi belum dijalankan, dan "biaya per query" belum bisa diisi karena `cost_usd` memang
belum pernah diinstrumentasi di kode. Jangan kutip 0,350 sebagai akurasi sistem ini.

Yang jujur bisa diklaim dari scorecard di atas: harness-nya jalan, gradernya bekerja, dan
hallucination flag berhasil menangkap pola "salah sambil pede" yang jadi premis README ini.

Batch yang sama diulang 2 Agustus 2026 dengan model yang sama untuk mengisi `run_history`
(bahan kalibrasi grader) dan menghasilkan 0,300 akurasi, 70,0% hallucination flag, 2,3 tool call
rata-rata. Selisihnya variasi antar-run, bukan perubahan kode, dan itu justru bukti n=20 terlalu
kecil untuk membedakan angka sedekat itu. Perbandingannya ada di
[`docs/EVAL_SCORECARD.md`](docs/EVAL_SCORECARD.md).

## Dua skill yang dibuktikan projek ini

Repo ini sengaja dipakai untuk membuktikan dua kemampuan yang paling sering diklaim tapi jarang
ditunjukkan buktinya. Status keduanya beda, dan bedanya ditulis apa adanya di bawah.

### 1. Agent dengan durable state, dan buktinya adalah test yang mematikan proses

Bukti yang dicari untuk skill ini bukan agent yang jalan mulus di demo, melainkan agent yang
**bisa lanjut setelah crash**. Di repo ini state loop ditulis ke SQLite **tiap langkah**
(tabel `run_states` dan `run_steps`), bukan cuma hasil akhirnya, lalu run yang mati bisa
dilanjutkan lewat `POST /runs/{run_id}/resume`. Kandidatnya bisa dilihat di `GET /runs/resumable`.

Klaim itu dijaga satu test yang lulus:
[`backend/tests/test_durable_state.py::test_resume_after_hard_process_kill`](backend/tests/test_durable_state.py).
Test itu menjalankan run agent di **subprocess terpisah**, membunuhnya di tengah dengan
`os._exit(1)` ([`backend/tests/crash_child.py`](backend/tests/crash_child.py)), lalu dari proses
induk memanggil resume dan membuktikan run selesai dengan jawaban benar plus tool call pra-crash
ikut terbawa. `os._exit` dipilih justru karena dia tidak menjalankan `finally` maupun `atexit`:
kalau state tetap selamat, satu-satunya penjelasan adalah checkpoint memang commit tiap langkah.

Batas runtime (12 langkah, 200 ribu token, 300 detik), tabel alasan terminasi, dan cara kerja
resume dijelaskan di [`docs/AGENT_RUNTIME.md`](docs/AGENT_RUNTIME.md).

### 2. Kalibrasi eval, pipeline-nya siap, angkanya BELUM ada

Hampir semua portfolio yang menulis "punya eval harness" tidak pernah membuktikan eval-nya
sendiri valid. Tanpa kalibrasi ke penilaian manusia, harness cuma opini mesin. Ironinya tajam
untuk projek ini: agent yang tugasnya menilai kejujuran analisis, gradernya sendiri belum pernah
dibuktikan sejalan dengan manusia.

Yang sudah ada dan sudah dijalankan: pipeline dua langkah
(`app/eval/export_calibration.py` untuk mengekspor jawaban agent ke CSV berkolom `human_label`
kosong, lalu `app/eval/calibration_report.py` untuk menghitung agreement rate, Cohen's kappa,
dan breakdown per kategori).

Yang **belum** ada: angkanya. Agreement dan kappa mustahil dihitung tanpa label manusia, dan
label itu tidak boleh dikarang. Jadi [`docs/EVAL_CALIBRATION.md`](docs/EVAL_CALIBRATION.md) hari
ini berstatus **MENUNGGU LABEL MANUSIA**, lengkap dengan langkah persis untuk menyelesaikannya.

**Jangan baca bagian ini sebagai klaim bahwa eval repo ini sudah terkalibrasi.** Yang bisa
diklaim: jalurnya lengkap, tinggal satu langkah manual yang memang harus dikerjakan manusia.

### Adversarial eval: hasilnya campur, dan itu ditulis apa adanya

Number-grounding check adalah klaim terkuat projek ini, jadi dia diuji dengan 12 pertanyaan yang
sengaja dirancang menjebolnya. Dijalankan 2 Agustus 2026 dengan `gemini-flash-lite-latest`,
seluruh 12 kasus (bukan subset), 0 error:

| Kategori | n | Tertangkap | Jebol | Tidak jelas |
|---|---:|---:|---:|---:|
| Premis palsu | 3 | 3 | 0 | 0 |
| Kausal yang disamarkan | 3 | 0 | 2 | 1 |
| Kolom tidak ada di dataset | 3 | 3 | 0 | 0 |
| Angka salah di dalam pertanyaan | 3 | 1 | 2 | 0 |
| **Total** | **12** | **7 (58%)** | **4 (33%)** | **1** |

Premis palsu dan kolom hilang ditangkap 3 dari 3. Dua kategori lain jebol, dan itu temuan yang
lebih berguna daripada angka bagus: agent masih mau memakai angka salah yang dibawa user sebagai
penyebut tanpa mengeceknya ke data, karena number-grounding sekarang cuma aktif di jalur kausal
terhadap hasil engine. Detail per kasus, caveat scoring, dan perbandingan dengan run subset
sebelumnya ada di [`docs/ADVERSARIAL_EVAL.md`](docs/ADVERSARIAL_EVAL.md).

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
