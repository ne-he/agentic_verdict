"""
DGP time-series dengan step-intervention diketahui.

Deret pra-intervensi mengikuti tren + musiman + 1 kovariat control.
Pada intervention_index, ditambah lift konstan. CausalImpact harus me-recover-nya.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TSTruth:
    df: pd.DataFrame
    intervention_index: int
    true_effect_per_period: float


def make_timeseries(
    n_periods: int = 180,
    intervention_index: int = 120,
    true_effect_per_period: float = 8.0,
    seed: int = 21,
) -> TSTruth:
    rng = np.random.default_rng(seed)
    t = np.arange(n_periods)

    control = 50 + 0.1 * t + 5 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 2, n_periods)
    # y berkorelasi kuat dgn control (synthetic control bisa belajar dari ini)
    y = 0.9 * control + rng.normal(0, 2, n_periods)
    y[intervention_index:] += true_effect_per_period  # efek mulai di sini

    dates = pd.date_range("2025-01-01", periods=n_periods, freq="D")
    df = pd.DataFrame({"date": dates, "y": y, "control_series": control})
    return TSTruth(
        df=df,
        intervention_index=intervention_index,
        true_effect_per_period=true_effect_per_period,
    )
