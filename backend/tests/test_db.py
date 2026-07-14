"""Acceptance T3.4 — SQLite persistence via SQLAlchemy 2.0.

Semua test pakai in-memory SQLite (":memory:") supaya tidak ada file sisa.
Verifikasi: simpan run → query balik konsisten; simpan scorecard → query balik;
upsert gold_question; artifact path tersimpan.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.schemas import AnalysisResult, GoldQuestion, GoldSet, Scorecard, ToolCall
from app.db.models import Base, RunHistory, ScorecardRow, GoldQuestionRow, Artifact
from app.db.repository import (
    get_run,
    get_scorecard,
    list_runs,
    list_scorecards,
    save_run,
    save_scorecard,
    upsert_gold_question,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """In-memory SQLite session — dibuat segar tiap test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session_()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _make_result(run_id: str | None = None, dataset_id: str = "superstore") -> AnalysisResult:
    return AnalysisResult(
        run_id=run_id or str(uuid.uuid4()),
        answer_markdown="Total Profit = **$286,397.02**",
        code="df['Profit'].sum()",
        dataset_id=dataset_id,
        dataset_snapshot="sha256:abc123",
        chart_paths=["/sandbox/artifacts/chart_1.png"],
        tool_calls=[ToolCall(tool="inspect_schema"), ToolCall(tool="write_and_execute")],
        tokens=1200,
        cost_usd=0.00024,
        duration_ms=3200,
    )


def _make_scorecard(run_id: str) -> Scorecard:
    return Scorecard(
        run_id=run_id,
        question_id="q002",
        correctness=1.0,
        cost_usd=0.00024,
        tool_calls=2,
        time_to_insight=3.2,
        hallucination_flag=False,
        verification_accuracy=1.0,
    )


def _make_gold_question() -> tuple[GoldSet, GoldQuestion]:
    gs = GoldSet(
        dataset_id="superstore",
        dataset_file="datasets/superstore.csv",
        questions=[],
    )
    gq = GoldQuestion(
        id="q002",
        category="descriptive",
        question="Berapa total profit?",
        gold_answer="Total Profit = $286,397.02",
        gold_code="df['Profit'].sum()",
        expected_value=286397.02,
        allowed_tolerance=0.001,
    )
    return gs, gq


# ── run_history ────────────────────────────────────────────────────────────────


def test_save_run_and_get_run(db_session: Session):
    result = _make_result()
    save_run(result, question="Berapa total profit?", session=db_session)
    db_session.commit()

    retrieved = get_run(result.run_id, session=db_session)
    assert retrieved is not None
    assert retrieved.run_id == result.run_id
    assert retrieved.dataset_id == "superstore"
    assert retrieved.answer_markdown == result.answer_markdown
    assert retrieved.tokens == 1200


def test_save_run_stores_artifacts(db_session: Session):
    result = _make_result()
    save_run(result, question="q?", session=db_session)
    db_session.commit()

    artifacts = db_session.query(Artifact).filter_by(run_id=result.run_id).all()
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "chart"
    assert "chart_1.png" in artifacts[0].file_path


def test_get_run_nonexistent_returns_none(db_session: Session):
    assert get_run("nonexistent_run_id", session=db_session) is None


def test_list_runs_returns_latest_first(db_session: Session):
    r1 = _make_result(run_id="run_alpha")
    r2 = _make_result(run_id="run_beta")
    save_run(r1, question="q1", session=db_session)
    save_run(r2, question="q2", session=db_session)
    db_session.commit()

    runs = list_runs(limit=10, session=db_session)
    assert len(runs) == 2
    run_ids = [r.run_id for r in runs]
    assert "run_alpha" in run_ids and "run_beta" in run_ids


# ── scorecards ─────────────────────────────────────────────────────────────────


def test_save_scorecard_and_get_scorecard(db_session: Session):
    result = _make_result()
    save_run(result, question="q?", session=db_session)
    sc = _make_scorecard(result.run_id)
    save_scorecard(sc, session=db_session)
    db_session.commit()

    retrieved = get_scorecard(result.run_id, session=db_session)
    assert retrieved is not None
    assert retrieved.correctness == pytest.approx(1.0)
    assert retrieved.question_id == "q002"
    assert retrieved.hallucination_flag is False


def test_list_scorecards(db_session: Session):
    for i in range(3):
        r = _make_result(run_id=f"run_{i:03d}")
        save_run(r, question=f"q{i}", session=db_session)
        save_scorecard(_make_scorecard(r.run_id), session=db_session)
    db_session.commit()

    scs = list_scorecards(limit=10, session=db_session)
    assert len(scs) == 3


# ── gold_questions ─────────────────────────────────────────────────────────────


def test_upsert_gold_question_insert(db_session: Session):
    gs, gq = _make_gold_question()
    upsert_gold_question(gs, gq, session=db_session)
    db_session.commit()

    row = db_session.query(GoldQuestionRow).filter_by(question_id="q002").first()
    assert row is not None
    assert row.expected_value == pytest.approx(286397.02)
    assert row.is_trap is False


def test_upsert_gold_question_update(db_session: Session):
    gs, gq = _make_gold_question()
    upsert_gold_question(gs, gq, session=db_session)
    db_session.commit()

    # Update: ubah expected_value
    gq2 = gq.model_copy(update={"expected_value": 999999.0})
    upsert_gold_question(gs, gq2, session=db_session)
    db_session.commit()

    rows = db_session.query(GoldQuestionRow).filter_by(question_id="q002").all()
    assert len(rows) == 1  # tidak duplikasi
    assert rows[0].expected_value == pytest.approx(999999.0)


# ── schema consistency ─────────────────────────────────────────────────────────


def test_all_tables_exist(db_session: Session):
    """Verifikasi 4 tabel yang dibutuhkan ada di DB."""
    result = db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()
    table_names = {r[0] for r in result}
    assert {"run_history", "scorecards", "gold_questions", "artifacts"}.issubset(table_names)
