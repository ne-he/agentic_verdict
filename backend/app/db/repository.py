"""Repo layer — simpan & query run_history, scorecards, gold_questions, artifacts (T3.4).

Semua fungsi terima Session opsional (untuk test bisa inject in-memory session).
Bila session=None, buka session baru dari pool lalu tutup otomatis.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.core.schemas import (
    AnalysisResult,
    BatchSummary,
    EvalDashboard,
    GoldQuestion,
    GoldSet,
    RunRecord,
    Scorecard,
)
from app.db.models import Artifact, GoldQuestionRow, RunHistory, ScorecardRow
from app.db.session import create_tables, get_session
from app.eval.metrics import aggregate


@contextmanager
def _session_scope(session: Session | None) -> Generator[Session, None, None]:
    """Context manager: pakai session yang disediakan atau buat baru + tutup otomatis."""
    if session is not None:
        yield session
    else:
        s = get_session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()


# ── Inisialisasi ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """Buat semua tabel (idempotent, panggil sekali saat startup)."""
    create_tables()


# ── run_history ───────────────────────────────────────────────────────────────

def save_run(
    result: AnalysisResult,
    question: str,
    session: Session | None = None,
) -> RunHistory:
    """Simpan AnalysisResult ke run_history. Return ORM row."""
    row = RunHistory(
        run_id=result.run_id,
        dataset_id=result.dataset_id,
        dataset_snapshot=result.dataset_snapshot,
        question=question,
        answer_markdown=result.answer_markdown,
        code=result.code,
        tokens=result.tokens,
        cost_usd=result.cost_usd,
        duration_ms=result.duration_ms,
    )
    with _session_scope(session) as s:
        s.add(row)
        s.flush()
        for path in result.chart_paths:
            s.add(Artifact(run_id=result.run_id, artifact_type="chart", file_path=path))
        if session is None:
            pass  # commit happens in context manager
        else:
            s.flush()
    return row


def get_run(run_id: str, session: Session | None = None) -> RunHistory | None:
    """Query satu run by run_id."""
    with _session_scope(session) as s:
        return s.get(RunHistory, run_id) or s.query(RunHistory).filter_by(run_id=run_id).first()


def list_runs(limit: int = 50, session: Session | None = None) -> list[RunHistory]:
    """Query run_history terbaru (urut created_at DESC)."""
    with _session_scope(session) as s:
        return (
            s.query(RunHistory)
            .order_by(RunHistory.created_at.desc())
            .limit(limit)
            .all()
        )


def list_run_records(limit: int = 50, session: Session | None = None) -> list[RunRecord]:
    """Daftar run terbaru sebagai RunRecord (untuk halaman History). Tanpa chart_paths (ringan)."""
    with _session_scope(session) as s:
        rows = (
            s.query(RunHistory)
            .order_by(RunHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            RunRecord(
                run_id=r.run_id,
                dataset_id=r.dataset_id,
                dataset_snapshot=r.dataset_snapshot,
                question=r.question,
                answer_markdown=r.answer_markdown,
                code=r.code,
                tokens=r.tokens,
                cost_usd=r.cost_usd,
                duration_ms=r.duration_ms,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ]


def get_run_record(run_id: str, session: Session | None = None) -> RunRecord | None:
    """Ambil satu run sebagai RunRecord (schema API), konversi di dalam session.

    Mengembalikan objek lepas (detached-safe) supaya aman dipakai setelah session ditutup.
    """
    with _session_scope(session) as s:
        row = s.query(RunHistory).filter_by(run_id=run_id).first()
        if row is None:
            return None
        charts = [
            a.file_path
            for a in s.query(Artifact)
            .filter_by(run_id=run_id, artifact_type="chart")
            .all()
        ]
        return RunRecord(
            run_id=row.run_id,
            dataset_id=row.dataset_id,
            dataset_snapshot=row.dataset_snapshot,
            question=row.question,
            answer_markdown=row.answer_markdown,
            code=row.code,
            tokens=row.tokens,
            cost_usd=row.cost_usd,
            duration_ms=row.duration_ms,
            chart_paths=charts,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )


# ── scorecards ────────────────────────────────────────────────────────────────

def save_scorecard(sc: Scorecard, session: Session | None = None) -> ScorecardRow:
    """Simpan Scorecard ke tabel scorecards. Return ORM row."""
    row = ScorecardRow(
        run_id=sc.run_id,
        question_id=sc.question_id,
        correctness=sc.correctness,
        cost_usd=sc.cost_usd,
        tool_calls=sc.tool_calls,
        time_to_insight=sc.time_to_insight,
        hallucination_flag=sc.hallucination_flag,
        verification_accuracy=sc.verification_accuracy,
    )
    with _session_scope(session) as s:
        s.add(row)
        if session is not None:
            s.flush()
    return row


def get_scorecard(run_id: str, session: Session | None = None) -> ScorecardRow | None:
    """Query scorecard by run_id."""
    with _session_scope(session) as s:
        return s.query(ScorecardRow).filter_by(run_id=run_id).first()


def list_scorecards(limit: int = 100, session: Session | None = None) -> list[ScorecardRow]:
    """Query scorecard terbaru."""
    with _session_scope(session) as s:
        return (
            s.query(ScorecardRow)
            .order_by(ScorecardRow.created_at.desc())
            .limit(limit)
            .all()
        )


def get_eval_dashboard(limit: int = 50, session: Session | None = None) -> EvalDashboard:
    """Bangun EvalDashboard: agregat metrik + N scorecard terbaru (failure dashboard)."""
    with _session_scope(session) as s:
        rows = (
            s.query(ScorecardRow)
            .order_by(ScorecardRow.created_at.desc())
            .limit(limit)
            .all()
        )
        cards = [
            Scorecard(
                run_id=r.run_id,
                question_id=r.question_id,
                correctness=r.correctness,
                cost_usd=r.cost_usd,
                tool_calls=r.tool_calls,
                time_to_insight=r.time_to_insight,
                hallucination_flag=r.hallucination_flag,
                verification_accuracy=r.verification_accuracy,
            )
            for r in rows
        ]
    summary: BatchSummary = aggregate(cards)
    return EvalDashboard(summary=summary, recent=cards)


# ── gold_questions ────────────────────────────────────────────────────────────

def upsert_gold_question(
    gs: GoldSet,
    q: GoldQuestion,
    session: Session | None = None,
) -> GoldQuestionRow:
    """Insert atau update satu GoldQuestion ke DB (by question_id)."""
    with _session_scope(session) as s:
        row = s.query(GoldQuestionRow).filter_by(question_id=q.id).first()
        if row is None:
            row = GoldQuestionRow(question_id=q.id)
            s.add(row)
        row.dataset_id = gs.dataset_id
        row.category = q.category
        row.question = q.question
        row.gold_answer = q.gold_answer
        row.expected_value = q.expected_value
        row.allowed_tolerance = q.allowed_tolerance
        row.is_trap = q.is_trap
        if session is not None:
            s.flush()
    return row
