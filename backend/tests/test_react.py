"""Acceptance T1.5 (unit) — ReAct loop orkestrasi dgn Gemini di-mock (tanpa kuota/Docker).

Aksi di-script supaya hanya pakai inspect_schema (murni DuckDB) lalu final -> tak butuh sandbox.
Test live end-to-end via CLI + Gemini asli dijalankan terpisah (lihat laporan).
"""

import json

from app.agent.react_loop import ReactLoop
from app.core.schemas import SSEEvent


class ScriptedLLM:
    """Fake generate: balas plan utk prompt planner, lalu aksi sesuai antrian utk loop."""

    def __init__(self, actions: list[dict]):
        self._actions = list(actions)

    def __call__(self, prompt: str) -> str:
        if "perencana" in prompt:  # prompt planner
            return json.dumps(
                [
                    {"description": "inspect schema", "tool": "inspect_schema"},
                    {"description": "hitung", "tool": "write_and_execute"},
                ]
            )
        if self._actions:
            return json.dumps(self._actions.pop(0))
        return json.dumps({"final": "fallback", "code": ""})


def test_loop_runs_plan_tool_final():
    events: list[SSEEvent] = []
    llm = ScriptedLLM(
        [
            {"thought": "lihat skema", "action": "inspect_schema", "args": {}},
            {"final": "Total Sales = **$2,297,200.86**", "code": "df['Sales'].sum()"},
        ]
    )
    loop = ReactLoop(generate=llm)
    res = loop.run("Berapa total penjualan?", "superstore", on_event=events.append)

    assert "2,297,200.86" in res.answer_markdown
    assert res.code == "df['Sales'].sum()"
    assert [tc.tool for tc in res.tool_calls] == ["inspect_schema"]
    assert res.tool_calls[0].error is None
    types = [e.type for e in events]
    # Kontrak VERDICT ANALYST: event pertama = intent (D2), lalu plan, terakhir final.
    assert types[0] == "intent" and types[1] == "plan" and types[-1] == "final"


def test_loop_respects_max_tool_calls():
    # Selalu balas aksi tool (tak pernah final) -> harus berhenti di batas.
    llm = ScriptedLLM([{"action": "inspect_schema", "args": {}}] * 50)
    loop = ReactLoop(generate=llm, max_tool_calls=3)
    res = loop.run("q", "superstore")
    assert len(res.tool_calls) <= 3
    assert "batas iterasi" in res.answer_markdown.lower()


def test_loop_handles_non_json_then_final():
    class Flaky:
        def __init__(self):
            self.n = 0

        def __call__(self, prompt: str) -> str:
            if "perencana" in prompt:
                return json.dumps([{"description": "x", "tool": "inspect_schema"}])
            self.n += 1
            if self.n == 1:
                return "ini bukan json"
            return json.dumps({"final": "ok", "code": "df.head()"})

    loop = ReactLoop(generate=Flaky())
    res = loop.run("q", "superstore")
    assert res.answer_markdown == "ok"


def test_loop_attaches_verification_and_confidence():
    # Final menyertakan key_value + verify_sql -> loop jalankan cross-check (DuckDB, tanpa Docker).
    llm = ScriptedLLM(
        [
            {
                "final": "Total Sales = **$2,297,200.86**",
                "code": "df['Sales'].sum()",
                "key_value": 2297200.86,
                "verify_sql": 'SELECT SUM("Sales") FROM t',
            }
        ]
    )
    loop = ReactLoop(generate=llm)
    events: list[SSEEvent] = []
    res = loop.run("Total penjualan?", "superstore", on_event=events.append)

    assert res.verification is not None and res.verification.passed
    assert res.confidence is not None and res.confidence.label == "HIGH"
    assert res.dataset_snapshot.startswith("sha256:")
    assert "verify" in [e.type for e in events]
    assert "confidence" in [e.type for e in events]


def test_loop_skips_unknown_tool():
    llm = ScriptedLLM(
        [
            {"action": "drop_table", "args": {}},
            {"final": "selesai", "code": ""},
        ]
    )
    loop = ReactLoop(generate=llm)
    res = loop.run("q", "superstore")
    assert res.tool_calls == []  # tool tak dikenal tidak dieksekusi
    assert res.answer_markdown == "selesai"
