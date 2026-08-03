"""Durable state loop agent: checkpoint per LANGKAH, bukan cuma hasil akhir.

Kenapa ada: run_history menyimpan hasil. Kalau proses mati di tengah run, hasil
itu tidak pernah ditulis dan seluruh pekerjaan hilang. Checkpointer menulis state
loop tiap iterasi ke SQLite (commit per langkah), jadi run yang mati bisa
dilanjutkan lewat POST /runs/{run_id}/resume.

Kontrak sengaja kecil supaya react_loop tidak perlu tahu soal SQLAlchemy:
  start()       -> catat header run (pertanyaan, dataset, intent, plan, transcript awal)
  record_step() -> catat satu iterasi loop
  finish()      -> tandai selesai + alasan terminasi
  load()        -> rekonstruksi state untuk resume

Default implementasi = NullCheckpointer (no-op). Ini disengaja: test lama dan
pemakaian library tidak ikut menulis ke DB kecuali diminta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.schemas import PlanStep, ToolCall


@dataclass
class StepRecord:
    """Satu iterasi loop yang tersimpan."""

    step_index: int
    kind: str = "tool"  # tool | invalid_response | unknown_tool
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    error: str = ""
    chart_paths: list[str] = field(default_factory=list)
    tokens_after: int = 0


@dataclass
class ResumeState:
    """State yang cukup untuk melanjutkan run dari langkah terakhir yang tersimpan."""

    run_id: str
    question: str
    dataset_id: str
    causal_roles: dict[str, Any] | None
    intent: str
    intent_data: dict[str, Any]
    plan: list[PlanStep]
    transcript_head: str
    tokens: int
    elapsed_ms: int
    status: str
    steps: list[StepRecord]

    @property
    def steps_done(self) -> int:
        return len(self.steps)

    def tool_calls(self) -> list[ToolCall]:
        """ToolCall yang sudah terjadi sebelum crash (hanya langkah ber-kind 'tool')."""
        return [
            ToolCall(
                tool=s.tool,
                input=s.args,
                output=s.output or None,
                error=s.error or None,
            )
            for s in self.steps
            if s.kind == "tool"
        ]


class RunCheckpointer(Protocol):
    """Kontrak penyimpan state loop. Implementasi nyata: SqliteCheckpointer."""

    def start(
        self,
        *,
        run_id: str,
        question: str,
        dataset_id: str,
        causal_roles: dict[str, Any] | None,
        intent: str,
        intent_data: dict[str, Any],
        plan: list[PlanStep],
        transcript_head: str,
    ) -> None: ...

    def record_step(self, run_id: str, step: StepRecord) -> None: ...

    def finish(
        self,
        *,
        run_id: str,
        status: str,
        termination_reason: str,
        tokens: int = 0,
        elapsed_ms: int = 0,
    ) -> None: ...

    def load(self, run_id: str) -> ResumeState | None: ...

    def bump_resume_count(self, run_id: str) -> int: ...


class NullCheckpointer:
    """Tidak menyimpan apa-apa. Default supaya ReactLoop tetap bisa dipakai tanpa DB."""

    def start(self, **_kwargs: Any) -> None:
        return None

    def record_step(self, run_id: str, step: StepRecord) -> None:
        return None

    def finish(self, **_kwargs: Any) -> None:
        return None

    def load(self, run_id: str) -> ResumeState | None:
        return None

    def bump_resume_count(self, run_id: str) -> int:
        return 0


class SqliteCheckpointer:
    """Simpan state loop ke tabel run_states + run_steps lewat repository.

    Tiap `record_step` membuka session sendiri dan commit. Itu memang lebih mahal
    daripada satu transaksi besar, tapi justru itu intinya: kalau proses dibunuh
    setelah langkah ke-2, langkah ke-1 dan ke-2 harus sudah ada di disk.
    """

    def __init__(self, ensure_tables: bool = True) -> None:
        from app.db import repository

        self._repo = repository
        if ensure_tables:
            self._repo.init_db()

    def start(
        self,
        *,
        run_id: str,
        question: str,
        dataset_id: str,
        causal_roles: dict[str, Any] | None,
        intent: str,
        intent_data: dict[str, Any],
        plan: list[PlanStep],
        transcript_head: str,
    ) -> None:
        self._repo.start_run_state(
            run_id=run_id,
            question=question,
            dataset_id=dataset_id,
            causal_roles_json=json.dumps(causal_roles, ensure_ascii=False) if causal_roles else "",
            intent=intent,
            intent_json=json.dumps(intent_data, ensure_ascii=False),
            plan_json=json.dumps([s.model_dump() for s in plan], ensure_ascii=False),
            transcript_head=transcript_head,
        )

    def record_step(self, run_id: str, step: StepRecord) -> None:
        self._repo.append_run_step(
            run_id=run_id,
            step_index=step.step_index,
            kind=step.kind,
            tool=step.tool,
            input_json=json.dumps(step.args, ensure_ascii=False, default=str),
            output_text=step.output,
            error=step.error,
            chart_paths_json=json.dumps(step.chart_paths, ensure_ascii=False),
            tokens_after=step.tokens_after,
        )

    def finish(
        self,
        *,
        run_id: str,
        status: str,
        termination_reason: str,
        tokens: int = 0,
        elapsed_ms: int = 0,
    ) -> None:
        self._repo.finish_run_state(
            run_id=run_id,
            status=status,
            termination_reason=termination_reason,
            tokens=tokens,
            elapsed_ms=elapsed_ms,
        )

    def bump_resume_count(self, run_id: str) -> int:
        return self._repo.bump_resume_count(run_id)

    def load(self, run_id: str) -> ResumeState | None:
        header = self._repo.get_run_state(run_id)
        if header is None:
            return None
        raw_steps = self._repo.list_run_steps(run_id)
        steps = [
            StepRecord(
                step_index=s["step_index"],
                kind=s["kind"],
                tool=s["tool"],
                args=_loads(s["input_json"], {}),
                output=s["output_text"],
                error=s["error"],
                chart_paths=_loads(s["chart_paths_json"], []),
                tokens_after=s["tokens_after"],
            )
            for s in raw_steps
        ]
        plan = [PlanStep.model_validate(p) for p in _loads(header["plan_json"], [])]
        return ResumeState(
            run_id=header["run_id"],
            question=header["question"],
            dataset_id=header["dataset_id"],
            causal_roles=_loads(header["causal_roles_json"], None) or None,
            intent=header["intent"],
            intent_data=_loads(header["intent_json"], {}),
            plan=plan,
            transcript_head=header["transcript_head"],
            tokens=header["tokens"],
            elapsed_ms=header["elapsed_ms"],
            status=header["status"],
            steps=steps,
        )


def _loads(raw: str, default: Any) -> Any:
    """json.loads yang tidak meledak kalau kolomnya kosong atau rusak."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
