# PROMPT UNTUK CLAUDE DESIGN (Frontend)

> Cara pakai: buka Claude (chat / Claude Code sesi terpisah), paste **PROMPT UTAMA** di bawah.
> Hasilnya (komponen Next.js + mock data) lo taro di folder `frontend/`. Nanti Claude Code Antigravity
> yang nyambungin ke API real (task T4.2). **Claude design jangan bikin backend** — cukup UI + mock data.

---

## KONTEKS PENTING SEBELUM PROMPT

Design ini harus **match kontrak data backend** biar gampang disambung. Tipe data kunci (mirror dari `backend/app/core/schemas.py`):

```ts
type PlanStep   = { id: string; description: string; tool: string; status: "pending"|"running"|"done"|"error" }
type ToolCall   = { tool: string; input: string; output: string; error?: string; durationMs: number }
type Verification = { methodA: string; methodB: string; agreement: number; contradictions: string[]; passed: boolean }
type Confidence = { answerConsistency: number; verificationAgreement: number; toolExecutionSuccess: number; dataCoverage: number; final: number; label: "HIGH"|"MEDIUM"|"LOW" }
type AnalysisResult = { runId: string; answerMarkdown: string; code: string; chartPaths: string[]; verification: Verification; confidence: Confidence; toolCalls: ToolCall[]; tokens: number; costUsd: number; durationMs: number }
type SSEEvent = { type: "plan"|"step"|"tool"|"chart"|"verify"|"confidence"|"final"|"error"; data: any }
```

---

## PROMPT UTAMA (copy semua di bawah ini ke Claude design)

````
ROLE: Kamu senior product designer + frontend engineer. Bangun UI untuk produk "ANALYST — Verified
Analytics Agent". Output: komponen Next.js 14 (App Router) + Tailwind + shadcn/ui, pakai MOCK DATA
(jangan bikin backend / API call real). Semua dalam TypeScript.

PRODUK: Agentic data analyst yang nulis kodenya sendiri, jalanin di sandbox, verifikasi tiap angka
pakai 2 metode, dan kasih confidence yang DIHITUNG (bukan ditebak). Tagline: "Ask questions. See the
evidence. Verify every number." Pembeda = Trust + Verification + Reproducibility. Ini portfolio piece
buat recruiter 2026 — harus keliatan production-grade, bukan demo mahasiswa.

POSITIONING VISUAL: Profesional, dense-but-clean, mirip Linear / Vercel / Cursor / Claude Research.
Dark theme default. Monospace untuk kode & angka. BUKAN gaya chatbot bubble warna-warni. Yang dijual
adalah "execution trace yang transparan", bukan jawaban instan.

LAYOUT UTAMA (halaman /analyze) — SPLIT VIEW:
- Kiri (~35%): CHAT / pertanyaan. Input NL di bawah, riwayat pertanyaan sesi di atas. Dropdown pilih
  dataset (Retail/Superstore, Finance, HR Attrition). Dukung follow-up multi-turn.
- Kanan (~65%): ANALYSIS WORKSPACE. Di atas: EXECUTION TIMELINE horizontal (Planner → Tool 1 → Tool 2
  → Self-Verify → Answer) tiap node bisa status pending/running/done/error + bisa di-expand.
  Di bawah timeline: 5 TAB:
    1. Executive Summary — ringkasan buat manager (angka kunci + kontributor + confidence). Markdown.
    2. Evidence — tiap klaim dipasangin bukti: query + result. Format claim → SQL → hasil.
    3. Code — semua kode yang dijalankan, syntax-highlighted, tombol Copy + "Re-run this analysis".
    4. Charts — gambar chart (PNG), tombol download.
    5. Verification Report — TAB KILLER. Tampilkan tiap klaim: Method A vs Method B, agreement %,
       atau "Mismatch detected → confidence reduced". Visual jelas hijau (cocok) / merah (mismatch).

KOMPONEN WAJIB:
- ConfidenceBadge: HIGH (hijau) / MEDIUM (kuning) / LOW (merah). Hover/expand → breakdown 4 komponen
  (answer consistency 40%, verification agreement 30%, tool execution 20%, data coverage 10%) sebagai
  bar kecil + skor final %. HARUS keliatan "dihitung", bukan label asal.
- StreamingState: tampilan progresif saat agent kerja — spinner per langkah ("Menulis SQL...",
  "Menjalankan sandbox...", "Verifikasi selesai ✓"). Chart muncul inline pas siap.
- ExecutionTimeline: node status + durasi tiap step, expandable lihat tool input/output.

HALAMAN LAIN:
- /history : daftar run lama (pertanyaan, dataset, confidence, correctness kalau ada). Klik → buka ulang.
- /eval : FAILURE ANALYSIS DASHBOARD. Cards: Last 100 Runs (Correct / Incorrect / Hallucination /
  Verification Failure / Execution Failure) + "Top Failure Types" (wrong aggregation, wrong date
  filtering, schema misunderstanding, null handling). Chart tren correctness over time + cost
  distribution. Ini bagian yang bikin recruiter senior mikir "ini reliability engineering".

ATURAN OUTPUT:
- Semua data dari file mock terpusat: frontend/lib/mock.ts (export contoh AnalysisResult, daftar run,
  metrik eval, daftar dataset). Tipe ikutin yang aku kasih di bawah PERSIS (biar gampang disambung API).
- Pisahin komponen reusable di frontend/components/. Pakai shadcn/ui (Card, Tabs, Badge, Button,
  ScrollArea, Tooltip, Skeleton).
- Responsive: split view jadi tab di mobile.
- Aksesibel: kontras cukup, fokus keyboard di input.
- JANGAN bikin: backend, auth, API call real, state management berat. Cukup UI + mock + state lokal.

TIPE DATA (pakai PERSIS ini di frontend/lib/types.ts):
[TEMPEL blok TypeScript "KONTEKS PENTING" dari atas ke sini]

DELIVERABLE:
1. Struktur folder frontend/ (app/, components/, lib/).
2. Halaman: /analyze (split view + timeline + 5 tab), /history, /eval.
3. Komponen: ConfidenceBadge, ExecutionTimeline, WorkspaceTabs, VerificationReport, StreamingState,
   FailureDashboard, DatasetPicker.
4. frontend/lib/mock.ts + types.ts.
5. Catatan singkat di README frontend: mana yang perlu disambung ke API real (endpoint /analyze SSE,
   /run/{id}, /eval/dashboard, /datasets).

Mulai dengan ringkasan arsitektur komponen + wireframe ASCII, lalu kasih kodenya per file.
````

---

## CATATAN BUAT NEHEMIAH
- Kalau mau konsisten sama identitas visual lo yang lain, kasih tau Claude design palet warnanya. Default-nya gue saranin **dark + 1 aksen** (biru/emerald buat "verified"). Hindari oranye Lava kalau mau project ini beda branding dari portfolio Saturn.
- Output design = **mock dulu**. Yang nyambungin ke backend real itu Claude Code Antigravity (task T4.2). Jadi pastikan `types.ts` design = `schemas.py` backend. Itu kunci biar nyambung mulus.
- Jangan minta Claude design bikin backend. Sekali dia bikin backend, kontraknya bakal beda sama punya lo dan repot nyatuinnya.
