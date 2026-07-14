"""Acceptance jalur deploy — sandbox via SUBPROCESS (USE_DOCKER=false).

Tidak butuh Docker → menutupi path yang dipakai di Render. Menguji:
- kode pandas normal balikin output
- kode matplotlib menghasilkan PNG (memvalidasi fix env: MPLCONFIGDIR + var sistem)
- secret (GEMINI_API_KEY) TIDAK bocor ke env subprocess
- timeout tidak nge-hang
"""

from __future__ import annotations

import os

from app.core.config import PROJECT_ROOT
from app.sandbox.runner import _run_subprocess

DATASET = str(PROJECT_ROOT / "datasets" / "superstore.csv")


def test_subprocess_normal_output():
    code = (
        "import pandas as pd\n"
        "df = pd.read_csv(DATASET_PATH, encoding='latin-1')\n"
        "print('rows', df.shape[0])\n"
    )
    res = _run_subprocess(code, DATASET, timeout=60)
    assert res.ok, res.stderr
    assert res.backend == "subprocess"
    assert "9994" in res.stdout


def test_subprocess_matplotlib_chart():
    code = (
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [3, 1, 2])\n"
        "plt.savefig('chart.png')\n"
        "print('charted')\n"
    )
    res = _run_subprocess(code, DATASET, timeout=60)
    assert res.ok, res.stderr
    assert res.chart_paths, "harus ada PNG"
    assert all(os.path.exists(p) for p in res.chart_paths)
    import shutil

    for p in res.chart_paths:
        shutil.rmtree(os.path.dirname(p), ignore_errors=True)


def test_subprocess_does_not_leak_secret(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET_SHOULD_NOT_LEAK")
    code = (
        "import os\n"
        "print('KEY=' + os.environ.get('GEMINI_API_KEY', 'ABSENT'))\n"
    )
    res = _run_subprocess(code, DATASET, timeout=60)
    assert res.ok, res.stderr
    assert "ABSENT" in res.stdout
    assert "SECRET_SHOULD_NOT_LEAK" not in res.stdout


def test_subprocess_timeout_does_not_hang():
    res = _run_subprocess("while True:\n    pass\n", DATASET, timeout=3)
    assert res.timed_out is True
    assert not res.ok
