"""Orkestrator jalur kausal: route → engine → assumptions → decision → confidence.

Satu-satunya pintu masuk yang dipakai tools agent. Semua angka dihitung DI SINI
(deterministik, P1) — LLM cuma menarasikan CausalResult yang sudah jadi.
"""
from __future__ import annotations

import pandas as pd

from app.causal.assumptions.checks import build_assumptions
from app.causal.decision import decide
from app.causal.engines import ab_test
from app.causal.router.classifier import route
from app.causal.schemas import (
    AssumptionStatus,
    CausalConfidenceBreakdown,
    CausalOptions,
    CausalResult,
    ColumnRoles,
    DeclaredType,
    Method,
    RouterDecision,
)
from app.core.datasets import get_encoding, resolve_path

# Bobot confidence kausal (BLUEPRINT D5). Jumlah = 1.0.
W_ROUTER = 0.30
W_ASSUMPTION = 0.30
W_VERIFICATION = 0.25
W_TOOL = 0.15

# Skor kesehatan per status asumsi.
_STATUS_SCORE = {
    AssumptionStatus.PASS: 1.0,
    AssumptionStatus.WARN: 0.5,
    AssumptionStatus.FAIL: 0.0,
}
_NEUTRAL = 0.5  # tanpa sinyal → netral, bukan 0/1


def load_dataset(dataset_id: str) -> pd.DataFrame:
    return pd.read_csv(resolve_path(dataset_id), encoding=get_encoding(dataset_id))


def suggest_roles(df: pd.DataFrame) -> dict:
    """Usulan mapping kolom (heuristik nama + isi). Agent menampilkan ini ke user
    untuk DIKONFIRMASI (D3) — bukan untuk langsung dipakai."""
    treatment_hints = ("group", "variant", "treatment", "arm", "grup", "perlakuan", "bucket")
    outcome_hints = ("convert", "outcome", "target", "revenue", "sales", "click", "churn", "konversi")
    time_hints = ("date", "time", "tanggal", "waktu", "timestamp")

    def _match(hints: tuple[str, ...]) -> list[str]:
        return [c for c in df.columns if any(h in c.lower() for h in hints)]

    treatment_cands = [
        c for c in _match(treatment_hints) if df[c].nunique(dropna=True) == 2
    ] or [c for c in df.columns if df[c].nunique(dropna=True) == 2]
    outcome_cands = _match(outcome_hints)
    ts_cands = _match(time_hints)

    proposal = {
        "treatment": treatment_cands[0] if treatment_cands else None,
        "outcome": outcome_cands[0] if outcome_cands else None,
        "covariates": [
            c
            for c in df.columns
            if c not in {*treatment_cands[:1], *outcome_cands[:1], *ts_cands[:1]}
            and pd.api.types.is_numeric_dtype(df[c])
        ][:5],
        "timestamp": ts_cands[0] if ts_cands else None,
    }
    return proposal


def compute_causal_confidence(
    *,
    router_decision: RouterDecision,
    assumptions: list,
    verification_agreement: float | None = None,
    tool_execution_success: float = 1.0,
) -> CausalConfidenceBreakdown:
    """Confidence kausal — computed, breakdown wajib tampil (P5)."""
    if assumptions:
        health = sum(_STATUS_SCORE[a.status] for a in assumptions) / len(assumptions)
    else:
        health = _NEUTRAL
    veri = verification_agreement if verification_agreement is not None else _NEUTRAL

    final = (
        W_ROUTER * router_decision.confidence
        + W_ASSUMPTION * health
        + W_VERIFICATION * veri
        + W_TOOL * max(0.0, min(1.0, tool_execution_success))
    )
    final = max(0.0, min(1.0, final))
    label = "HIGH" if final >= 0.8 else ("MEDIUM" if final >= 0.5 else "LOW")
    return CausalConfidenceBreakdown(
        router_confidence=round(router_decision.confidence, 4),
        assumption_health=round(health, 4),
        verification_agreement=round(veri, 4),
        tool_execution_success=round(tool_execution_success, 4),
        final=round(final, 4),
        label=label,
    )


def run_causal_analysis(
    dataset_id: str,
    roles: ColumnRoles,
    options: CausalOptions | None = None,
    declared_type: DeclaredType = DeclaredType.AUTO,
    override_method: Method | None = None,
) -> CausalResult:
    """Pipeline kausal penuh untuk satu dataset + mapping terkonfirmasi."""
    options = options or CausalOptions()
    df = load_dataset(dataset_id)

    decision = route(df, roles, declared_type, options.expected_ratio)
    method = override_method or decision.method
    if override_method and override_method != decision.method:
        decision.reasons.append(
            f"User meng-override metode router ({decision.method.value} → {override_method.value})."
        )

    if method == Method.AB_TEST:
        out = ab_test.run(df, roles, options)
    elif method == Method.DESCRIPTIVE:
        return CausalResult(
            dataset_id=dataset_id, roles=roles, router_decision=decision
        )
    else:
        # M3: observational (DoWhy+PSM), stretch: timeseries/CATE.
        raise NotImplementedError(
            f"metode '{method.value}' belum diimplementasikan (roadmap M3) — "
            "router tetap transparan soal ini; gunakan A/B path atau tunggu M3"
        )

    effect = out["effect"]
    power = out["power"]
    method_specific = out["method_specific"]
    srm = decision.diagnostics.get("srm", {})

    assumptions = build_assumptions(
        method,
        method_specific=method_specific,
        srm=srm,
        power=power.model_dump(),
        effect=effect,
    )
    verdict = decide(effect, assumptions, power)

    return CausalResult(
        dataset_id=dataset_id,
        roles=roles,
        router_decision=decision,
        effect=effect,
        power=power,
        method_specific=method_specific,
        assumptions=assumptions,
        verdict=verdict,
    )
