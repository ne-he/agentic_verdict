"""Acceptance T2.3 — chart + reproducible bundle.

PNG kebentuk + bundle lengkap (verification+confidence+snapshot) + re-run kode -> hasil sama.
Bagian sandbox/chart butuh Docker (di-skip otomatis bila tak tersedia).
"""

import os
import shutil

import docker
import pytest

from app.agent.bundle import build_analysis_bundle, dataset_snapshot, rerun_code
from app.agent.tools import build_default_registry
from app.core.schemas import ToolCall, VerificationResult

DATASET = "superstore"


def _docker_ready() -> bool:
    try:
        docker.from_env().ping()
        docker.from_env().images.get("analyst-sandbox:latest")
        return True
    except Exception:
        return False


needs_docker = pytest.mark.skipif(not _docker_ready(), reason="Docker tidak tersedia")


def test_dataset_snapshot_deterministic():
    s1 = dataset_snapshot(DATASET)
    s2 = dataset_snapshot(DATASET)
    assert s1 == s2 and s1.startswith("sha256:")


def test_build_bundle_complete():
    verification = VerificationResult(
        method_a="agent: 2297200.86", method_b="duckdb: 2297200.86",
        agreement=1.0, contradictions=[], passed=True,
    )
    bundle = build_analysis_bundle(
        run_id="run_x",
        dataset_id=DATASET,
        answer_markdown="Total Sales = **$2,297,200.86**",
        code="print(df['Sales'].sum())",
        verification=verification,
        tool_calls=[ToolCall(tool="inspect_schema"), ToolCall(tool="write_and_execute")],
    )
    assert bundle.dataset_id == DATASET
    assert bundle.dataset_snapshot.startswith("sha256:")
    assert bundle.verification is not None and bundle.verification.passed
    assert bundle.confidence is not None and bundle.confidence.label == "HIGH"


@needs_docker
def test_make_chart_then_bundle_has_png():
    reg = build_default_registry()
    res = reg.get("make_chart").run(
        dataset_id=DATASET,
        code="import matplotlib.pyplot as plt\ndf.groupby('Region')['Sales'].sum().plot.bar()\nplt.savefig('chart.png')",
    )
    assert res.ok, res.error
    bundle = build_analysis_bundle(
        run_id="run_chart",
        dataset_id=DATASET,
        answer_markdown="Bar chart sales per region.",
        code="df.groupby('Region')['Sales'].sum()",
        chart_paths=res.chart_paths,
    )
    assert bundle.chart_paths and all(os.path.exists(p) for p in bundle.chart_paths)
    for p in bundle.chart_paths:
        shutil.rmtree(os.path.dirname(p), ignore_errors=True)


@needs_docker
def test_rerun_code_reproducible():
    code = "print(round(df['Sales'].sum(), 2))"
    out1 = rerun_code(code, DATASET)
    out2 = rerun_code(code, DATASET)
    assert out1.ok and out2.ok, (out1.stderr, out2.stderr)
    assert out1.stdout.strip() == out2.stdout.strip()
    assert "2297200.86" in out1.stdout
