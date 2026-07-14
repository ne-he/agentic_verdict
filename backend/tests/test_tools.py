"""Acceptance T1.3 — tiap tool jalan di Superstore CSV, output sesuai bentuk.

inspect_schema murni DuckDB (tak butuh Docker). write_and_execute & make_chart butuh sandbox;
di-skip otomatis bila Docker tidak tersedia.
"""

import json

import docker
import pytest

from app.agent.tools import build_default_registry

DATASET = "superstore"


def _docker_ready() -> bool:
    try:
        docker.from_env().ping()
        docker.from_env().images.get("analyst-sandbox:latest")
        return True
    except Exception:
        return False


needs_docker = pytest.mark.skipif(
    not _docker_ready(), reason="Docker / image analyst-sandbox tidak tersedia"
)


def test_registry_has_six_tools():
    # 3 deskriptif (ANALYST) + 3 kausal (VERDICT) — BLUEPRINT D6.
    reg = build_default_registry()
    assert set(reg.names()) == {
        "inspect_schema", "write_and_execute", "make_chart",
        "causal_route", "causal_analyze", "causal_refute",
    }


def test_function_declarations_shape():
    reg = build_default_registry()
    decls = reg.function_declarations()
    assert len(decls) == 6
    for d in decls:
        assert {"name", "description", "parameters"} <= set(d)
        assert d["parameters"]["type"] == "object"


def test_inspect_schema_superstore():
    reg = build_default_registry()
    res = reg.get("inspect_schema").run(dataset_id=DATASET)
    assert res.ok, res.error
    payload = json.loads(res.output)
    assert payload["n_rows"] == 9994
    assert payload["n_columns"] == 21
    names = [c["name"] for c in payload["columns"]]
    assert "Sales" in names and "Region" in names
    assert len(payload["sample_rows"]) == 5


@needs_docker
def test_write_and_execute_total_sales():
    reg = build_default_registry()
    res = reg.get("write_and_execute").run(
        dataset_id=DATASET, code="print(round(df['Sales'].sum(), 2))"
    )
    assert res.ok, res.error
    assert "2297200.86" in res.output


@needs_docker
def test_write_and_execute_reports_error():
    reg = build_default_registry()
    res = reg.get("write_and_execute").run(
        dataset_id=DATASET, code="print(df['KolomNgaco'].sum())"
    )
    assert not res.ok
    assert res.error  # KeyError ke-capture sebagai observasi


@needs_docker
def test_make_chart_returns_png():
    reg = build_default_registry()
    res = reg.get("make_chart").run(
        dataset_id=DATASET,
        code="import matplotlib.pyplot as plt\ndf.groupby('Region')['Sales'].sum().plot.bar()\nplt.savefig('chart.png')",
    )
    assert res.ok, res.error
    assert any(p.endswith(".png") for p in res.chart_paths)
    import os
    import shutil

    for p in res.chart_paths:
        shutil.rmtree(os.path.dirname(p), ignore_errors=True)
