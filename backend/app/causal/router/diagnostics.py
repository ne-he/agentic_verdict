"""
Diagnostik struktur data untuk router. (Port dari VERDICT, tanpa perubahan logika.)

Dua diagnostik inti:
- SMD (standardized mean difference): seberapa tidak-seimbang kovariat antar arm.
  |SMD| < 0.1 = seimbang (rule of thumb), tanda assignment plausibel acak.
- SRM (sample ratio mismatch): apakah rasio sampel meleset dari desain.
  SRM terdeteksi = hasil A/B BUSUK, harus di-flag merah sebelum apa-apa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

MAX_CATEGORICAL_LEVELS = 10  # level kategorikal terbanyak yang di-one-hot untuk SMD


def _smd_pair(x0: pd.Series, x1: pd.Series) -> float:
    m0, m1 = x0.mean(), x1.mean()
    s0, s1 = x0.std(ddof=1), x1.std(ddof=1)
    pooled = np.sqrt((s0**2 + s1**2) / 2)
    return float((m1 - m0) / pooled) if pooled > 0 else 0.0


def standardized_mean_diff(
    df: pd.DataFrame, treatment_col: str, covariates: list[str]
) -> dict[str, float]:
    """SMD tiap kovariat antara dua arm (asumsi treatment biner 0/1).

    SMD = (mean_treat - mean_control) / pooled_sd.
    Kovariat kategorikal di-one-hot per level (indikator 0/1) — imbalance pada
    kategori (mis. platform, region) sama bahayanya dengan imbalance numerik.
    """
    groups = sorted(df[treatment_col].dropna().unique())
    if len(groups) != 2:
        # >2 arm: hitung SMD thd arm pertama sebagai referensi (disederhanakan).
        groups = groups[:2]
    g0, g1 = groups
    a = df[df[treatment_col] == g0]
    b = df[df[treatment_col] == g1]

    out: dict[str, float] = {}
    for cov in covariates:
        if pd.api.types.is_numeric_dtype(df[cov]):
            out[cov] = _smd_pair(a[cov], b[cov])
        else:
            levels = df[cov].value_counts().index[:MAX_CATEGORICAL_LEVELS]
            for lv in levels:
                out[f"{cov}={lv}"] = _smd_pair(
                    (a[cov] == lv).astype(float), (b[cov] == lv).astype(float)
                )
    return out


def sample_ratio_mismatch(
    df: pd.DataFrame, treatment_col: str, expected_ratio: float | None = None
) -> dict[str, float | bool]:
    """Chi-square goodness-of-fit thd rasio yang diharapkan.

    expected_ratio = proporsi arm pertama (default 0.5 → 50/50).
    p_value < 0.001 → SRM terdeteksi (ambang ketat, standar industri).
    """
    counts = df[treatment_col].value_counts().sort_index()
    n = int(counts.sum())
    k = len(counts)

    if k == 2 and expected_ratio is not None:
        expected = np.array([expected_ratio, 1 - expected_ratio]) * n
    else:
        expected = np.full(k, n / k)  # uniform

    chi2, p = stats.chisquare(f_obs=counts.values, f_exp=expected)
    return {
        "chi2": float(chi2),
        "p_value": float(p),
        "srm_detected": bool(p < 0.001),
        "counts": {str(k_): int(v) for k_, v in counts.items()},
    }


def max_abs_smd(smd: dict[str, float]) -> float:
    return max((abs(v) for v in smd.values()), default=0.0)
