# AGENTIC VERDICT — Blueprint Eksekusi Merge

> **Analytics agent yang bisa jawab "APA" dan "KENAPA".**
> Nulis kodenya sendiri, jalanin di sandbox, verifikasi tiap angka — dan waktu pertanyaannya kausal
> ("apakah X *menyebabkan* Y?"), dia nggak nebak: dia routing ke causal engine yang tervalidasi,
> surface asumsinya, dan kasih efek + confidence interval yang defensible.
>
> One-liner produk: *"An analyst that writes its own code, checks its own math — and when you ask WHY, proves it causally."*

**Owner:** Nehemiah · **Status:** Spec (approved, pre-build) · **Target durasi:** 6–8 minggu
**Eksekusi:** Claude Code — **baca file ini sebagai sumber kebenaran tunggal.** Aturan kerja harian ada di `CLAUDE.md` repo ini.

---

## 0. North Star (kenapa projek ini ada)

Ini **merge dua projek existing** jadi satu flagship:

| Parent | Lokasi | Apa yang diambil |
|---|---|---|
| **ANALYST** (agentic_analyst) | `..\agentic_analyst\` | SELURUH fondasi: agent loop ReAct + Gemini, Docker sandbox, self-verification 2 metode, computed confidence, eval harness, SQLite history, frontend Next.js 14 |
| **VERDICT** | `..\verdict\` | Otak kausal: A/B engine (sig+CI+CUPED+power/MDE+SRM), router pemilih metode, assumptions layer + translator bahasa PM, DGP sintetik ber-ground-truth |

**Kenapa digabung:** ANALYST punya *trust infrastructure* tapi cuma bisa jawab pertanyaan deskriptif
("berapa", "tren apa"). VERDICT punya *causal rigor* tapi nggak punya wadah — baru M1, backend-only,
tanpa UI. Digabung = satu projek yang nutup **ketiga kelas portofolio sekaligus**:
- 🤖 **AI** — agentic system (planner, tool use, self-verify)
- 📊 **ML/DataSci** — statistical & causal inference tervalidasi ground-truth
- 💼 **Bisnis** — decision rule ship/hold/iterate + narasi asumsi dalam bahasa PM

**Pembeda vs "chat with CSV" (hafalkan, ini pitch interview):**
1. Agent **nulis & jalanin kodenya sendiri** di sandbox terkunci — bukan template query.
2. Tiap angka **dihitung ulang 2 metode independen** (pandas vs DuckDB SQL) → computed confidence, bukan "confidence" karangan LLM.
3. Pertanyaan kausal **nggak dijawab LLM** — dijawab engine deterministik yang **lolos test recover ground-truth** di data sintetik.
4. Router metode **transparan + bisa di-override** — surface alasan & asumsi, bukan black box.
5. Ada **eval harness** yang menilai agent-nya sendiri (gold questions, hallucination flag).

Kalau di akhir project cuma jadi "ANALYST yang ada tombol A/B test", **gagal**. Yang bikin flagship:
agent yang *sadar* kapan sebuah pertanyaan butuh causal treatment, milih metode dengan alasan, dan
jujur soal asumsi yang ditanggung. Jaga itu di atas segalanya.

---

## 1. Kondisi Awal (inventaris jujur — verified 14 Jul 2026)

### 1.1 ANALYST (`..\agentic_analyst\`) — MATANG, jadi BASE

```
backend/app/
├── agent/            planner.py · react_loop.py · llm.py · self_verify.py · confidence.py · bundle.py
│   └── tools/        base.py (interface tool) · inspect_schema.py · execute.py
├── api/routes.py     HTTP + SSE streaming
├── core/             config.py · schemas.py · datasets.py
├── db/               models.py · repository.py · session.py · migrations/
├── eval/             grader.py · loader.py · metrics.py · run_batch.py · gold_set/superstore.json
├── sandbox/          runner.py · image/Dockerfile (no network, non-root, limit cpu/mem)
└── main.py · cli.py
backend/tests/        16 file test (api, react, planner, sandbox, confidence, grader, dst.)
frontend/             Next.js 14 App Router + Tailwind — split view, 5 tab workspace, SSE
docs/                 00_BLUEPRINT.md · DEPLOY.md (HF Space Docker + Vercel, SIAP tapi belum dieksekusi)
datasets/superstore.csv
```
Status: jalan lokal, tests ada, **belum deploy**.

### 1.2 VERDICT (`..\verdict\`) — hanya sebagian yang REAL

| Modul | File | Status |
|---|---|---|
| A/B engine | `backend/app/engines/ab_test.py` | ✅ REAL (z-test/Welch, CI, CUPED, power/MDE, SRM) |
| Router | `backend/app/router/classifier.py` + `diagnostics.py` | ✅ REAL (decision tree + SMD/SRM) |
| Assumptions | `backend/app/assumptions/checks.py` + `translator.py` | ✅ REAL (overlap/balance → kalimat bisnis) |
| Decision rule | `backend/app/reporting/decision.py` + `narrative.py` | ✅ REAL (ship/hold/iterate + narasi Gemini) |
| DGP sintetik | `backend/tests/synthetic/dgp_*.py` | ✅ REAL (ground-truth diketahui) |
| Ingestion | `backend/app/ingestion/` | ✅ REAL (loader + profiler) |
| Observational | `engines/observational.py` (1.2 KB) | ❌ STUB |
| Time-series | `engines/timeseries.py` (0.9 KB) | ❌ STUB |
| CATE | `engines/heterogeneous.py` (0.8 KB) | ❌ STUB |
| PDF builder | `reporting/pdf_builder.py` (0.6 KB) | ❌ STUB |

**Konsekuensi:** yang di-port hari pertama = baris ✅ saja. Stub JANGAN di-copy — nanti ditulis ulang
di M3 sesuai spec §3 `..\verdict\VERDICT_BLUEPRINT.md` (dokumen itu tetap referensi teknis engine).

### 1.3 Parent repos SETELAH merge
`agentic_analyst\` dan `verdict\` **JANGAN dihapus / diubah** selama build. Read-only reference.
Setelah AGENTIC VERDICT deploy & stabil (M4 kelar), dua folder itu dipindah ke `End\` oleh Nehemiah manual.

---

## 2. Arsitektur Target

```
┌────────────────────────────────────────────────────────────────────────┐
│                    NEXT.JS 14 FRONTEND (Vercel)                          │
│  Split view: [ Investigation log ] | [ Analysis workspace ]              │
│  Workspace 6 tab: Summary · Evidence · Code · Charts · Verify · ★CAUSAL │
│  ★CAUSAL tab = Router Decision Card (metode+alasan+override)             │
│              + Assumption badges (pass/warn/fail, bahasa PM)             │
│              + Effect size + CI + decision rule (ship/hold/iterate)      │
│              + Column-role mapping modal (treatment/outcome/covariates)  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ HTTP + SSE
┌──────────────────────────────────▼───────────────────────────────────────┐
│                          FASTAPI BACKEND                                  │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ AGENT LOOP (ReAct existing)                                         │ │
│  │  PLANNER ★upgrade: intent classification                            │ │
│  │    intent=DESCRIPTIVE → jalur lama (pandas sandbox + DuckDB verify)  │ │
│  │    intent=CAUSAL      → jalur baru (tools kausal, LLM DILARANG       │ │
│  │                          menghitung — P1)                            │ │
│  │  TOOLS: inspect_schema · write_and_execute · make_chart              │ │
│  │        ★causal_route  ★causal_analyze  ★causal_refute                │ │
│  │  SELF-VERIFY + COMPUTED CONFIDENCE ★extended:                        │ │
│  │    jawaban kausal dapat komponen assumption_health                   │ │
│  └───────────────────────┬────────────────────────────────────────────┘ │
│  ┌───────────────────────▼──────────────┐  ┌──────────────────────────┐ │
│  │ app/causal/  (eks-VERDICT, porting)   │  │ DOCKER SANDBOX (existing) │ │
│  │  router/ → engines/ → assumptions/    │  │ no-net · limits · nonroot │ │
│  │  → decision (deterministik, Python)   │  └──────────────────────────┘ │
│  └───────────────────────────────────────┘                               │
│  EVAL HARNESS (existing) ★extended: causal gold questions + DGP checks    │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
        SQLITE — run_history · scorecards · gold_questions · artifacts
```

**Prinsip arsitektur #1: VERDICT masuk sebagai *package* + *tools*, BUKAN service terpisah.**
Nggak ada microservice kedua, nggak ada HTTP internal. `app/causal/` cuma library Python murni
(DataFrame masuk → object Pydantic keluar) yang dibungkus 3 tool agent. Semua infra (SSE, DB,
sandbox, eval) tetap satu.

---

## 3. Keputusan Desain Kunci (baca sebelum nulis kode)

### D1 — Base = COPY dari ANALYST, bukan tulis ulang
Repo ini dimulai dengan menyalin seluruh `agentic_analyst` (minus junk — perintah di §7).
JANGAN refactor besar-besaran kode ANALYST yang sudah jalan. Perubahan pada kode existing dibatasi:
planner (intent), registrasi tools, confidence (komponen baru), schemas (tipe baru), frontend (tab baru).

### D2 — Intent classification di planner, konservatif
Planner mengklasifikasi tiap pertanyaan: `DESCRIPTIVE` | `CAUSAL`.
- Sinyal CAUSAL: "apakah X menyebabkan/meningkatkan/berdampak ke Y", "efek", "gara-gara", "impact of", "does X drive Y", perbandingan treatment vs control.
- **Default saat ragu = DESCRIPTIVE** + agent menyarankan: *"Kalau maksudmu efek kausal X→Y, jawab 'ya' dan tandai kolom treatment-nya."* Salah masuk jalur kausal itu mahal (minta mapping, asumsi); salah masuk deskriptif cuma kurang dalam. Konservatif menang.
- Intent + alasannya DITAMPILKAN di investigation log (transparansi, konsisten dengan DNA ANALYST).

### D3 — Column-role mapping: agent mengusulkan, user mengkonfirmasi
Causal path butuh peran kolom (`treatment`, `outcome`, `covariates`, opsional `pre_metric` untuk CUPED).
Alur: `causal_route` dipanggil → agent usulkan mapping dari nama/isi kolom → frontend munculkan
modal konfirmasi → user bisa koreksi → baru `causal_analyze` jalan.
**JANGAN pernah menjalankan analisis kausal dengan mapping yang belum dikonfirmasi user.**
(Ini juga fitur demo yang bagus: kelihatan agent "nanya dengan cerdas".)

### D4 — P1: LLM TIDAK PERNAH menghitung angka kausal (warisan VERDICT, non-negotiable)
Semua statistik/CI/keputusan dihitung Python deterministik di `app/causal/`. Gemini hanya menarasikan
object hasil. **Number-grounding check:** setiap angka dalam prosa jawaban kausal harus ada di object
hasil (regex match dengan toleransi format); mismatch → fallback ke template deterministik + log warning.

### D5 — Computed confidence diperluas, bukan diganti
Formula existing ANALYST tetap untuk jawaban deskriptif. Untuk jawaban kausal:
```
final = 0.30·router_confidence + 0.30·assumption_health
      + 0.25·verification_agreement + 0.15·tool_execution_success
assumption_health = proporsi tertimbang check pass/warn/fail dari assumptions layer
```
Bobot boleh di-tune, tapi **komponen dan breakdown-nya wajib tampil di UI** — angka tanpa breakdown = melanggar DNA projek.

### D6 — Tiga tool baru (interface ikut `agent/tools/base.py` existing)

| Tool | Input | Output (Pydantic) | Isi |
|---|---|---|---|
| `causal_route` | dataset_id, proposed_roles | `RouterDecision`: method, confidence, reasons[], assumptions_required[], needs_confirmation | Bungkus `causal/router/classifier.py` + diagnostics (SMD, SRM) |
| `causal_analyze` | dataset_id, confirmed_roles, method, params | `CausalResult`: effect (abs+rel), CI, p, power/MDE, cuped_variance_reduction, assumption_checks[], decision (ship/hold/iterate), warnings[] | Dispatch ke engine sesuai method |
| `causal_refute` | analysis_id, checks[] | `RefutationResult`: placebo, random-common-cause, sensitivity | M3 — stub dulu di M1–M2, tapi kontraknya didefinisikan sekarang |

Schemas kausal hidup di `app/causal/schemas.py` (port dari `verdict/app/core/schemas.py`, ambil bagian kausalnya saja) dan di-re-export lewat `core/schemas.py` untuk API.

### D7 — Dependency split: jalur A/B ringan, jalur observational Docker
- M1–M2 (A/B path): scipy + statsmodels murni → jalan native Windows, aman.
- M3 (DoWhy/EconML/CausalImpact): **WAJIB dalam Docker** (toolchain Linux; jangan debug build di Windows native — pelajaran dari VERDICT §11). Pin semua versi di `pyproject.toml`.
- Deps kausal dibuat **optional extra** (`pip install -e .[causal-advanced]`) supaya deploy A/B path nggak berat.

### D8 — Naming & identitas
- Folder/repo: `agentic_verdict`. Nama produk: **VERDICT ANALYST**.
- Tagline README: *"Ask anything. When you ask WHY, get a defensible answer."*
- ANALYST branding lama (README HF frontmatter dll.) di-update ke identitas baru di M1.

### D9 — Dataset demo
`datasets/superstore.csv` (existing) untuk deskriptif. **Tambah `datasets/ab_marketing.csv`** —
generate dari DGP sintetik VERDICT (`dgp_ab.py`) dengan true lift yang diketahui, disimpan beserta
`datasets/ab_marketing.meta.json` (berisi ground-truth). Demo money-shot: tanya *"apakah kampanye
ini menaikkan konversi?"* → agent recover true lift dalam CI → tunjukkan meta file sebagai bukti.

---

## 4. Struktur Repo Target

```
agentic_verdict/
├── BLUEPRINT.md                      # file ini
├── CLAUDE.md                         # aturan kerja harian Claude Code
├── README.md                         # identitas VERDICT ANALYST (tulis ulang di M1, final di M4)
├── Dockerfile                        # deploy HF Space (port dari ANALYST, update)
├── .env.example                      # GEMINI_API_KEY · GEMINI_MODEL · DATABASE_URL · USE_DOCKER
├── datasets/
│   ├── superstore.csv                # existing (deskriptif)
│   ├── ab_marketing.csv              # ★ baru — dari DGP, ground-truth diketahui
│   └── ab_marketing.meta.json        # ★ true lift + parameter DGP (bukti demo)
├── docs/
│   ├── DEPLOY.md                     # port dari ANALYST, update nama/port
│   └── DECISIONS.md                  # ★ log keputusan desain selama build (bahan blog/interview)
├── backend/
│   ├── pyproject.toml                # merge deps; extras: [causal-advanced] utk DoWhy/EconML
│   ├── app/
│   │   ├── main.py · cli.py
│   │   ├── agent/
│   │   │   ├── planner.py            # ★ MODIF: intent classification (D2)
│   │   │   ├── react_loop.py         # existing (jangan rombak)
│   │   │   ├── llm.py · self_verify.py · bundle.py
│   │   │   ├── confidence.py         # ★ MODIF: formula kausal (D5)
│   │   │   └── tools/
│   │   │       ├── base.py · inspect_schema.py · execute.py   # existing
│   │   │       ├── causal_route.py   # ★ BARU (D6)
│   │   │       ├── causal_analyze.py # ★ BARU (D6)
│   │   │       └── causal_refute.py  # ★ BARU (kontrak sekarang, isi M3)
│   │   ├── causal/                   # ★ BARU — eks-VERDICT, library murni tanpa I/O web
│   │   │   ├── schemas.py            # RouterDecision, CausalResult, AssumptionCheck, ...
│   │   │   ├── router/               # classifier.py · diagnostics.py      (port ✅)
│   │   │   ├── engines/
│   │   │   │   ├── ab_test.py        # port ✅ (REAL)
│   │   │   │   ├── observational.py  # M3 — tulis baru sesuai VERDICT_BLUEPRINT §3.2
│   │   │   │   ├── timeseries.py     # stretch
│   │   │   │   └── heterogeneous.py  # stretch
│   │   │   ├── assumptions/          # checks.py · translator.py           (port ✅)
│   │   │   └── decision.py           # rules ship/hold/iterate             (port ✅ dari reporting/decision.py)
│   │   ├── api/ · core/ · db/ · eval/ · sandbox/               # existing ANALYST
│   │   └── eval/gold_set/
│   │       ├── superstore.json       # existing
│   │       └── causal_ab.json        # ★ M4 — gold questions kausal
│   └── tests/
│       ├── (16 test existing ANALYST — harus tetap hijau)
│       ├── causal_synthetic/         # ★ port dgp_*.py dari VERDICT
│       ├── test_causal_engines.py    # ★ recover ground-truth dalam CI (P2)
│       ├── test_causal_router.py     # ★ routing benar utk tiap DGP + SRM flag
│       ├── test_causal_tools.py      # ★ kontrak tool + needs_confirmation flow
│       └── test_number_grounding.py  # ★ angka prosa ⊆ angka object (D4)
└── frontend/                         # copy ANALYST
    ├── app/ · components/ · lib/
    └── components/causal/            # ★ BARU: RouterDecisionCard · AssumptionBadges ·
                                      #   EffectSummary · RoleMappingModal
```

---

## 5. Milestones (4 gate — tiap gate = kondisi selesai yang bisa diverifikasi)

> Aturan eskalasi: milestone slip → pecah jadi 2 sub-milestone lebih kecil dengan tanggal baru, replan di sesi yang sama. Jangan diem-dieman.

### M1 — Fondasi + Causal A/B path end-to-end (minggu 1–2)
1. Copy base ANALYST (perintah §7), rename identitas → VERDICT ANALYST, **16 test existing hijau** sebelum nyentuh apa pun.
2. Port modul ✅ VERDICT → `app/causal/` (router, ab_test, assumptions, decision, schemas) + `tests/causal_synthetic/`.
3. `test_causal_engines.py`: DGP true-lift δ → engine recover δ dalam CI. **Hijau = boleh lanjut** (P2).
4. Tool `causal_route` + `causal_analyze` (A/B only) + registrasi di react loop.
5. Planner intent classification (D2) + unit test-nya.
6. Generate `datasets/ab_marketing.csv` + meta.json.
7. Number-grounding check untuk narasi kausal (D4) + test.

**GATE M1:** dari chat, tanya *"apakah kampanye di ab_marketing.csv menaikkan konversi?"* →
intent CAUSAL → route → (mapping dikonfirmasi via API dulu, UI belum) → efek + CI yang memuat
true lift → narasi lolos number-grounding. Semua test hijau (lama + baru).

### M2 — UI Causal + confidence + DEPLOY PUBLIK (minggu 3–4)
1. Frontend: tab **Causal** (RouterDecisionCard + AssumptionBadges + EffectSummary) + **RoleMappingModal** (D3).
2. Confidence formula kausal (D5) + breakdown tampil di UI.
3. Router decision & intent muncul di investigation log (SSE event baru).
4. Eksekusi `docs/DEPLOY.md`: backend → HF Space (Docker), frontend → Vercel.

**GATE M2:** URL publik hidup; demo A/B end-to-end **lewat browser** termasuk modal mapping;
badge confidence + breakdown tampil. *(Deploy di sini, BUKAN nunggu M4 — warisan aturan VERDICT:
deploy sebelum fitur berat. Ini asuransi anti-"projek ke-4 yang nganggur".)*

### M3 — Observational path (minggu 5–6)
1. `engines/observational.py` TULIS BARU sesuai `..\verdict\VERDICT_BLUEPRINT.md` §3.2: DoWhy graph + PSM, refutation (placebo, random common cause), **di Docker** (D7).
2. `causal_refute` tool diisi beneran; hasil refutation masuk tab Causal.
3. DGP confounded: engine naive (diff-in-means) HARUS bias, engine PSM HARUS recover true effect → dua-duanya di-assert (ini cerita interview paling kuat: *"gue buktiin metode naive salah, dan metode gue bener, di data yang gue tau jawabannya"*).
4. Router path observational aktif (imbalance/SRM → observational + alasan).

**GATE M3:** upload data observasi confounded → router pilih observational + jelasin kenapa →
efek + refutation tampil di UI. Stretch (BOLEH SKIP): timeseries/CausalImpact, CATE.

### M4 — Eval, polish, launch (minggu 7–8)
1. `eval/gold_set/causal_ab.json` — ≥10 gold questions kausal; grader extended (efek dalam toleransi, arah benar, asumsi ke-flag).
2. Jalankan full eval batch → angka masuk README (*"X% correct-within-CI on causal gold set"*).
3. README final: pitch, arsitektur, GIF demo, angka eval, limitasi jujur (bagian "What this can NOT tell you" — sinyal senioritas).
4. Re-deploy final + smoke test publik. Update `armory.js` / Hall of Projects + entry knowledge base web CV.

**GATE M4 = Definition of Done (§6).**

---

## 6. Definition of Done — "productable" checklist

- [ ] URL publik hidup (HF Space + Vercel), cold-start < 60 dtk terdokumentasi di README
- [ ] Demo 3 menit tanpa nyentuh kode: upload/pilih dataset → tanya deskriptif → tanya kausal → mapping modal → jawaban + confidence breakdown + assumption badges
- [ ] Semua test hijau di CI (port `verdict/.github/workflows/ci.yml`, extend)
- [ ] Test recover-ground-truth untuk SEMUA engine yang di-ship (P2)
- [ ] Eval harness punya skor causal gold set, tercetak di README
- [ ] README: arsitektur, pitch 5 pembeda (§0), limitasi jujur, cara run lokal
- [ ] `docs/DECISIONS.md` terisi (bahan blog post + jawaban interview "why did you...")
- [ ] Zero secrets di repo (`.env` di-gitignore, cek sebelum push pertama)
- [ ] Parent folders (`agentic_analyst`, `verdict`) belum disentuh — pindah ke `End\` cuma setelah semua di atas ✅

---

## 7. Setup Sesi Pertama (langkah eksekusi persis)

```powershell
# 0. Kerjakan DARI folder ini: Ongoing\agentic_verdict

# 1. Copy base ANALYST tanpa junk (PowerShell / robocopy):
robocopy "..\agentic_analyst" "." /E `
  /XD .git .venv node_modules .next __pycache__ .pytest_cache analyst_backend.egg-info sandbox\artifacts sandbox\tmp `
  /XF analyst.db *.log q1_out.txt "Sample - Superstore.csv.zip" structure_dan_pengembangannya.docx .env

# 2. JANGAN timpa BLUEPRINT.md & CLAUDE.md milik agentic_verdict (file ini).
#    Kalau robocopy bawa README/docs lama ANALYST → boleh, nanti ditulis ulang di M1.
#    docs/00_BLUEPRINT.md & 01_CLAUDE_CODE_TASKS.md lama ANALYST → hapus (sudah digantikan file ini).

# 3. Init git BARU (jangan warisi history):
git init && git add -A && git commit -m "M1 start: base copied from ANALYST"

# 4. Env: copy .env.example → .env, isi GEMINI_API_KEY. Python 3.11/3.12 (BUKAN 3.14 — deps kausal belum support).

# 5. Baseline: cd backend && pip install -e . && pytest   → 16 test WAJIB hijau sebelum modif apa pun.

# 6. Port VERDICT (copy manual, file per file, sesuai tabel §1.2 kolom ✅):
#    ..\verdict\backend\app\router\*        → backend\app\causal\router\
#    ..\verdict\backend\app\engines\ab_test.py → backend\app\causal\engines\
#    ..\verdict\backend\app\assumptions\*   → backend\app\causal\assumptions\
#    ..\verdict\backend\app\reporting\decision.py → backend\app\causal\decision.py
#    ..\verdict\backend\app\core\schemas.py → ambil model kausal → backend\app\causal\schemas.py
#    ..\verdict\backend\tests\synthetic\*   → backend\tests\causal_synthetic\
#    Perbaiki import path; JANGAN copy file stub (observational/timeseries/heterogeneous/pdf_builder).

# 7. Lanjut urutan M1 di §5. Satu langkah = commit satu.
```

---

## 8. Aturan Non-Negotiable (gabungan DNA dua parent)

- **P1 — LLM tidak pernah menghitung angka kausal.** Python deterministik hitung; Gemini narasi; number-grounding check wajib (D4).
- **P2 — Tidak ada engine tanpa test recover ground-truth.** Test belum hijau = modul belum ada.
- **P3 — Router transparan.** Selalu `reasons[]` + `assumptions_required[]` + override. Ragu → konservatif.
- **P4 — Verifikasi 2 metode tetap hidup** untuk jalur deskriptif (DNA ANALYST). Jangan dimatikan demi kecepatan.
- **P5 — Confidence selalu computed + breakdown tampil.** Tidak ada angka confidence tanpa asal-usul.
- **P6 — Test suite existing ANALYST tidak boleh merah.** Fitur baru yang merusak yang lama = regresi, revert dulu.

## 9. JANGAN (scope guard — pelanggaran paling mungkin)

- JANGAN bikin microservice / API terpisah untuk kausal. Satu backend (D-arsitektur §2).
- JANGAN rombak react_loop / sandbox / SSE yang sudah jalan. Sentuh seminimal D1.
- JANGAN kerjakan timeseries & CATE sebelum M1–M3 kelar. Itu stretch, bukan core.
- JANGAN copy stub VERDICT lalu "nanti diisi" — tulis baru saat waktunya, dari spec.
- JANGAN skip deploy M2 demi "nambah satu fitur lagi". Deploy adalah gate, bukan hadiah.
- JANGAN jalankan causal analysis tanpa konfirmasi mapping user (D3).
- JANGAN commit: `.env`, `*.db`, `*.log`, artifacts sandbox, checkpoint apa pun.
- JANGAN debug DoWhy/EconML di Windows native — Docker only (D7).

## 10. Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Gemini free tier rate limit saat eval batch | `gemini-2.0-flash`, batch dengan delay + retry backoff (pola sudah ada di eval ANALYST) |
| DoWhy/EconML dependency hell | D7: Docker only, versi di-pin, extras terpisah; A/B path tidak tergantung mereka |
| Intent classifier salah arah | D2: default DESCRIPTIVE + saran eksplisit; log intent untuk dipantau |
| Merge conflict konsep confidence lama vs baru | D5: dua formula terpisah by intent, satu komponen UI breakdown |
| Scope creep (penyakit lama: eksperimen molor) | Gate M2 = deploy publik. Kalau minggu 4 belum ada URL, STOP fitur, deploy dulu |
| ANALYST belum pernah deploy (DEPLOY.md untested) | Justru dites di M2 saat sistem masih kecil, bukan M4 saat sudah berat |

---

## 11. Posisi di Portofolio 3 Kelas

| Kelas | Peran VERDICT ANALYST |
|---|---|
| 🤖 AI | Flagship agentic: planner, tool-use, self-verification, eval harness |
| 📊 ML/DataSci | Flagship inferensi: statistik + kausal tervalidasi ground-truth, SRM/CUPED/PSM/refutation |
| 💼 Bisnis | Flagship decision science: ship/hold/iterate rule + asumsi dalam bahasa PM |

Projek pendamping per kelas tetap: PULSE (MLOps), BRIEF (fine-tuning — tetap standalone, JANGAN
digabung ke sini; nilai jualnya "model trainer" dan akan tenggelam), FinSight (RAG finance),
TrashVision (DL). Integrasi BRIEF×VERDICT ANALYST (hasil analisis → 3 brief audiens) = ide demo
LEPAS di masa depan, bukan bagian repo ini.

---

*Blueprint v1 — 14 Jul 2026. Kalau realita build menyimpang dari dokumen ini, update dokumen ini
dulu (plus alasan di `docs/DECISIONS.md`), baru lanjut koding. Dokumen bohong lebih bahaya daripada
tidak ada dokumen.*
