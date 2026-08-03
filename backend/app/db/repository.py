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
from app.db.models import (
    Artifact,
    GoldQuestionRow,
    RunHistory,
    RunStateRow,
    RunStepRow,
    ScorecardRow,
)
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
        termination_reason=result.termination_reason,
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
                termination_reason=r.termination_reason or "completed",
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
            termination_reason=row.termination_reason or "completed",
            chart_paths=charts,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )


# ── durable state (run_states + run_steps) ────────────────────────────────────
#
# Beda dengan run_history yang cuma menyimpan HASIL, dua tabel ini menyimpan
# PROSES: state loop ditulis tiap langkah supaya run yang mati di tengah bisa
# dilanjutkan, bukan diulang dari nol.

def start_run_state(
    *,
    run_id: str,
    question: str,
    dataset_id: str,
    causal_roles_json: str = "",
    intent: str = "descriptive",
    intent_json: str = "",
    plan_json: str = "[]",
    transcript_head: str = "",
    session: Session | None = None,
) -> RunStateRow:
    """Tulis header state run (status="running"). Idempotent terhadap run_id yang sama."""
    with _session_scope(session) as s:
        row = s.query(RunStateRow).filter_by(run_id=run_id).first()
        if row is None:
            row = RunStateRow(run_id=run_id)
            s.add(row)
        row.question = question
        row.dataset_id = dataset_id
        row.causal_roles_json = causal_roles_json
        row.intent = intent
        row.intent_json = intent_json
        row.plan_json = plan_json
        row.transcript_head = transcript_head
        row.status = "running"
        row.termination_reason = ""
        s.flush()
    return row


def append_run_step(
    *,
    run_id: str,
    step_index: int,
    kind: str = "tool",
    tool: str = "",
    input_json: str = "{}",
    output_text: str = "",
    error: str = "",
    chart_paths_json: str = "[]",
    tokens_after: int = 0,
    session: Session | None = None,
) -> RunStepRow:
    """Simpan satu langkah loop + update tokens di header. Commit per langkah (durable)."""
    row = RunStepRow(
        run_id=run_id,
        step_index=step_index,
        kind=kind,
        tool=tool,
        input_json=input_json,
        output_text=output_text,
        error=error,
        chart_paths_json=chart_paths_json,
        tokens_after=tokens_after,
    )
    with _session_scope(session) as s:
        s.add(row)
        state = s.query(RunStateRow).filter_by(run_id=run_id).first()
        if state is not None:
            state.tokens = tokens_after
        s.flush()
    return row


def finish_run_state(
    *,
    run_id: str,
    status: str,
    termination_reason: str,
    tokens: int = 0,
    elapsed_ms: int = 0,
    session: Session | None = None,
) -> None:
    """Tandai run selesai (status="completed"/"failed") + catat alasan terminasi."""
    with _session_scope(session) as s:
        state = s.query(RunStateRow).filter_by(run_id=run_id).first()
        if state is None:
            return
        state.status = status
        state.termination_reason = termination_reason
        state.tokens = tokens
        state.elapsed_ms = elapsed_ms
        s.flush()


def bump_resume_count(run_id: str, session: Session | None = None) -> int:
    """Naikkan penghitung berapa kali run ini di-resume. Return nilai barunya."""
    with _session_scope(session) as s:
        state = s.query(RunStateRow).filter_by(run_id=run_id).first()
        if state is None:
            return 0
        state.resume_count = (state.resume_count or 0) + 1
        s.flush()
        return state.resume_count


def get_run_state(run_id: str, session: Session | None = None) -> dict | None:
    """Ambil header state run sebagai dict lepas (aman dipakai setelah session tutup)."""
    with _session_scope(session) as s:
        row = s.query(RunStateRow).filter_by(run_id=run_id).first()
        if row is None:
            return None
        return {
            "run_id": row.run_id,
            "question": row.question,
            "dataset_id": row.dataset_id,
            "causal_roles_json": row.causal_roles_json,
            "intent": row.intent,
            "intent_json": row.intent_json,
            "plan_json": row.plan_json,
            "transcript_head": row.transcript_head,
            "tokens": row.tokens,
            "elapsed_ms": row.elapsed_ms,
            "status": row.status,
            "termination_reason": row.termination_reason,
            "resume_count": row.resume_count,
        }


def list_run_steps(run_id: str, session: Session | None = None) -> list[dict]:
    """Ambil semua langkah satu run, urut step_index, sebagai list dict lepas."""
    with _session_scope(session) as s:
        rows = (
            s.query(RunStepRow)
            .filter_by(run_id=run_id)
            .order_by(RunStepRow.step_index.asc())
            .all()
        )
        return [
            {
                "step_index": r.step_index,
                "kind": r.kind,
                "tool": r.tool,
                "input_json": r.input_json,
                "output_text": r.output_text,
                "error": r.error,
                "chart_paths_json": r.chart_paths_json,
                "tokens_after": r.tokens_after,
            }
            for r in rows
        ]


def list_resumable_runs(limit: int = 50, session: Session | None = None) -> list[dict]:
    """Run yang state-nya masih "running", kandidat resume setelah crash."""
    with _session_scope(session) as s:
        rows = (
            s.query(RunStateRow)
            .filter(RunStateRow.status == "running")
            .order_by(RunStateRow.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "run_id": r.run_id,
                "question": r.question,
                "dataset_id": r.dataset_id,
                "intent": r.intent,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


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


def scorecard_map(
    run_ids: list[str] | None = None, session: Session | None = None
) -> dict[str, dict]:
    """run_id → data scorecard sebagai dict lepas (aman setelah session tutup).

    Dipakai export kalibrasi: ambil sekali, bukan satu query per run, dan jangan
    kembalikan ORM row yang bakal jadi DetachedInstanceError di luar session.
    """
    with _session_scope(session) as s:
        q = s.query(ScorecardRow)
        if run_ids is not None:
            if not run_ids:
                return {}
            q = q.filter(ScorecardRow.run_id.in_(run_ids))
        return {
            r.run_id: {
                "question_id": r.question_id,
                "correctness": r.correctness,
                "cost_usd": r.cost_usd,
                "tool_calls": r.tool_calls,
                "time_to_insight": r.time_to_insight,
                "hallucination_flag": bool(r.hallucination_flag),
                "verification_accuracy": r.verification_accuracy,
            }
            for r in q.all()
        }


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
