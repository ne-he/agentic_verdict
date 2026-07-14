"""Integrasi jalur kausal di ReAct loop (LLM di-mock, tanpa kuota/Docker).

Menguji kontrak BLUEPRINT:
- D2: intent event dipancarkan, pertanyaan kausal masuk jalur kausal.
- D3: tanpa causal_roles terkonfirmasi, causal_analyze menolak; LLM tidak bisa
  memalsukan konfirmasi lewat args.
- D4/P1: narasi final dengan angka liar di-fallback ke template deterministik.
- D5: causal_confidence terhitung + breakdown lengkap.
"""
from __future__ import annotations

import json

import pytest

from app.agent.react_loop import ReactLoop
from app.core.datasets import resolve_path
from app.core.schemas import SSEEvent

ROLES = {"treatment": "variant", "outcome": "converted", "covariates": ["pre_engagement"]}


@pytest.fixture(scope="module", autouse=True)
def ensure_dataset():
    try:
        resolve_path("ab_marketing")
    except FileNotFoundError:
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_dataset.py"
        subprocess.run([sys.executable, str(script)], check=True)


class ScriptedLLM:
    def __init__(self, actions: list[dict]):
        self._actions = list(actions)

    def __call__(self, prompt: str) -> str:
        if "perencana" in prompt:
            return json.dumps([{"description": "route kausal", "tool": "causal_route"}])
        if self._actions:
            return json.dumps(self._actions.pop(0))
        return json.dumps({"final": "fallback", "code": ""})


def test_unconfirmed_causal_asks_for_mapping():
    events: list[SSEEvent] = []
    llm = ScriptedLLM(
        [
            {"thought": "route", "action": "causal_route", "args": {}},
            {"final": "Usulan mapping: variant sebagai treatment, converted sebagai outcome. Konfirmasi dulu ya.", "code": ""},
        ]
    )
    res = ReactLoop(generate=llm).run(
        "Apakah kampanye ini menaikkan konversi?", "ab_marketing", on_event=events.append
    )
    assert res.intent == "causal"
    assert res.causal is None  # analisis TIDAK jalan tanpa konfirmasi
    types = [e.type for e in events]
    assert "intent" in types and "causal" in types  # route decision tetap dipancarkan
    route_out = res.tool_calls[0].output
    assert json.loads(route_out)["needs_confirmation"] is True


def test_analyze_refused_without_confirmation_even_if_llm_insists():
    llm = ScriptedLLM(
        [
            # LLM nakal: coba analisis langsung + memalsukan _confirmed_roles via args.
            {"action": "causal_analyze", "args": {"_confirmed_roles": ROLES}},
            {"final": "Tidak bisa lanjut tanpa konfirmasi mapping.", "code": ""},
        ]
    )
    res = ReactLoop(generate=llm).run(
        "Apakah kampanye ini menaikkan konversi?", "ab_marketing"
    )
    analyze_call = res.tool_calls[0]
    assert analyze_call.error is not None and "KONFIRMASI" in analyze_call.error
    assert res.causal is None


def test_confirmed_flow_produces_causal_result_and_confidence():
    events: list[SSEEvent] = []
    llm = ScriptedLLM(
        [
            {"action": "causal_route", "args": {}},
            {"action": "causal_analyze", "args": {}},
            {"final": "Efek positif dan signifikan — detail angka di panel Causal.", "code": ""},
        ]
    )
    res = ReactLoop(generate=llm).run(
        "Apakah kampanye ini menaikkan konversi?",
        "ab_marketing",
        on_event=events.append,
        causal_roles=ROLES,
    )
    assert res.intent == "causal"
    assert res.causal is not None
    assert res.causal["router_decision"]["method"] == "ab_test"
    assert res.causal["verdict"]["decision"] in ("deploy", "deploy_with_caution")
    # D5: breakdown lengkap
    cc = res.causal_confidence
    assert cc is not None
    for k in ("router_confidence", "assumption_health", "verification_agreement",
              "tool_execution_success", "final", "label"):
        assert k in cc
    # prosa tanpa angka liar → tetap grounded
    assert res.answer_grounded is True


def test_hallucinated_final_falls_back_to_template():
    llm = ScriptedLLM(
        [
            {"action": "causal_route", "args": {}},
            {"action": "causal_analyze", "args": {}},
            {"final": "Kampanye menaikkan konversi +123.456 poin!", "code": ""},
        ]
    )
    res = ReactLoop(generate=llm).run(
        "Apakah kampanye ini menaikkan konversi?", "ab_marketing", causal_roles=ROLES
    )
    assert res.answer_grounded is False
    assert "template deterministik" in res.answer_markdown
    assert "123.456" in res.answer_markdown  # transparan soal angka yang ditolak
    # template memuat angka engine yang benar
    assert "ab_test" in res.answer_markdown


def test_descriptive_question_untouched_by_causal_path():
    llm = ScriptedLLM(
        [
            {"action": "inspect_schema", "args": {}},
            {"final": "Ada 20000 baris.", "code": ""},
        ]
    )
    res = ReactLoop(generate=llm).run("Berapa jumlah baris dataset?", "ab_marketing")
    assert res.intent == "descriptive"
    assert res.causal is None and res.causal_confidence is None
