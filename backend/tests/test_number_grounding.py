"""Number-grounding (P1/D4): angka di prosa kausal harus ada di hasil engine.

Prosa halu → fallback template deterministik. Test juga confidence kausal (D5).
"""
from __future__ import annotations

from app.causal.grounding import check_grounding, render_template, result_numbers
from app.causal.schemas import (
    AssumptionCheck,
    AssumptionStatus,
    CausalResult,
    ColumnRoles,
    Decision,
    EffectEstimate,
    Method,
    PowerAnalysis,
    Risk,
    RouterDecision,
    Verdict,
)
from app.causal.service import compute_causal_confidence


def _result() -> CausalResult:
    return CausalResult(
        dataset_id="ab_marketing",
        roles=ColumnRoles(treatment="variant", outcome="converted"),
        router_decision=RouterDecision(
            method=Method.AB_TEST,
            confidence=0.9,
            reasons=["Kovariat seimbang antar arm."],
            assumptions_required=["Penugasan acak."],
        ),
        effect=EffectEstimate(
            point=0.0198,
            ci_low=0.0116,
            ci_high=0.0280,
            relative_lift=0.196,
            p_value=0.000002,
            is_significant=True,
        ),
        power=PowerAnalysis(observed_n_per_arm=10_000, mde_absolute=0.0118),
        assumptions=[
            AssumptionCheck(
                name="sample_ratio",
                status=AssumptionStatus.PASS,
                value=0.7,
                business_explanation="Alokasi sampel sehat.",
                risk=Risk.LOW,
            )
        ],
        verdict=Verdict(decision=Decision.DEPLOY, rationale="Efek signifikan & asumsi sehat."),
    )


class TestGrounding:
    def test_grounded_prose_passes(self):
        prose = (
            "Kampanye menaikkan konversi sebesar +0.0198 poin (CI 95%: [0.0116, 0.0280]), "
            "signifikan. Lift relatif 19.6%."
        )
        grounded, ungrounded = check_grounding(prose, _result())
        assert grounded, f"harusnya grounded, tapi: {ungrounded}"

    def test_percent_variant_matches(self):
        # 0.0198 ditulis "1.98%" → tetap grounded (varian ×100)
        grounded, _ = check_grounding("Konversi naik 1.98% (absolut).", _result())
        assert grounded

    def test_hallucinated_number_fails(self):
        grounded, ungrounded = check_grounding(
            "Kampanye menaikkan konversi sebesar 0.0500 poin.", _result()
        )
        assert not grounded
        assert "0.0500" in ungrounded

    def test_small_integers_are_structural(self):
        grounded, _ = check_grounding("Ada 2 arm dan 3 langkah analisis.", _result())
        assert grounded

    def test_result_numbers_contains_percent_variants(self):
        nums = result_numbers(_result())
        assert any(abs(v - 1.98) < 1e-9 for v in nums)


class TestTemplate:
    def test_template_is_self_grounded(self):
        """Template fallback WAJIB lolos grounding-check-nya sendiri."""
        result = _result()
        prose = render_template(result)
        grounded, ungrounded = check_grounding(prose, result)
        assert grounded, f"template memuat angka liar: {ungrounded}"

    def test_template_mentions_decision_and_method(self):
        prose = render_template(_result())
        assert "ab_test" in prose and "DEPLOY" in prose


class TestCausalConfidence:
    def test_breakdown_and_weights(self):
        r = _result()
        conf = compute_causal_confidence(
            router_decision=r.router_decision,
            assumptions=r.assumptions,
            verification_agreement=1.0,
            tool_execution_success=1.0,
        )
        # 0.30*0.9 + 0.30*1.0 + 0.25*1.0 + 0.15*1.0 = 0.97
        assert abs(conf.final - 0.97) < 1e-6
        assert conf.label == "HIGH"

    def test_failed_assumption_drags_confidence(self):
        r = _result()
        r.assumptions[0].status = AssumptionStatus.FAIL
        conf = compute_causal_confidence(
            router_decision=r.router_decision,
            assumptions=r.assumptions,
            verification_agreement=None,  # tanpa verifikasi → netral
            tool_execution_success=1.0,
        )
        assert conf.assumption_health == 0.0
        assert conf.final < 0.8

    def test_no_signal_is_neutral_not_extreme(self):
        r = _result()
        conf = compute_causal_confidence(
            router_decision=r.router_decision,
            assumptions=[],
            verification_agreement=None,
        )
        assert conf.assumption_health == 0.5
        assert conf.verification_agreement == 0.5
