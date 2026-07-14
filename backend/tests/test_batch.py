"""Acceptance T3.3 — Batch eval runner.

Test pakai injectable run_fn (mock, tanpa Gemini/Docker) supaya cepat dan gratis.
Verifikasi: semua pertanyaan diproses, agregat benar, save_fn dipanggil tiap run.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.schemas import AnalysisResult, BatchSummary
from app.eval.run_batch import run_batch


# ── Fake run_fn ───────────────────────────────────────────────────────────────


def _make_run_fn(answer: str = "Total = 286397.02", cost: float = 0.001, n_tools: int = 2):
    """Fake run_fn yang selalu balik AnalysisResult dengan jawaban yang sama."""
    from app.core.schemas import ToolCall

    def _run(question: str, dataset_id: str) -> AnalysisResult:
        return AnalysisResult(
            run_id=str(uuid.uuid4()),
            answer_markdown=answer,
            code="df['Profit'].sum()",
            dataset_id=dataset_id,
            tool_calls=[ToolCall(tool="inspect_schema") for _ in range(n_tools)],
            cost_usd=cost,
            duration_ms=500,
        )

    return _run


def _error_run_fn(question: str, dataset_id: str) -> AnalysisResult:
    raise RuntimeError("Gemini timeout")


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_batch_processes_all_gold_questions():
    """Batch memproses semua 20 gold questions dari superstore.json."""
    calls: list[tuple[str, str]] = []

    def tracking_run(question: str, dataset_id: str) -> AnalysisResult:
        calls.append((question, dataset_id))
        return _make_run_fn()(question, dataset_id)

    summary = run_batch(run_fn=tracking_run, verbose=False)
    assert summary.total == 20
    assert len(calls) == 20


def test_batch_summary_fields():
    """BatchSummary punya semua field dengan tipe benar."""
    summary = run_batch(run_fn=_make_run_fn("Total = 999.99", cost=0.002), verbose=False)
    assert isinstance(summary, BatchSummary)
    assert summary.total == 20
    assert 0.0 <= summary.avg_correctness <= 1.0
    assert summary.total_cost_usd == pytest.approx(0.002 * 20)
    assert 0.0 <= summary.hallucination_rate <= 1.0
    assert len(summary.run_ids) == 20


def test_batch_max_questions():
    """--max-questions membatasi jumlah pertanyaan yang diproses."""
    summary = run_batch(run_fn=_make_run_fn(), max_questions=5, verbose=False)
    assert summary.total == 5


def test_batch_save_fn_called_per_question():
    """save_fn dipanggil satu kali per pertanyaan."""
    saved = []
    run_batch(run_fn=_make_run_fn(), save_fn=saved.append, verbose=False)
    assert len(saved) == 20
    # Tiap item adalah Scorecard
    from app.core.schemas import Scorecard
    for sc in saved:
        assert isinstance(sc, Scorecard)


def test_batch_handles_run_error_gracefully():
    """Bila run_fn throw exception, batch lanjut (tidak crash) dan correctness=0."""
    summary = run_batch(run_fn=_error_run_fn, verbose=False)
    assert summary.total == 20
    # Semua error → correctness 0 (atau neutral 0.5 karena no number)
    assert summary.avg_correctness <= 0.5


def test_batch_custom_gold_dir(tmp_path: Path):
    """Batch bisa pakai gold_dir kustom."""
    import json

    gold_data = {
        "dataset_id": "superstore",
        "dataset_file": "datasets/superstore.csv",
        "encoding": "latin-1",
        "questions": [
            {
                "id": "t001",
                "category": "descriptive",
                "question": "Berapa total Sales?",
                "gold_answer": "Total = $2,297,200.86",
                "gold_code": "df['Sales'].sum()",
                "expected_value": 2297200.86,
                "allowed_tolerance": 0.001,
            }
        ],
    }
    (tmp_path / "test.json").write_text(json.dumps(gold_data), encoding="utf-8")
    summary = run_batch(
        gold_dir=tmp_path,
        run_fn=_make_run_fn("Total Sales = $2,297,200.86"),
        verbose=False,
    )
    assert summary.total == 1
    assert summary.avg_correctness == pytest.approx(1.0)
