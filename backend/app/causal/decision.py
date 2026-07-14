"""
★ Decision rule — DETERMINISTIK (Python, bukan LLM). (Port dari VERDICT reporting/decision.py.)

Mapping signifikansi × asumsi → keputusan bisnis. Ini yang dirender LLM jadi prosa,
tapi keputusannya dihitung di sini (P1).
"""
from __future__ import annotations

from app.causal.schemas import (
    AssumptionCheck,
    AssumptionStatus,
    Decision,
    EffectEstimate,
    PowerAnalysis,
    Verdict,
)


def decide(
    effect: EffectEstimate | None,
    assumptions: list[AssumptionCheck],
    power: PowerAnalysis | None = None,
) -> Verdict:
    has_fail = any(a.status == AssumptionStatus.FAIL for a in assumptions)
    has_warn = any(a.status == AssumptionStatus.WARN for a in assumptions)

    # Asumsi gagal (mis. SRM) → hasil tidak bisa dipercaya, apapun p-value-nya.
    if has_fail:
        return Verdict(
            decision=Decision.DO_NOT_SHIP,
            rationale="Asumsi kunci gagal (mis. sample ratio mismatch). Perbaiki dulu sebelum percaya hasil apa pun.",
        )

    if effect is None or effect.is_significant is None:
        return Verdict(decision=Decision.INCONCLUSIVE, rationale="Efek tidak dapat diestimasi.")

    if effect.is_significant:
        if has_warn:
            return Verdict(
                decision=Decision.DEPLOY_WITH_CAUTION,
                rationale=(
                    f"Efek signifikan (lift {effect.point:+.3g}, CI [{effect.ci_low:.3g}, "
                    f"{effect.ci_high:.3g}]), tapi ada asumsi yang perlu dimitigasi sebelum full rollout."
                ),
            )
        return Verdict(
            decision=Decision.DEPLOY,
            rationale=(
                f"Efek signifikan & asumsi sehat (lift {effect.point:+.3g}, "
                f"CI [{effect.ci_low:.3g}, {effect.ci_high:.3g}]). Bukti cukup untuk deploy."
            ),
        )

    # Tidak signifikan: bedakan "benar-benar null" vs "underpowered"
    required_n = power.required_n_per_arm if power else None
    if required_n and power and required_n > power.observed_n_per_arm:
        return Verdict(
            decision=Decision.INCONCLUSIVE,
            rationale=(
                f"Belum signifikan, tapi sampel kurang. Butuh ~{required_n:,.0f}/arm "
                f"(sekarang {power.observed_n_per_arm:,})  untuk menyimpulkan."
            ),
            required_n=required_n,
        )
    return Verdict(
        decision=Decision.DO_NOT_SHIP,
        rationale="Tidak ada efek terdeteksi pada daya uji yang memadai. Jangan ship.",
    )
