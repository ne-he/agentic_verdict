"""Dependencies untuk API (FASE 4 / T4.1).

`get_react_loop` di-inject ke endpoint /analyze. Default: ReactLoop dengan Gemini live
plus checkpointer SQLite (durable state per langkah → run bisa di-resume setelah crash).
Saat test, override via `app.dependency_overrides[get_react_loop]` supaya pakai LLM mock
(persis pola injectable di run_batch) — JANGAN andelin Gemini live di test.
"""

from __future__ import annotations

from app.agent.checkpoint import SqliteCheckpointer
from app.agent.react_loop import ReactLoop


def get_react_loop() -> ReactLoop:
    """Factory ReactLoop default (live Gemini + durable state). Override di test."""
    return ReactLoop(checkpointer=SqliteCheckpointer())
