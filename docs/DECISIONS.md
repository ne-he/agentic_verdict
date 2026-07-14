# DECISIONS.md — log keputusan desain VERDICT ANALYST

> Bahan blog post + jawaban interview "why did you...". Satu entry per keputusan
> yang menyimpang dari / mempertajam BLUEPRINT.md.

## 2026-07-14 — Sesi M1 (merge awal)

1. **Python 3.12 via Anaconda, bukan 3.14.** Mesin dev cuma punya Python 3.14 di PATH,
   tapi deps ANALYST dipin `<3.13` (scipy 1.14/pandas 2.2 belum punya wheel 3.14 di pin
   itu). Venv dibuat dari `C:\Users\wilhe\anaconda3\python.exe` (3.12.4). Deploy Docker
   tidak terpengaruh (base image 3.12).

2. **Intent classifier = regex deterministik, bukan LLM.** Gratis, 0 latency, bisa
   di-unit-test, dan default konservatif (DESCRIPTIVE) sesuai D2. Kalau nanti banyak
   false negative di log, upgrade ke LLM classify — tapi mulai dari yang bisa diuji.

3. **Kontrak SSE berubah: event `intent` dipancarkan SEBELUM `plan`; event baru `causal`.**
   Dua test lama (test_react, test_api) yang meng-assert `plan` sebagai event pertama
   di-update — ini perubahan kontrak yang disengaja (D2: intent wajib transparan),
   bukan regresi.

4. **Context kausal di-inject per-call, bukan via state tool.** Loop meng-inject
   `_confirmed_roles` saat memanggil tool kausal dan MEMBUANG `_confirmed_roles` dari
   args LLM (LLM tidak bisa memalsukan konfirmasi user). Thread-safe untuk request paralel.

5. **VERDICT masuk sebagai package `app/causal/` + 3 tools** — bukan microservice
   (sesuai BLUEPRINT D-arsitektur). Yang di-port hanya modul REAL: ab_test, router,
   assumptions, decision, DGP sintetik. Stub (observational/timeseries/CATE/pdf)
   TIDAK di-copy — ditulis baru di M3.

6. **`CausalResult` (bukan `AnalysisResult`) sebagai top-level kausal**, ditempel ke
   `AnalysisResult.causal` sebagai dict — kontrak core tidak tergantung `app.causal`,
   dan DB repository lama tidak perlu migrasi.

7. **Number-grounding lenient by design:** varian ×100 (persen), pembulatan 1–4 desimal,
   integer ≤12 dianggap struktural. Konsekuensi: angka halu yang kebetulan nabrak varian
   hasil bisa lolos (ketahuan saat test pakai 99.9 yang nabrak p-value SRM ~0.999×100).
   Trade-off diterima: false-block lebih merusak UX daripada false-pass langka; template
   fallback tetap menjaga kasus paling bahaya.

8. **Test decision rule pakai object terkonstruksi, bukan DGP seed-hunting.** `decide()`
   pure function; test INCONCLUSIVE-vs-DO_NOT_SHIP dengan EffectEstimate/PowerAnalysis
   eksplisit — deterministik, tidak rapuh terhadap noise seed.

9. **Konfirmasi mapping disimpan per-dataset di frontend** (`confirmedRoles` state, reset
   saat ganti dataset) → pertanyaan kausal follow-up tidak minta konfirmasi ulang.
