"""P2: engine kausal WAJIB me-recover ground-truth dari DGP sintetik dalam CI-nya.

Kalau test ini merah, engine-nya BELUM ADA (definisi selesai per CLAUDE.md).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.causal.decision import decide
from app.causal.engines import ab_test
from app.causal.schemas import CausalOptions, ColumnRoles, Decision
from tests.causal_synthetic.dgp_ab import make_ab_binary, make_ab_continuous


def _roles(treatment: str, outcome: str, covs: list[str] | None = None) -> ColumnRoles:
    return ColumnRoles(treatment=treatment, outcome=outcome, covariates=covs or [])


class TestABBinary:
    def test_recovers_true_lift_within_ci(self):
        truth = make_ab_binary(n_per_arm=10_000, true_lift_absolute=0.02, seed=42)
        out = ab_test.run(truth.df, _roles("group", "converted"), CausalOptions())
        e = out["effect"]
        assert e.ci_low <= truth.true_lift_absolute <= e.ci_high
        assert e.point == pytest.approx(truth.true_lift_absolute, abs=0.01)
        assert e.is_significant is True
        assert out["method_specific"]["metric_type"] == "binary"

    def test_null_effect_not_significant(self):
        truth = make_ab_binary(n_per_arm=5_000, true_lift_absolute=0.0, seed=7)
        out = ab_test.run(truth.df, _roles("group", "converted"), CausalOptions())
        e = out["effect"]
        assert e.ci_low <= 0.0 <= e.ci_high
        assert e.is_significant is False

    def test_pvalue_calibrated_under_null(self):
        """Di bawah null, p<0.05 harus terjadi ~5% dari banyak simulasi (kalibrasi)."""
        hits = 0
        n_sim = 40
        for seed in range(n_sim):
            truth = make_ab_binary(n_per_arm=1_000, true_lift_absolute=0.0, seed=seed)
            out = ab_test.run(truth.df, _roles("group", "converted"), CausalOptions())
            if out["effect"].p_value < 0.05:
                hits += 1
        # binomial(40, 0.05): >7 false positive sangat tidak mungkin (p < 1e-4)
        assert hits <= 7, f"p-value tidak terkalibrasi: {hits}/{n_sim} false positive"


class TestABContinuous:
    def test_recovers_true_effect_within_ci(self):
        truth = make_ab_continuous(n_per_arm=5_000, true_effect=3.0, seed=7)
        out = ab_test.run(truth.df, _roles("group", "revenue"), CausalOptions())
        e = out["effect"]
        assert e.ci_low <= truth.true_lift_absolute <= e.ci_high
        assert out["method_specific"]["metric_type"] == "continuous"

    def test_cuped_reduces_variance_and_keeps_truth(self):
        truth = make_ab_continuous(n_per_arm=5_000, true_effect=3.0, seed=7)
        opts = CausalOptions(cuped=True, cuped_pre_column="pre_metric")
        out = ab_test.run(truth.df, _roles("group", "revenue"), opts)
        reduction = out["method_specific"]["cuped_variance_reduction"]
        assert reduction is not None and reduction > 0.1  # pre berkorelasi → wajib memangkas varians
        e = out["effect"]
        assert e.ci_low <= truth.true_lift_absolute <= e.ci_high

    def test_power_analysis_present(self):
        truth = make_ab_continuous(n_per_arm=2_000, true_effect=3.0, seed=11)
        out = ab_test.run(truth.df, _roles("group", "revenue"), CausalOptions())
        p = out["power"]
        assert p.observed_n_per_arm == 2_000
        assert p.mde_absolute is not None and p.mde_absolute > 0


class TestEngineGuards:
    def test_constant_outcome_rejected(self):
        truth = make_ab_binary(n_per_arm=100, true_lift_absolute=0.0, seed=1)
        df = truth.df.copy()
        df["converted"] = 1
        with pytest.raises(ValueError, match="konstan"):
            ab_test.run(df, _roles("group", "converted"), CausalOptions())

    def test_single_arm_rejected(self):
        truth = make_ab_binary(n_per_arm=100, seed=1)
        df = truth.df[truth.df["group"] == 1]
        with pytest.raises(ValueError, match="2 arm"):
            ab_test.run(df, _roles("group", "converted"), CausalOptions())

    def test_missing_rows_dropped_and_reported(self):
        truth = make_ab_binary(n_per_arm=1_000, seed=3)
        df = truth.df.copy()
        df.loc[df.index[:50], "converted"] = np.nan
        out = ab_test.run(df, _roles("group", "converted"), CausalOptions())
        assert out["method_specific"]["n_rows_dropped_missing"] == 50


class TestDecisionRule:
    def test_significant_healthy_deploys(self):
        truth = make_ab_binary(n_per_arm=10_000, true_lift_absolute=0.02, seed=42)
        out = ab_test.run(truth.df, _roles("group", "converted"), CausalOptions())
        verdict = decide(out["effect"], assumptions=[], power=out["power"])
        assert verdict.decision == Decision.DEPLOY

    def test_underpowered_inconclusive(self):
        # Rule mapping deterministik: non-signifikan + required_n > observed_n
        # → INCONCLUSIVE ("belum bisa disimpulkan"), BUKAN "tidak ada efek".
        from app.causal.schemas import EffectEstimate, PowerAnalysis

        effect = EffectEstimate(
            point=0.01, ci_low=-0.005, ci_high=0.025, p_value=0.2, is_significant=False
        )
        power = PowerAnalysis(observed_n_per_arm=300, mde_absolute=0.03, required_n_per_arm=2_400)
        verdict = decide(effect, assumptions=[], power=power)
        assert verdict.decision == Decision.INCONCLUSIVE
        assert verdict.required_n == 2_400

    def test_no_effect_at_adequate_power_do_not_ship(self):
        from app.causal.schemas import EffectEstimate, PowerAnalysis

        effect = EffectEstimate(
            point=0.001, ci_low=-0.004, ci_high=0.006, p_value=0.7, is_significant=False
        )
        power = PowerAnalysis(observed_n_per_arm=50_000, mde_absolute=0.004, required_n_per_arm=1_000)
        verdict = decide(effect, assumptions=[], power=power)
        assert verdict.decision == Decision.DO_NOT_SHIP
