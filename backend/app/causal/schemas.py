"""Kontrak data jalur kausal (port dari VERDICT core/schemas.py, bagian kausal saja).

Single source of truth untuk router, engines, assumptions, decision.
Top-level result di sini bernama CausalResult (bukan AnalysisResult) supaya tidak
bentrok dengan app.core.schemas.AnalysisResult milik agent.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────
class ColumnRole(str, Enum):
    UNIT_ID = "unit_id"
    TREATMENT = "treatment"
    OUTCOME = "outcome"
    COVARIATE = "covariate"
    TIMESTAMP = "timestamp"
    IGNORE = "ignore"


class DeclaredType(str, Enum):
    AUTO = "auto"            # biar router yang putuskan
    RANDOMIZED = "randomized"
    OBSERVATIONAL = "observational"
    TIMESERIES = "timeseries"


class Method(str, Enum):
    AB_TEST = "ab_test"
    OBSERVATIONAL = "observational"
    TIMESERIES = "timeseries"
    DESCRIPTIVE = "descriptive"   # fallback: tak bisa klaim kausal


class AssumptionStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Decision(str, Enum):
    DEPLOY = "deploy"
    DEPLOY_WITH_CAUTION = "deploy_with_caution"
    DO_NOT_SHIP = "do_not_ship"
    INCONCLUSIVE = "inconclusive"


# ── Roles & options ──────────────────────────────────────────────────────────
class ColumnRoles(BaseModel):
    """Pemetaan peran kolom. WAJIB dikonfirmasi user sebelum analisis (D3)."""

    unit_id: str | None = None
    treatment: str | None = None
    outcome: str
    covariates: list[str] = Field(default_factory=list)
    timestamp: str | None = None
    intervention_date: str | None = None   # untuk jalur time-series


class CausalOptions(BaseModel):
    cuped: bool = False
    cuped_pre_column: str | None = None
    cate: bool = False
    expected_ratio: float | None = None      # untuk SRM (default 50/50)


# ── Router ───────────────────────────────────────────────────────────────────
class RouterDecision(BaseModel):
    method: Method
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str]                       # P3: kenapa metode ini dipilih
    assumptions_required: list[str]          # P3: asumsi yang sekarang ditanggung
    diagnostics: dict[str, Any] = Field(default_factory=dict)  # SMD, SRM, dst
    allow_override: bool = True


# ── Effect & method-specific ─────────────────────────────────────────────────
class EffectEstimate(BaseModel):
    point: float
    ci_low: float
    ci_high: float
    ci_level: float = 0.95
    relative_lift: float | None = None       # vs baseline control
    p_value: float | None = None
    is_significant: bool | None = None


class PowerAnalysis(BaseModel):
    observed_n_per_arm: int
    mde_absolute: float | None = None        # MDE pada N & power sekarang
    required_n_per_arm: float | None = None  # untuk capai target MDE
    days_needed: float | None = None
    power: float = 0.8


class RefutationResult(BaseModel):
    name: str                                # placebo / random_common_cause / subset / e_value
    passed: bool
    detail: str
    value: float | None = None


class Segment(BaseModel):
    label: str
    effect: float
    ci_low: float
    ci_high: float
    n: int


class CateResult(BaseModel):
    segments: list[Segment]
    drivers_shap: list[dict[str, float]] = Field(default_factory=list)
    note: str | None = None


# ── Assumptions ──────────────────────────────────────────────────────────────
class AssumptionCheck(BaseModel):
    name: str
    status: AssumptionStatus
    value: float | None = None
    business_explanation: str                # kalimat bahasa bisnis (deterministik)
    risk: Risk


# ── Decision ─────────────────────────────────────────────────────────────────
class Verdict(BaseModel):
    decision: Decision
    rationale: str                           # deterministik (Python), bukan LLM
    required_n: float | None = None          # kalau INCONCLUSIVE


# ── Confidence kausal (BLUEPRINT D5) ─────────────────────────────────────────
CausalConfidenceLabel = Literal["HIGH", "MEDIUM", "LOW"]


class CausalConfidenceBreakdown(BaseModel):
    """final = 0.30·router_confidence + 0.30·assumption_health
             + 0.25·verification_agreement + 0.15·tool_execution_success
    Komponen + breakdown WAJIB tampil di UI (P5)."""

    router_confidence: float = Field(..., ge=0.0, le=1.0)
    assumption_health: float = Field(..., ge=0.0, le=1.0)
    verification_agreement: float = Field(..., ge=0.0, le=1.0)
    tool_execution_success: float = Field(..., ge=0.0, le=1.0)
    final: float = Field(..., ge=0.0, le=1.0)
    label: CausalConfidenceLabel


# ── Top-level result jalur kausal ────────────────────────────────────────────
class CausalResult(BaseModel):
    """Bundle lengkap satu analisis kausal — dikonsumsi agent & frontend tab Causal."""

    dataset_id: str
    roles: ColumnRoles
    router_decision: RouterDecision
    effect: EffectEstimate | None = None
    power: PowerAnalysis | None = None
    method_specific: dict[str, Any] = Field(default_factory=dict)  # SRM, CUPED%, arm labels
    refutations: list[RefutationResult] = Field(default_factory=list)
    cate: CateResult | None = None
    assumptions: list[AssumptionCheck] = Field(default_factory=list)
    verdict: Verdict | None = None
