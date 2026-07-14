# CLAUDE.md — AGENTIC VERDICT (aturan kerja Claude Code)

Merge ANALYST (agent + trust infra) × VERDICT (causal engines) jadi satu flagship: **VERDICT ANALYST**.
**BACA `BLUEPRINT.md` DULU** — itu sumber kebenaran tunggal (kondisi awal, arsitektur, keputusan D1–D9, milestone M1–M4, setup §7). Spec teknis engine kausal detail: `..\verdict\VERDICT_BLUEPRINT.md` (referensi read-only).

## Status
- [x] M1 — Fondasi + causal A/B path end-to-end (API level) — 14 Jul 2026, 164 test hijau
- [ ] M2 — UI Causal + confidence kausal + **DEPLOY PUBLIK** — UI fungsional ✅ (14 Jul), design polish (Nehemiah) + deploy ⏳
- [ ] M3 — Observational path (DoWhy + PSM + refutation, Docker)
- [ ] M4 — Causal eval set + README final + launch

*(Update checklist ini + `docs/DECISIONS.md` tiap sesi. Sesi baru: cek status di sini dulu.)*

## Non-negotiable (detail di BLUEPRINT §8)
1. LLM tidak pernah menghitung angka kausal — Python hitung, Gemini narasi, number-grounding check wajib.
2. Engine tanpa test recover-ground-truth = engine belum ada.
3. Router selalu surface reasons + assumptions + override. Ragu → konservatif (DESCRIPTIVE).
4. 16 test existing ANALYST tidak boleh merah. Regresi → revert dulu.
5. Causal analysis tidak jalan tanpa konfirmasi column-role mapping dari user.

## Jangan
- JANGAN sentuh folder parent `..\agentic_analyst` & `..\verdict` (read-only reference).
- JANGAN rombak react_loop / sandbox / SSE existing — sentuh seminimal BLUEPRINT D1.
- JANGAN copy file stub VERDICT (observational/timeseries/heterogeneous/pdf_builder).
- JANGAN kerjakan timeseries/CATE sebelum M3 kelar — stretch.
- JANGAN lewatin gate deploy di M2.
- JANGAN commit `.env`, `*.db`, `*.log`, sandbox artifacts.
- JANGAN debug DoWhy/EconML native Windows — Docker only.

## Cara kerja
- Satu langkah milestone = satu commit. Test hijau sebelum lanjut.
- Python 3.11/3.12. Ruff + type hints + Pydantic v2. Pin versi deps kausal.
- Keputusan desain baru / penyimpangan dari blueprint → tulis di `docs/DECISIONS.md` + update BLUEPRINT.

## Stack
Python · FastAPI + SSE · Gemini (`gemini-2.0-flash`) · DuckDB · Docker sandbox · SQLAlchemy 2.0 + SQLite · scipy/statsmodels (A/B) · DoWhy/EconML (M3, Docker) · Next.js 14 + Tailwind.

## Bahasa
Dokumen & komentar: Indonesia lugas. Kode: PEP8 / konvensi TS standar.
