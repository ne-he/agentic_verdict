"""Endpoint API ANALYST (FASE 4 / T4.1).

- POST /analyze             → stream SSEEvent (plan → step → tool → chart → verify → confidence → final)
- GET  /run/{run_id}        → hasil run historis dari DB
- POST /runs/{run_id}/resume→ lanjutkan run yang mati di tengah, dari checkpoint terakhir
- GET  /runs/resumable      → daftar run yang state-nya masih "running" (kandidat resume)
- GET  /eval/dashboard      → metrik agregat + run terbaru (failure dashboard)
- GET  /datasets            → daftar dataset tersedia

Catatan SSE: ReactLoop.run() sinkron & memancarkan event lewat callback `on_event`.
Loop dijalankan di thread terpisah; event masuk ke Queue lalu di-yield sebagai SSE.
Run disimpan ke DB setelah stream selesai supaya GET /run/{id} bisa mengambilnya.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import AsyncIterator, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.agent.react_loop import ReactLoop, RunNotResumable
from app.api.deps import get_react_loop
from app.core.datasets import DATASET_CATALOG, list_datasets
from app.sandbox.runner import ARTIFACTS_ROOT
from app.core.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    DatasetInfo,
    EvalDashboard,
    ResumableRun,
    RunRecord,
    SSEEvent,
)
from app.db import repository

router = APIRouter()

_SENTINEL = object()


def _sse(event: SSEEvent) -> str:
    """Format satu SSEEvent jadi frame text/event-stream."""
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"event: {event.type}\ndata: {payload}\n\n"


def _run_stream(
    work: Callable[[Callable[[SSEEvent], None]], AnalysisResult],
    question: str,
) -> AsyncIterator[str]:
    """Jalankan `work` di thread terpisah, stream event-nya sebagai SSE, lalu persist.

    Dipakai dua endpoint: /analyze (run baru) dan /runs/{id}/resume (lanjutan run
    yang mati). Bedanya cuma callable `work`-nya.
    """

    async def event_stream() -> AsyncIterator[str]:
        events: queue.Queue = queue.Queue()
        holder: dict[str, object] = {}

        def on_event(ev: SSEEvent) -> None:
            events.put(ev)

        def worker() -> None:
            try:
                holder["result"] = work(on_event)
            except Exception as exc:  # noqa: BLE001 - sampaikan ke client sbg event error
                holder["error"] = exc
            finally:
                events.put(_SENTINEL)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            try:
                item = events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            if item is _SENTINEL:
                break
            yield _sse(item)  # type: ignore[arg-type]

        # Stream selesai → persist run (kalau sukses) atau kirim event error.
        err = holder.get("error")
        if err is not None:
            yield _sse(SSEEvent(type="error", data={"message": str(err)}))
            return

        result = holder.get("result")
        if isinstance(result, AnalysisResult):
            try:
                repository.save_run(result, question=question)
            except Exception:  # noqa: BLE001 - gagal simpan tak boleh merusak stream
                pass

    return event_stream()


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    loop: ReactLoop = Depends(get_react_loop),
) -> StreamingResponse:
    """Jalankan analisis dan stream tiap event ke client (SSE)."""
    if req.dataset_id not in list_datasets():
        raise HTTPException(
            status_code=404,
            detail=f"dataset '{req.dataset_id}' tidak dikenal. Tersedia: {list_datasets()}",
        )

    def work(on_event: Callable[[SSEEvent], None]) -> AnalysisResult:
        return loop.run(
            req.question,
            req.dataset_id,
            on_event=on_event,
            causal_roles=req.causal_roles,
        )

    return StreamingResponse(_run_stream(work, req.question), media_type="text/event-stream")


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    loop: ReactLoop = Depends(get_react_loop),
) -> StreamingResponse:
    """Lanjutkan run yang mati di tengah, dari langkah terakhir yang tersimpan.

    404 kalau run_id tidak ada di checkpoint. 409 kalau run-nya sudah selesai
    (tidak ada yang perlu dilanjutkan). Sukses → stream SSE persis seperti /analyze,
    diawali event `step` bertanda "resume" supaya UI tahu ini lanjutan.
    """
    state = repository.get_run_state(run_id)
    if state is None:
        raise HTTPException(
            status_code=404, detail=f"run '{run_id}' tidak ada di checkpoint"
        )
    if state["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail=f"run '{run_id}' statusnya '{state['status']}', tidak perlu di-resume",
        )

    def work(on_event: Callable[[SSEEvent], None]) -> AnalysisResult:
        try:
            return loop.resume(run_id, on_event=on_event)
        except RunNotResumable as exc:
            raise RuntimeError(str(exc)) from exc

    return StreamingResponse(
        _run_stream(work, state["question"]), media_type="text/event-stream"
    )


@router.get("/runs/resumable", response_model=list[ResumableRun])
async def resumable_runs(limit: int = 50) -> list[ResumableRun]:
    """Run yang state-nya masih 'running', biasanya sisa proses yang mati di tengah."""
    return [ResumableRun(**row) for row in repository.list_resumable_runs(limit=limit)]


@router.get("/runs", response_model=list[RunRecord])
async def list_runs(limit: int = 50) -> list[RunRecord]:
    """Daftar run historis terbaru (halaman History)."""
    return repository.list_run_records(limit=limit)


@router.get("/run/{run_id}", response_model=RunRecord)
async def get_run(run_id: str) -> RunRecord:
    """Ambil hasil run historis dari DB."""
    record = repository.get_run_record(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' tidak ditemukan")
    return record


@router.get("/eval/dashboard", response_model=EvalDashboard)
async def eval_dashboard(limit: int = 50) -> EvalDashboard:
    """Metrik agregat + N run terbaru untuk failure dashboard."""
    return repository.get_eval_dashboard(limit=limit)


@router.get("/datasets", response_model=list[DatasetInfo])
async def datasets() -> list[DatasetInfo]:
    """Daftar dataset AKTIF di playground (hanya yang file CSV-nya tersedia)."""
    return [
        DatasetInfo(
            dataset_id=ds_id,
            file=DATASET_CATALOG[ds_id]["file"],
            encoding=DATASET_CATALOG[ds_id].get("encoding", "utf-8"),
        )
        for ds_id in list_datasets()
    ]


@router.get("/artifacts/{subdir}/{filename}")
async def get_artifact(subdir: str, filename: str) -> FileResponse:
    """Layani file chart PNG dari ARTIFACTS_ROOT/<subdir>/<filename> (guard path traversal)."""
    if not filename.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="hanya file .png yang dilayani")
    base = ARTIFACTS_ROOT.resolve()
    target = (base / subdir / filename).resolve()
    # Cegah path traversal: target harus di dalam ARTIFACTS_ROOT.
    if base not in target.parents:
        raise HTTPException(status_code=400, detail="path tidak valid")
    if not target.exists():
        raise HTTPException(status_code=404, detail="artifact tidak ditemukan")
    return FileResponse(str(target), media_type="image/png")
