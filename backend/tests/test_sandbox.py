"""Acceptance T1.2 — sandbox runner (Docker).

Butuh Docker Desktop jalan + image analyst-sandbox ter-build.
Test di-skip otomatis kalau Docker tidak tersedia.
"""

import os
import shutil

import docker
import pytest

from app.core.config import PROJECT_ROOT
from app.sandbox.runner import run_code

DATASET = str(PROJECT_ROOT / "datasets" / "superstore.csv")


def _docker_ready() -> bool:
    try:
        docker.from_env().ping()
        docker.from_env().images.get("analyst-sandbox:latest")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_ready(), reason="Docker / image analyst-sandbox tidak tersedia"
)


def test_normal_code_returns_output():
    code = "import pandas as pd\ndf = pd.read_csv(DATASET_PATH, encoding='latin-1')\nprint(df.shape)"
    res = run_code(code, DATASET)
    assert res.ok, res.stderr
    assert "9994" in res.stdout  # 9994 baris data


def test_no_network():
    code = "import socket\nsocket.create_connection(('8.8.8.8', 53), timeout=5)\nprint('CONNECTED')"
    res = run_code(code, DATASET)
    assert not res.ok
    assert "CONNECTED" not in res.stdout


def test_timeout_does_not_hang():
    res = run_code("while True:\n    pass", DATASET, timeout_sec=5)
    assert res.timed_out is True
    assert not res.ok


def test_container_auto_removed():
    """Setelah run, tidak ada container analyst-sandbox yang tersisa."""
    run_code("print('hi')", DATASET)
    client = docker.from_env()
    leftover = [
        c
        for c in client.containers.list(all=True)
        if c.image.tags and "analyst-sandbox:latest" in c.image.tags
    ]
    assert leftover == [], f"Container tidak terhapus: {leftover}"


def test_chart_png_collected():
    code = (
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [3, 1, 2])\n"
        "plt.savefig('chart.png')\n"
        "print('charted')"
    )
    res = run_code(code, DATASET)
    assert res.ok, res.stderr
    assert any(p.endswith(".png") for p in res.chart_paths)
    assert all(os.path.exists(p) for p in res.chart_paths)  # PNG persist setelah cleanup
    for p in res.chart_paths:
        shutil.rmtree(os.path.dirname(p), ignore_errors=True)
