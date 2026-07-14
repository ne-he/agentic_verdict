"""DGP A/B bersih (randomized). True lift diketahui."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ABTruth:
    df: pd.DataFrame
    true_lift_absolute: float   # p1 - p0
    baseline_rate: float        # p0


def make_ab_binary(
    n_per_arm: int = 10_000,
    baseline_rate: float = 0.10,
    true_lift_absolute: float = 0.02,
    seed: int = 42,
) -> ABTruth:
    """Outcome biner. Assignment acak 50/50, tidak ada confounder.

    control: Bernoulli(p0), treatment: Bernoulli(p0 + lift).
    Tambah satu pre-covariate berkorelasi (untuk uji CUPED).
    """
    rng = np.random.default_rng(seed)
    p0, p1 = baseline_rate, baseline_rate + true_lift_absolute

    group = np.array([0] * n_per_arm + [1] * n_per_arm)
    pre = rng.normal(0, 1, size=2 * n_per_arm)          # pre-period covariate
    base_p = np.where(group == 1, p1, p0)
    # outcome sedikit dipengaruhi pre (bikin CUPED ada gunanya), tetap unbiased
    noise = 0.02 * pre
    outcome = (rng.random(2 * n_per_arm) < np.clip(base_p + noise, 0, 1)).astype(int)

    df = pd.DataFrame({"group": group, "pre_metric": pre, "converted": outcome})
    return ABTruth(df=df, true_lift_absolute=true_lift_absolute, baseline_rate=baseline_rate)


def make_ab_continuous(
    n_per_arm: int = 5_000,
    baseline_mean: float = 50.0,
    true_effect: float = 3.0,
    sd: float = 20.0,
    seed: int = 7,
) -> ABTruth:
    rng = np.random.default_rng(seed)
    group = np.array([0] * n_per_arm + [1] * n_per_arm)
    pre = rng.normal(baseline_mean, sd, size=2 * n_per_arm)
    effect = np.where(group == 1, true_effect, 0.0)
    outcome = baseline_mean + effect + 0.6 * (pre - baseline_mean) + rng.normal(0, sd * 0.5, 2 * n_per_arm)
    df = pd.DataFrame({"group": group, "pre_metric": pre, "revenue": outcome})
    return ABTruth(df=df, true_lift_absolute=true_effect, baseline_rate=baseline_mean)
