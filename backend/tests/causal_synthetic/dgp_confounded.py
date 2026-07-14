"""
DGP observasional dengan CONFOUNDER. True ATE diketahui.

Konstruksi: confounder X mempengaruhi BOTH treatment assignment DAN outcome.
→ naive diff (mean treat - mean control) akan BIAS.
→ PSM/DoWhy harus mendekati true_ate.

Engine M2 divalidasi dengan menunjukkan: |naive - true| >> |psm - true|.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import special


@dataclass
class ConfoundedTruth:
    df: pd.DataFrame
    true_ate: float


def make_confounded(
    n: int = 8_000,
    true_ate: float = 5.0,
    seed: int = 11,
) -> ConfoundedTruth:
    rng = np.random.default_rng(seed)

    # confounders
    age = rng.normal(40, 10, n)
    tenure = rng.normal(3, 1.5, n)

    # treatment assignment tergantung confounders (bukan acak)
    logit = -2.0 + 0.04 * (age - 40) + 0.5 * (tenure - 3)
    p_treat = special.expit(logit)
    treatment = (rng.random(n) < p_treat).astype(int)

    # outcome tergantung confounders + efek treatment konstan (= true_ate)
    outcome = (
        20
        + 0.8 * age
        + 2.0 * tenure
        + true_ate * treatment
        + rng.normal(0, 5, n)
    )

    df = pd.DataFrame(
        {"age": age, "tenure": tenure, "treatment": treatment, "outcome": outcome}
    )
    return ConfoundedTruth(df=df, true_ate=true_ate)


def naive_diff(t: ConfoundedTruth) -> float:
    d = t.df
    return d[d.treatment == 1].outcome.mean() - d[d.treatment == 0].outcome.mean()
