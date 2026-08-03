"""Kontrak data tunggal untuk ANALYST (Pydantic v2).

ATURAN #5: schema didefinisikan di SINI sebelum endpoint/agent. Frontend meng-mirror
file ini ke `frontend/lib/types.ts` (via `frontend/lib/schemas.json` yang di-export).
Jangan duplikasi definisi tipe di tempat lain — ubah di sini, regenerate JSON schema.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Tipe literal yang dipakai lintas model ──────────────────────────────────
StepStatus = Literal["pending", "running", "done", "error"]
ConfidenceLabel = Literal["HIGH", "MEDIUM", "LOW"]
Intent = Literal["descriptive", "causal"]
# Alasan run agent berhenti (aturan produksi #3). Vocabulary + label bahasa manusia
# ada di app/agent/termination.py.
TerminationReason = Literal[
    "completed", "step_budget", "token_budget", "timeout", "tool_error", "cancelled", "crashed",
]
SSEEventType = Literal[
    "plan", "intent", "step", "tool", "chart", "verify", "causal",
    "confidence", "final", "error",
]


# ── Request masuk ───────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    """Pertanyaan analitik dari user terhadap sebuah dataset.

    `causal_roles`: mapping kolom kausal yang SUDAH dikonfirmasi user lewat
    RoleMappingModal (D3). None = belum ada konfirmasi → causal_analyze menolak jalan.
    Bentuk: {"treatment": str|None, "outcome": str, "covariates": [str], ...}
    """

    question: str = Field(..., min_length=1)
    dataset_id: str = Field(..., min_length=1)
    session_id: str | None = None
    causal_roles: dict[str, Any] | None = None


# ── Perencanaan & eksekusi tool ─────────────────────────────────────────────
class PlanStep(BaseModel):
    """Satu langkah eksplisit dari planner. Juga menyetir progress bar UI."""

    id: int
    description: str
    tool: str
    status: StepStatus = "pending"


class ToolCall(BaseModel):
    """Catatan satu pemanggilan tool (untuk execution trace / 'show your work')."""

    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str | None = None
    error: str | None = None
    duration_ms: int = 0


# ── Verifikasi & confidence ─────────────────────────────────────────────────
class VerificationResult(BaseModel):
    """Hasil self-verify: angka kunci dihitung 2 metode lalu dibandingkan."""

    method_a: str
    method_b: str
    agreement: float = Field(..., ge=0.0, le=1.0)
    contradictions: list[str] = Field(default_factory=list)
    passed: bool


class ConfidenceBreakdown(BaseModel):
    """Computed confidence (Blueprint §4.5) — BUKAN tebakan LLM.

    final = 0.40*answer_consistency + 0.30*verification_agreement
          + 0.20*tool_execution_success + 0.10*data_coverage
    """

    answer_consistency: float = Field(..., ge=0.0, le=1.0)
    verification_agreement: float = Field(..., ge=0.0, le=1.0)
    tool_execution_success: float = Field(..., ge=0.0, le=1.0)
    data_coverage: float = Field(..., ge=0.0, le=1.0)
    final: float = Field(..., ge=0.0, le=1.0)
    label: ConfidenceLabel


# ── Hasil akhir analisis (bundle reproducible) ──────────────────────────────
class AnalysisResult(BaseModel):
    """Bundle lengkap satu run: jawaban + kode + chart + verifikasi + confidence.

    Jalur kausal (intent="causal"):
    - `causal` = CausalResult utuh (router decision + effect + assumptions + verdict),
      di-dump sebagai dict supaya kontrak core tidak tergantung app.causal.
    - `causal_confidence` = breakdown formula kausal (BLUEPRINT D5); breakdown
      WAJIB tampil di UI (P5).
    - `answer_grounded` = False kalau narasi LLM gagal number-grounding dan
      di-fallback ke template deterministik (P1/D4).
    """

    run_id: str
    answer_markdown: str
    code: str
    dataset_id: str = ""
    dataset_snapshot: str = ""  # hash file dataset saat run -> provenance reproducibility
    chart_paths: list[str] = Field(default_factory=list)
    verification: VerificationResult | None = None
    confidence: ConfidenceBreakdown | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    intent: Intent = "descriptive"
    causal: dict[str, Any] | None = None
    causal_confidence: dict[str, Any] | None = None
    answer_grounded: bool = True
    # Kenapa run berhenti. "completed" = model memberi jawaban final; sisanya
    # menandakan jawaban kemungkinan belum tuntas (kena budget/timeout/error).
    termination_reason: TerminationReason = "completed"


# ── Streaming (SSE) ─────────────────────────────────────────────────────────
class SSEEvent(BaseModel):
    """Satu event yang di-stream ke frontend selama analisis berjalan."""

    type: SSEEventType
    data: dict[str, Any] = Field(default_factory=dict)


# ── Eval ────────────────────────────────────────────────────────────────────
class Scorecard(BaseModel):
    """Nilai satu run terhadap gold answer (dihasilkan eval harness)."""

    run_id: str
    question_id: str = ""
    correctness: float = Field(..., ge=0.0, le=1.0)
    cost_usd: float = 0.0
    tool_calls: int = 0
    time_to_insight: float = 0.0  # detik
    hallucination_flag: bool = False
    verification_accuracy: float = Field(0.0, ge=0.0, le=1.0)


class GoldQuestion(BaseModel):
    """Satu pertanyaan dalam gold set (divalidasi saat load)."""

    id: str
    category: str
    question: str
    gold_answer: str
    gold_code: str
    expected_value: float
    allowed_tolerance: float = 0.01
    is_trap: bool = False
    trap_note: str | None = None


class GoldSet(BaseModel):
    """Satu file gold set JSON: metadata dataset + list pertanyaan."""

    dataset_id: str
    dataset_file: str
    encoding: str = "utf-8"
    date_columns: list[str] = Field(default_factory=list)
    date_format: str | None = None
    note: str | None = None
    questions: list[GoldQuestion]


class BatchSummary(BaseModel):
    """Agregat hasil batch eval (semua pertanyaan dalam satu batch run)."""

    total: int
    avg_correctness: float = Field(..., ge=0.0, le=1.0)
    total_cost_usd: float = 0.0
    hallucination_rate: float = Field(..., ge=0.0, le=1.0)
    avg_tool_calls: float = 0.0
    avg_time_to_insight: float = 0.0
    run_ids: list[str] = Field(default_factory=list)


# ── Response API (FASE 4) ────────────────────────────────────────────────────
class RunRecord(BaseModel):
    """Satu run historis yang diambil dari DB (GET /run/{id})."""

    run_id: str
    dataset_id: str
    dataset_snapshot: str = ""
    question: str
    answer_markdown: str
    code: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    termination_reason: str = "completed"
    chart_paths: list[str] = Field(default_factory=list)
    created_at: str | None = None


class ResumableRun(BaseModel):
    """Run yang state-nya masih 'running' di checkpoint, kandidat resume setelah crash."""

    run_id: str
    question: str
    dataset_id: str
    intent: str = "descriptive"
    updated_at: str | None = None


class DatasetInfo(BaseModel):
    """Metadata satu dataset yang tersedia (GET /datasets)."""

    dataset_id: str
    file: str
    encoding: str = "utf-8"


class EvalDashboard(BaseModel):
    """Metrik agregat + run terbaru untuk failure dashboard (GET /eval/dashboard)."""

    summary: BatchSummary
    recent: list[Scorecard] = Field(default_factory=list)


# Model yang di-export ke JSON schema untuk FE.
EXPORTED_MODELS: list[type[BaseModel]] = [
    AnalyzeRequest,
    PlanStep,
    ToolCall,
    VerificationResult,
    ConfidenceBreakdown,
    AnalysisResult,
    SSEEvent,
    Scorecard,
    GoldQuestion,
    GoldSet,
    BatchSummary,
    RunRecord,
    ResumableRun,
    DatasetInfo,
    EvalDashboard,
]
