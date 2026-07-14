"""Router harus memilih metode yang benar untuk tiap bentuk data (P3) + transparan."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.causal.router.classifier import route
from app.causal.router.diagnostics import sample_ratio_mismatch
from app.causal.schemas import ColumnRoles, DeclaredType, Method
from tests.causal_synthetic.dgp_ab import make_ab_binary
from tests.causal_synthetic.dgp_confounded import make_confounded


def test_clean_ab_routes_to_ab_test():
    truth = make_ab_binary(n_per_arm=5_000, seed=42)
    roles = ColumnRoles(treatment="group", outcome="converted", covariates=["pre_metric"])
    d = route(truth.df, roles)
    assert d.method == Method.AB_TEST
    assert d.confidence >= 0.8
    assert d.reasons and d.assumptions_required  # P3
    assert d.allow_override is True


def test_confounded_routes_to_observational():
    truth = make_confounded(seed=42)
    covs = [c for c in truth.df.columns if c not in ("treatment", "outcome")]
    roles = ColumnRoles(treatment="treatment", outcome="outcome", covariates=covs)
    d = route(truth.df, roles)
    assert d.method == Method.OBSERVATIONAL
    assert any("SMD" in r or "seimbang" in r for r in d.reasons)


def test_declared_observational_wins():
    truth = make_ab_binary(n_per_arm=2_000, seed=1)
    roles = ColumnRoles(treatment="group", outcome="converted", covariates=["pre_metric"])
    d = route(truth.df, roles, DeclaredType.OBSERVATIONAL)
    assert d.method == Method.OBSERVATIONAL


def test_no_treatment_with_time_routes_timeseries():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=100), "sales": range(100)})
    roles = ColumnRoles(
        outcome="sales", timestamp="date", intervention_date="2026-02-15"
    )
    d = route(df, roles)
    assert d.method == Method.TIMESERIES


def test_no_treatment_no_time_is_descriptive():
    df = pd.DataFrame({"sales": range(100)})
    d = route(df, ColumnRoles(outcome="sales"))
    assert d.method == Method.DESCRIPTIVE
    assert "kausal" in " ".join(d.assumptions_required).lower()


def test_srm_detected_and_flagged():
    """Rasio 60/40 saat desain 50/50 → SRM harus kepegang & confidence anjlok."""
    rng = np.random.default_rng(0)
    n0, n1 = 6_000, 4_000
    df = pd.DataFrame(
        {
            "group": np.array([0] * n0 + [1] * n1),
            "pre_metric": rng.normal(0, 1, n0 + n1),
            "converted": rng.integers(0, 2, n0 + n1),
        }
    )
    srm = sample_ratio_mismatch(df, "group", expected_ratio=0.5)
    assert srm["srm_detected"] is True

    roles = ColumnRoles(treatment="group", outcome="converted", covariates=["pre_metric"])
    d = route(df, roles, DeclaredType.RANDOMIZED, expected_ratio=0.5)
    assert d.method == Method.AB_TEST
    assert d.confidence <= 0.5
    assert any("SRM" in r for r in d.reasons)


def test_multi_arm_rejected():
    truth = make_ab_binary(n_per_arm=300, seed=2)
    df = truth.df.copy()
    df.loc[df.index[:100], "group"] = 2  # arm ketiga
    roles = ColumnRoles(treatment="group", outcome="converted")
    with pytest.raises(ValueError, match="arm"):
        route(df, roles)


def test_missing_outcome_rejected():
    truth = make_ab_binary(n_per_arm=100, seed=2)
    with pytest.raises(ValueError, match="outcome"):
        route(truth.df, ColumnRoles(treatment="group", outcome="tidak_ada"))
