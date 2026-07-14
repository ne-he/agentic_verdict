"""
A/B engine — significance + CI + CUPED + power/MDE. (Port dari VERDICT.)

Memilih tes by tipe metrik:
- outcome biner {0,1}      → two-proportion z-test
- outcome kontinu          → Welch's t-test (varians tak sama)

VALIDASI (P2): tests/test_causal_engines.py harus assert engine ini me-recover
true lift dari tests/causal_synthetic/dgp_ab.py dalam CI-nya.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from app.causal.schemas import (
    CausalOptions,
    ColumnRoles,
    EffectEstimate,
    PowerAnalysis,
)

Z = 1.959963984540054  # z_{0.975}


def _is_binary(s: pd.Series) -> bool:
    vals = set(pd.unique(s.dropna()))
    return vals.issubset({0, 1, True, False})


def _arms(df: pd.DataFrame, treatment: str) -> tuple[pd.Series, pd.Series, object, object]:
    groups = sorted(df[treatment].dropna().unique())
    if len(groups) != 2:
        raise ValueError("A/B engine butuh tepat 2 arm (kontrol vs treatment)")
    g0, g1 = groups  # konvensi: terkecil = kontrol
    return df[df[treatment] == g0], df[df[treatment] == g1], g0, g1


def _apply_cuped(df: pd.DataFrame, outcome: str, pre_col: str) -> pd.Series:
    """CUPED: Y_adj = Y - theta*(X - mean(X)), theta = cov(Y,X)/var(X)."""
    y, x = df[outcome].astype(float), df[pre_col].astype(float)
    theta = np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)
    return y - theta * (x - x.mean())


def _two_proportion(c: pd.Series, t: pd.Series, outcome: str) -> EffectEstimate:
    n0, n1 = len(c), len(t)
    p0, p1 = c[outcome].mean(), t[outcome].mean()
    diff = p1 - p0
    p_pool = (c[outcome].sum() + t[outcome].sum()) / (n0 + n1)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n0 + 1 / n1))
    z = diff / se_pool if se_pool > 0 else 0.0
    pval = 2 * stats.norm.sf(abs(z))  # sf lebih presisi dari 1-cdf untuk p kecil
    se_unpool = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    return EffectEstimate(
        point=float(diff),
        ci_low=float(diff - Z * se_unpool),
        ci_high=float(diff + Z * se_unpool),
        relative_lift=float(diff / p0) if p0 > 0 else None,
        p_value=float(pval),
        is_significant=bool(pval < 0.05),
    )


def _welch(c: pd.Series, t: pd.Series, col: str) -> EffectEstimate:
    a, b = t[col].astype(float), c[col].astype(float)
    res = stats.ttest_ind(a, b, equal_var=False)
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    # Welch–Satterthwaite df
    df_w = se**4 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1)
        + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1)
    )
    tcrit = stats.t.ppf(0.975, df_w)
    return EffectEstimate(
        point=float(diff),
        ci_low=float(diff - tcrit * se),
        ci_high=float(diff + tcrit * se),
        relative_lift=float(diff / b.mean()) if b.mean() != 0 else None,
        p_value=float(res.pvalue),
        is_significant=bool(res.pvalue < 0.05),
    )


def _power_mde(c: pd.Series, t: pd.Series, col: str, binary: bool, power: float = 0.8) -> PowerAnalysis:
    """MDE absolut pada N sekarang + N dibutuhkan untuk deteksi efek teramati."""
    n = min(len(c), len(t))
    z_b = stats.norm.ppf(power)
    if binary:
        p_bar = pd.concat([c[col], t[col]]).mean()
        var = p_bar * (1 - p_bar)
        observed = abs(t[col].mean() - c[col].mean())
    else:
        var = pd.concat([c[col], t[col]]).var(ddof=1)
        observed = abs(t[col].mean() - c[col].mean())
    mde = (Z + z_b) * np.sqrt(2 * var / n)
    req_n = ((Z + z_b) ** 2 * 2 * var / observed**2) if observed > 0 else None
    return PowerAnalysis(
        observed_n_per_arm=int(n),
        mde_absolute=float(mde),
        required_n_per_arm=float(req_n) if req_n else None,
        power=power,
    )


def run(df: pd.DataFrame, roles: ColumnRoles, options: CausalOptions) -> dict:
    """Jalankan analisis A/B → dict berisi effect, power, method_specific."""
    outcome = roles.outcome

    # Baris dengan NaN di kolom wajib di-drop (dilaporkan, bukan diam-diam).
    needed = [roles.treatment, outcome]
    if options.cuped and options.cuped_pre_column:
        needed.append(options.cuped_pre_column)
    needed = [c for c in needed if c in df.columns]
    work = df.dropna(subset=needed).copy()
    n_dropped = len(df) - len(work)

    if work[outcome].nunique() < 2:
        raise ValueError("outcome konstan — tidak ada variasi untuk diuji")
    binary = _is_binary(work[outcome])

    cuped_reduction = None
    if options.cuped and options.cuped_pre_column and not binary:
        adj_col = f"{outcome}__cuped"
        work[adj_col] = _apply_cuped(work, outcome, options.cuped_pre_column)
        cuped_reduction = 1 - work[adj_col].var(ddof=1) / work[outcome].var(ddof=1)
        outcome = adj_col

    c, t, g0, g1 = _arms(work, roles.treatment)

    if binary:
        effect = _two_proportion(c, t, outcome)
    else:
        effect = _welch(c, t, outcome)
    power = _power_mde(c, t, outcome, binary)

    return {
        "effect": effect,
        "power": power,
        "method_specific": {
            "metric_type": "binary" if binary else "continuous",
            "control_arm": str(g0),
            "treatment_arm": str(g1),
            "cuped_variance_reduction": float(cuped_reduction) if cuped_reduction else None,
            "n_rows_dropped_missing": int(n_dropped),
        },
    }
