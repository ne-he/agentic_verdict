"""
Assumptions layer — checklist asumsi (pass/warn/fail) per metode. (Port dari VERDICT.)

translator.py yang ubah jadi kalimat bisnis + risk badge.
A/B yang sudah bisa diisi dari diagnostics router (SRM, power) — implement duluan.
Observasi/time-series checks menyusul di M3 (butuh output engine-nya).
"""
from __future__ import annotations

from app.causal.assumptions.translator import explain
from app.causal.schemas import (
    AssumptionCheck,
    AssumptionStatus,
    EffectEstimate,
    Method,
    Risk,
)


def checks_for_ab(
    method_specific: dict,
    srm: dict,
    power: dict,
    effect: EffectEstimate | None = None,
) -> list[AssumptionCheck]:
    out: list[AssumptionCheck] = []

    # SRM
    srm_detected = srm.get("srm_detected", False)
    out.append(
        AssumptionCheck(
            name="sample_ratio",
            status=AssumptionStatus.FAIL if srm_detected else AssumptionStatus.PASS,
            value=srm.get("p_value"),
            business_explanation=explain("sample_ratio", srm_detected, srm),
            risk=Risk.HIGH if srm_detected else Risk.LOW,
        )
    )

    # Power — WARN kalau hasil non-signifikan DAN efek teramati < MDE:
    # artinya "tidak signifikan" bisa cuma karena sampel kurang, bukan efek nol.
    mde = power.get("mde_absolute")
    if mde is None:
        underpowered = True
    else:
        underpowered = (
            effect is not None
            and effect.is_significant is False
            and abs(effect.point) < mde
        )
    out.append(
        AssumptionCheck(
            name="statistical_power",
            status=AssumptionStatus.WARN if underpowered else AssumptionStatus.PASS,
            value=mde,
            business_explanation=explain("statistical_power", underpowered, power),
            risk=Risk.MEDIUM if underpowered else Risk.LOW,
        )
    )
    return out


def build_assumptions(method: Method, **ctx) -> list[AssumptionCheck]:
    """Dispatcher. M3 menambah cabang observasi & time-series."""
    if method == Method.AB_TEST:
        return checks_for_ab(
            ctx.get("method_specific", {}),
            ctx.get("srm", {}),
            ctx.get("power", {}),
            ctx.get("effect"),
        )
    # TODO(M3): overlap, positivity (propensity), balance after matching,
    # E-value (unconfoundedness sensitivity), SUTVA, pre-period fit stability.
    return []
