"""Generate datasets/ab_marketing.csv + ab_marketing.meta.json (BLUEPRINT D9).

Dataset demo money-shot: eksperimen A/B sintetik dengan TRUE LIFT yang diketahui.
Demo: tanya "apakah kampanye ini menaikkan konversi?" → agent recover true lift
dalam CI → tunjukkan meta.json sebagai bukti. Reproducible (seed fix).

Jalankan dari backend/:  python scripts/generate_demo_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.causal_synthetic.dgp_ab import make_ab_binary  # noqa: E402

N_PER_ARM = 10_000
BASELINE = 0.10
TRUE_LIFT = 0.02
SEED = 42

COLUMN_RENAME = {"group": "variant", "pre_metric": "pre_engagement", "converted": "converted"}


def main() -> None:
    datasets_dir = Path(__file__).resolve().parents[2] / "datasets"
    datasets_dir.mkdir(exist_ok=True)

    truth = make_ab_binary(
        n_per_arm=N_PER_ARM, baseline_rate=BASELINE, true_lift_absolute=TRUE_LIFT, seed=SEED
    )
    df = truth.df.rename(columns=COLUMN_RENAME)
    csv_path = datasets_dir / "ab_marketing.csv"
    df.to_csv(csv_path, index=False)

    meta = {
        "description": (
            "Eksperimen A/B marketing SINTETIK — dibuat dari DGP dengan ground-truth "
            "yang diketahui, untuk membuktikan engine kausal me-recover efek sebenarnya."
        ),
        "generator": "backend/tests/causal_synthetic/dgp_ab.py :: make_ab_binary",
        "seed": SEED,
        "n_per_arm": N_PER_ARM,
        "columns": {
            "variant": "assignment acak 50/50 (0=control, 1=treatment)",
            "pre_engagement": "metrik pre-period (untuk CUPED / cek balance)",
            "converted": "outcome biner (1=konversi)",
        },
        "ground_truth": {
            "baseline_conversion_rate": BASELINE,
            "true_lift_absolute": TRUE_LIFT,
            "true_treatment_rate": BASELINE + TRUE_LIFT,
        },
        "expected_roles": {
            "treatment": "variant",
            "outcome": "converted",
            "covariates": ["pre_engagement"],
        },
    }
    meta_path = datasets_dir / "ab_marketing.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK: {csv_path} ({len(df):,} baris) + {meta_path}")


if __name__ == "__main__":
    main()
