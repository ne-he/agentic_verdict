"""Acceptance T1.4 — 3 pertanyaan contoh -> plan terstruktur valid.

Gemini di-mock (generate di-inject) supaya tidak boros kuota.
"""

import json

import pytest

from app.agent.planner import Planner, parse_plan
from app.core.schemas import PlanStep

TOOLS = ["inspect_schema", "write_and_execute", "make_chart"]

EXAMPLES = {
    "Berapa total penjualan keseluruhan?": [
        {"description": "Periksa skema dataset", "tool": "inspect_schema"},
        {"description": "Jumlahkan kolom Sales", "tool": "write_and_execute"},
    ],
    "Region mana yang revenue Q3 paling turun YoY?": [
        {"description": "Periksa skema", "tool": "inspect_schema"},
        {"description": "Filter Q3 dan hitung delta per region", "tool": "write_and_execute"},
        {"description": "Bar chart penurunan", "tool": "make_chart"},
    ],
    "Apakah diskon berkorelasi dengan profit?": [
        {"description": "Periksa skema", "tool": "inspect_schema"},
        {"description": "Hitung korelasi Pearson & Spearman", "tool": "write_and_execute"},
    ],
}


def _fake_generate_for(question: str):
    def gen(prompt: str) -> str:
        assert question in prompt  # prompt memuat pertanyaan
        return json.dumps(EXAMPLES[question])

    return gen


@pytest.mark.parametrize("question", list(EXAMPLES))
def test_plan_structured_valid(question):
    planner = Planner(generate=_fake_generate_for(question))
    steps = planner.plan(question, "superstore", TOOLS)
    assert all(isinstance(s, PlanStep) for s in steps)
    assert [s.id for s in steps] == list(range(1, len(steps) + 1))
    assert steps[0].tool == "inspect_schema"
    assert all(s.tool in TOOLS for s in steps)
    assert all(s.status == "pending" for s in steps)


def test_parse_strips_code_fence():
    raw = '```json\n[{"description": "cek", "tool": "inspect_schema"}]\n```'
    steps = parse_plan(raw, TOOLS)
    assert len(steps) == 1 and steps[0].tool == "inspect_schema"


def test_parse_handles_steps_object():
    raw = '{"steps": [{"description": "cek", "tool": "write_and_execute"}]}'
    steps = parse_plan(raw, TOOLS)
    assert steps[0].tool == "write_and_execute"


def test_parse_unknown_tool_falls_back():
    raw = '[{"description": "x", "tool": "delete_database"}]'
    steps = parse_plan(raw, TOOLS)
    assert steps[0].tool == "write_and_execute"


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_plan("[]", TOOLS)
