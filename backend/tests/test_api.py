"""Acceptance T4.1 — FastAPI endpoints + SSE.

Semua test pakai ReactLoop ber-LLM scripted (di-inject via dependency override) —
TIDAK menyentuh Gemini live. Hanya inspect_schema (DuckDB) + verify (DuckDB) yang jalan,
jadi tak butuh Docker.

Acceptance utama: /analyze mengalirkan event berurutan; /run/{id} mengembalikan run tersimpan.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.agent.react_loop import ReactLoop
from app.api.deps import get_react_loop
from app.core.schemas import AnalysisResult, Scorecard
from app.db import repository
from app.db.session import configure_database, create_tables
from app.main import app


# ── LLM scripted (tanpa Gemini) ──────────────────────────────────────────────


class ScriptedLLM:
    """Balas plan untuk prompt planner, lalu aksi sesuai antrian untuk loop."""

    def __init__(self, actions: list[dict]):
        self._actions = list(actions)

    def __call__(self, prompt: str) -> str:
        if "perencana" in prompt:
            return json.dumps(
                [
                    {"description": "inspect schema", "tool": "inspect_schema"},
                    {"description": "hitung", "tool": "write_and_execute"},
                ]
            )
        if self._actions:
            return json.dumps(self._actions.pop(0))
        return json.dumps({"final": "fallback", "code": ""})


def _scripted_loop() -> ReactLoop:
    """Loop yang: inspect_schema → final (dengan key_value + verify_sql)."""
    llm = ScriptedLLM(
        [
            {"thought": "lihat skema", "action": "inspect_schema", "args": {}},
            {
                "final": "Total Sales = **$2,297,200.86**",
                "code": "df['Sales'].sum()",
                "key_value": 2297200.86,
                "verify_sql": 'SELECT SUM("Sales") FROM t',
            },
        ]
    )
    return ReactLoop(generate=llm)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_sse(text: str) -> list[tuple[str | None, dict | None]]:
    """Parse text/event-stream → list (event_type, data_dict)."""
    events: list[tuple[str | None, dict | None]] = []
    for frame in text.strip().split("\n\n"):
        if not frame.strip():
            continue
        etype: str | None = None
        data: str | None = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                etype = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((etype, json.loads(data) if data else None))
    return events


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    """TestClient dengan DB sementara + ReactLoop scripted."""
    db_file = tmp_path / "api_test.db"
    configure_database(f"sqlite:///{db_file.as_posix()}")
    create_tables()
    app.dependency_overrides[get_react_loop] = _scripted_loop
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        configure_database(None)


# ── GET /datasets ─────────────────────────────────────────────────────────────


def test_datasets_endpoint(client):
    resp = client.get("/datasets")
    assert resp.status_code == 200
    data = resp.json()
    ids = [d["dataset_id"] for d in data]
    assert "superstore" in ids
    sup = next(d for d in data if d["dataset_id"] == "superstore")
    assert sup["file"] == "superstore.csv"
    assert sup["encoding"] == "latin-1"


# ── POST /analyze (SSE) ───────────────────────────────────────────────────────


def test_analyze_streams_events_in_order(client):
    resp = client.post(
        "/analyze", json={"question": "Berapa total penjualan?", "dataset_id": "superstore"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    types = [t for t, _ in events]

    # Urutan inti: intent (kontrak D2) → plan, final terakhir.
    assert types[0] == "intent"
    assert types[1] == "plan"
    assert types[-1] == "final"
    # Tool dieksekusi.
    assert "step" in types and "tool" in types
    # key_value + verify_sql → verify & confidence muncul sebelum final.
    assert "verify" in types and "confidence" in types
    assert types.index("verify") < types.index("confidence") < types.index("final")


def test_analyze_final_event_has_bundle(client):
    resp = client.post(
        "/analyze", json={"question": "Total penjualan?", "dataset_id": "superstore"}
    )
    events = _parse_sse(resp.text)
    final = next(d for t, d in events if t == "final")
    assert "2,297,200.86" in final["answer_markdown"]
    assert final["run_id"].startswith("run_")
    assert final["confidence"] is not None
    assert final["verification"] is not None and final["verification"]["passed"] is True


def test_analyze_unknown_dataset_404(client):
    resp = client.post("/analyze", json={"question": "x", "dataset_id": "tidak_ada"})
    assert resp.status_code == 404


# ── GET /run/{id} ─────────────────────────────────────────────────────────────


def test_analyze_persists_run_retrievable(client):
    resp = client.post(
        "/analyze", json={"question": "Berapa total penjualan?", "dataset_id": "superstore"}
    )
    events = _parse_sse(resp.text)
    run_id = next(d for t, d in events if t == "final")["run_id"]

    r2 = client.get(f"/run/{run_id}")
    assert r2.status_code == 200
    rec = r2.json()
    assert rec["run_id"] == run_id
    assert rec["dataset_id"] == "superstore"
    assert "2,297,200.86" in rec["answer_markdown"]
    assert rec["created_at"] is not None


def test_run_not_found_404(client):
    resp = client.get("/run/run_tidak_ada")
    assert resp.status_code == 404


def test_runs_list_includes_persisted(client):
    resp = client.post(
        "/analyze", json={"question": "Total penjualan?", "dataset_id": "superstore"}
    )
    run_id = next(d for t, d in _parse_sse(resp.text) if t == "final")["run_id"]

    r2 = client.get("/runs")
    assert r2.status_code == 200
    runs = r2.json()
    assert any(run["run_id"] == run_id for run in runs)


# ── GET /artifacts/{subdir}/{filename} ────────────────────────────────────────


def test_artifact_rejects_non_png(client):
    resp = client.get("/artifacts/somedir/data.txt")
    assert resp.status_code == 400


def test_artifact_not_found(client):
    resp = client.get("/artifacts/nonexistent/chart.png")
    assert resp.status_code == 404


# ── GET /eval/dashboard ───────────────────────────────────────────────────────


def test_eval_dashboard_aggregates(client):
    # Seed: run + scorecard langsung ke DB.
    res = AnalysisResult(
        run_id="run_seed", answer_markdown="x", code="", dataset_id="superstore"
    )
    repository.save_run(res, question="q")
    repository.save_scorecard(
        Scorecard(
            run_id="run_seed",
            question_id="q001",
            correctness=1.0,
            cost_usd=0.001,
            tool_calls=2,
            time_to_insight=2.0,
            hallucination_flag=False,
            verification_accuracy=1.0,
        )
    )
    resp = client.get("/eval/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total"] == 1
    assert data["summary"]["avg_correctness"] == 1.0
    assert len(data["recent"]) == 1
    assert data["recent"][0]["run_id"] == "run_seed"


def test_eval_dashboard_empty(client):
    resp = client.get("/eval/dashboard")
    assert resp.status_code == 200
    assert resp.json()["summary"]["total"] == 0


# ── Error handling ────────────────────────────────────────────────────────────


def test_analyze_emits_error_event(tmp_path):
    """Kalau loop.run() melempar exception → stream kirim event 'error', tak crash."""
    db_file = tmp_path / "err.db"
    configure_database(f"sqlite:///{db_file.as_posix()}")
    create_tables()

    class _BoomLoop:
        def run(self, *_a, **_k):
            raise RuntimeError("Gemini quota habis")

    app.dependency_overrides[get_react_loop] = lambda: _BoomLoop()
    try:
        c = TestClient(app)
        resp = c.post(
            "/analyze", json={"question": "x", "dataset_id": "superstore"}
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        types = [t for t, _ in events]
        assert "error" in types
        err = next(d for t, d in events if t == "error")
        assert "quota" in err["message"].lower()
    finally:
        app.dependency_overrides.clear()
        configure_database(None)


# ── Live smoke test (di-skip; jalankan manual pas kuota Gemini ada) ───────────


@pytest.mark.skipif(
    os.getenv("RUN_LIVE") != "1",
    reason="live Gemini + Docker — set RUN_LIVE=1 untuk jalankan manual",
)
def test_analyze_live_smoke():  # pragma: no cover - butuh API key + kuota
    configure_database(None)
    create_tables()
    app.dependency_overrides.clear()  # pakai loop live (Gemini asli)
    c = TestClient(app)
    resp = c.post(
        "/analyze", json={"question": "Berapa total penjualan?", "dataset_id": "superstore"}
    )
    assert resp.status_code == 200
    types = [t for t, _ in _parse_sse(resp.text)]
    assert types[0] == "plan" and types[-1] == "final"
