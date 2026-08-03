"""Tiga aturan produksi agent (brief 04, Prompt D).

1. TOOL MINIMUM:      tool yang dikirim ke model dipangkas per jenis pertanyaan.
2. STEP BUDGET & TIMEOUT: batas langkah, batas token, batas wall-clock aktif.
3. ALASAN TERMINASI:  tiap run mencatat kenapa berhenti, ikut ke run history.

Semua LLM di-mock. Tidak ada panggilan Gemini.
"""

from __future__ import annotations

import json
import time

import pytest

from app.agent import termination
from app.agent.react_loop import ReactLoop
from app.agent.tools import TOOLSETS, build_default_registry, build_registry_for_intent
from app.core.schemas import AnalysisResult
from app.db import repository
from app.db.session import configure_database, create_tables

CAUSAL_TOOLS = {"causal_route", "causal_analyze", "causal_refute"}


class ScriptedLLM:
    def __init__(self, actions: list[dict]):
        self._actions = list(actions)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "perencana" in prompt:
            return json.dumps([{"description": "x", "tool": "inspect_schema"}])
        if self._actions:
            return json.dumps(self._actions.pop(0))
        return json.dumps({"final": "fallback", "code": ""})

    @property
    def loop_prompts(self) -> list[str]:
        return [p for p in self.prompts if "perencana" not in p]


# ── Aturan 1: tool minimum ───────────────────────────────────────────────────


def test_descriptive_toolset_excludes_causal_tools():
    names = set(build_registry_for_intent("descriptive").names())
    assert names == {"inspect_schema", "write_and_execute", "make_chart"}
    assert not (names & CAUSAL_TOOLS)


def test_causal_toolset_excludes_chart_tool():
    names = set(build_registry_for_intent("causal").names())
    assert CAUSAL_TOOLS.issubset(names)
    assert "make_chart" not in names


def test_unknown_intent_falls_back_to_descriptive_set():
    assert build_registry_for_intent("entah").names() == list(TOOLSETS["descriptive"])


def test_default_registry_still_has_everything():
    """build_default_registry tetap lengkap, dipakai test kontrak tool."""
    assert len(build_default_registry().names()) == 6


def test_prompt_for_descriptive_question_omits_causal_tool_docs():
    llm = ScriptedLLM([{"final": "ok", "code": ""}])
    ReactLoop(generate=llm).run("Berapa total penjualan?", "superstore")
    prompt = llm.loop_prompts[0]
    for tool in CAUSAL_TOOLS:
        assert tool not in prompt, f"tool kausal '{tool}' bocor ke prompt deskriptif"


def test_prompt_for_causal_question_omits_chart_tool():
    llm = ScriptedLLM([{"final": "Perlu konfirmasi mapping dulu.", "code": ""}])
    ReactLoop(generate=llm).run("Apakah kampanye ini menaikkan konversi?", "superstore")
    prompt = llm.loop_prompts[0]
    assert "causal_route" in prompt
    assert "make_chart" not in prompt


def test_explicit_registry_is_respected():
    """Registry yang di-inject eksplisit tidak ikut dipangkas."""
    reg = build_default_registry()
    llm = ScriptedLLM([{"final": "ok", "code": ""}])
    ReactLoop(registry=reg, generate=llm).run("Berapa total penjualan?", "superstore")
    assert "causal_route" in llm.loop_prompts[0]


# ── Aturan 2: step budget & timeout ──────────────────────────────────────────


def test_step_budget_stops_run():
    llm = ScriptedLLM([{"action": "inspect_schema", "args": {}}] * 20)
    res = ReactLoop(generate=llm, max_tool_calls=3).run("q", "superstore")
    assert len(res.tool_calls) == 3
    assert res.termination_reason == "step_budget"


def test_token_budget_stops_run():
    llm = ScriptedLLM([{"action": "inspect_schema", "args": {}}] * 20)
    res = ReactLoop(generate=llm, max_tokens=1).run("q", "superstore")
    assert res.termination_reason == "token_budget"
    assert "budget token" in res.answer_markdown.lower()


def test_timeout_stops_run():
    class SlowLLM(ScriptedLLM):
        def __call__(self, prompt: str) -> str:
            out = super().__call__(prompt)
            if "perencana" not in prompt:
                time.sleep(0.05)
            return out

    llm = SlowLLM([{"action": "inspect_schema", "args": {}}] * 20)
    res = ReactLoop(generate=llm, timeout_s=0.01).run("q", "superstore")
    assert res.termination_reason == "timeout"
    assert "batas waktu" in res.answer_markdown.lower()


def test_defaults_are_documented_values():
    """Nilai default budget dikunci di test supaya tidak berubah diam-diam."""
    from app.agent import react_loop as rl

    assert rl.DEFAULT_MAX_TOOL_CALLS == 12
    assert rl.DEFAULT_MAX_TOKENS == 200_000
    assert rl.DEFAULT_TIMEOUT_S == 300.0


# ── Aturan 3: alasan terminasi ───────────────────────────────────────────────


def test_completed_run_reports_completed():
    llm = ScriptedLLM([{"final": "selesai", "code": ""}])
    res = ReactLoop(generate=llm).run("q", "superstore")
    assert res.termination_reason == "completed"
    assert not termination.is_incomplete(res.termination_reason)


def test_all_reasons_have_human_label():
    for reason in termination.ALL_REASONS:
        assert termination.label(reason) != reason


def test_termination_reason_persisted_to_run_history(tmp_path):
    configure_database(f"sqlite:///{(tmp_path / 'term.db').as_posix()}")
    create_tables()
    try:
        llm = ScriptedLLM([{"action": "inspect_schema", "args": {}}] * 10)
        res = ReactLoop(generate=llm, max_tool_calls=2).run("q", "superstore")
        repository.save_run(res, question="q")

        record = repository.get_run_record(res.run_id)
        assert record is not None
        assert record.termination_reason == "step_budget"
    finally:
        configure_database(None)


def test_duration_ms_is_measured_on_success_path():
    """BUG FIX: build_analysis_bundle dulu dipanggil tanpa duration_ms di react_loop,
    jadi durasi SELALU 0 di jalur sukses (yang kecatat non-nol malah cuma jalur error).
    Akibatnya time_to_insight di semua scorecard eval = 0.0 dan tidak berarti apa-apa.

    LLM di sini sengaja tidur 30 ms supaya durasinya jauh di atas resolusi timer
    Windows (~15 ms). Ambang assert dipasang longgar di 10 ms: yang diuji adalah
    "durasi beneran diukur", bukan presisi stopwatch-nya.
    """

    class SlowLLM(ScriptedLLM):
        def __call__(self, prompt: str) -> str:
            out = super().__call__(prompt)
            time.sleep(0.03)
            return out

    llm = SlowLLM([{"final": "selesai", "code": ""}])
    res: AnalysisResult = ReactLoop(generate=llm).run("q", "superstore")
    assert res.duration_ms >= 10, f"durasi tidak terukur: {res.duration_ms} ms"
