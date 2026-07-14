"""SQLAlchemy 2.0 ORM models (T3.4).

Tabel:
  - run_history   : tiap AnalysisResult yang diselesaikan
  - scorecards    : penilaian eval per run
  - gold_questions: pertanyaan gold set yang tersimpan (optional, untuk dashboard)
  - artifacts     : path file hasil (chart PNG, dsb)

Tidak ada tipe kolom SQLite-only — semua standar SQLAlchemy supaya portable ke Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunHistory(Base):
    """Satu run analitik yang telah diselesaikan."""

    __tablename__ = "run_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_snapshot: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    scorecard: Mapped[ScorecardRow | None] = relationship(
        "ScorecardRow", back_populates="run", uselist=False
    )
    artifacts: Mapped[list[Artifact]] = relationship("Artifact", back_populates="run")


class ScorecardRow(Base):
    """Hasil grading satu run terhadap gold answer."""

    __tablename__ = "scorecards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("run_history.run_id"), unique=True, nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    correctness: Mapped[float] = mapped_column(Float, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_insight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    run: Mapped[RunHistory] = relationship("RunHistory", back_populates="scorecard")


class GoldQuestionRow(Base):
    """Gold question yang tersimpan di DB (untuk dashboard & history)."""

    __tablename__ = "gold_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    gold_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    allowed_tolerance: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    is_trap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Artifact(Base):
    """Path file hasil analisis (chart PNG, dsb)."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("run_history.run_id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "chart", "code", dsb
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    run: Mapped[RunHistory] = relationship("RunHistory", back_populates="artifacts")
