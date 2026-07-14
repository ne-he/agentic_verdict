"""
DGP efek heterogen — effect = f(segment). CATE engine harus me-recover pola ini.

Di sini: efek besar untuk segmen 'new users', kecil/nol untuk 'power users'.
Causal forest harus menunjukkan CATE tinggi di segmen pertama.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HeteroTruth:
    df: pd.DataFrame
    effect_new_users: float
    effect_power_users: float


def make_heterogeneous(
    n: int = 12_000,
    effect_new_users: float = 6.0,
    effect_power_users: float = 0.5,
    seed: int = 33,
) -> HeteroTruth:
    rng = np.random.default_rng(seed)

    is_new = rng.integers(0, 2, n)           # 1 = new user
    usage = rng.normal(10, 4, n)             # kovariat tambahan
    treatment = rng.integers(0, 2, n)        # acak (clean) — fokus ke heterogenitas

    tau = np.where(is_new == 1, effect_new_users, effect_power_users)
    outcome = 30 + 1.2 * usage + tau * treatment + rng.normal(0, 4, n)

    df = pd.DataFrame(
        {"is_new_user": is_new, "usage": usage, "treatment": treatment, "outcome": outcome}
    )
    return HeteroTruth(
        df=df, effect_new_users=effect_new_users, effect_power_users=effect_power_users
    )
