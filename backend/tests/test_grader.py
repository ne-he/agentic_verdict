"""Acceptance T3.2 — Grader & Metrics.

Test:
- jawaban tepat → correctness 1.0
- jawaban meleset 5x tolerance → correctness 0.5
- jawaban salah total → correctness 0.0
- jawaban salah + confidence HIGH → hallucination_flag True
- jawaban benar + confidence HIGH → hallucination_flag False
- LLM judge fallback dipanggil bila numeric ekstrak gagal
- verification accuracy: 4 kombinasi (TP, TN, false-pass, false-alarm)
- aggregate: avg correctness, halluc rate, total cost
"""

from __future__ import annotations

import pytest

from app.core.schemas import (
    AnalysisResult,
    ConfidenceBreakdown,
    GoldQuestion,
    Scorecard,
    ToolCall,
    VerificationResult,
)
from app.eval.grader import (
    _extract_first_number,
    _numeric_correctness,
    _verification_accuracy,
    grade,
)
from app.eval.metrics import aggregate


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _make_confidence(label: str, final: float = 0.9) -> ConfidenceBreakdown:
    val = final
    return ConfidenceBreakdown(
        answer_consistency=val,
        verification_agreement=val,
        tool_execution_success=val,
        data_coverage=val,
        final=final,
        label=label,  # type: ignore[arg-type]
    )


def _make_result(
    answer: str,
    run_id: str = "run_test",
    confidence_label: str | None = "HIGH",
    verified: bool | None = True,
    duration_ms: int = 2000,
    cost_usd: float = 0.001,
    n_tools: int = 2,
) -> AnalysisResult:
    conf = _make_confidence(confidence_label) if confidence_label else None
    verif: VerificationResult | None = None
    if verified is not None:
        verif = VerificationResult(
            method_a="agent: 100",
            method_b="duckdb: 100",
            agreement=1.0 if verified else 0.1,
            contradictions=[] if verified else ["Nilai berbeda"],
            passed=verified,
        )
    return AnalysisResult(
        run_id=run_id,
        answer_markdown=answer,
        code="df['X'].sum()",
        confidence=conf,
        verification=verif,
        tool_calls=[ToolCall(tool="inspect_schema") for _ in range(n_tools)],
        duration_ms=duration_ms,
        cost_usd=cost_usd,
    )


def _make_gold(expected: float, tolerance: float = 0.001) -> GoldQuestion:
    return GoldQuestion(
        id="q_test",
        category="descriptive",
        question="Berapa total X?",
        gold_answer=f"Total = {expected}",
        gold_code="df['X'].sum()",
        expected_value=expected,
        allowed_tolerance=tolerance,
    )


# ── _extract_first_number ─────────────────────────────────────────────────────


def test_extract_number_plain():
    assert _extract_first_number("Total = 1234.56") == pytest.approx(1234.56)


def test_extract_number_with_comma():
    assert _extract_first_number("$2,297,200.86") == pytest.approx(2297200.86)


def test_extract_number_negative():
    assert _extract_first_number("Profit = -25729.36") == pytest.approx(-25729.36)


def test_extract_number_none():
    assert _extract_first_number("tidak ada angka di sini") is None


# ── _numeric_correctness ──────────────────────────────────────────────────────


def test_numeric_exact_match():
    assert _numeric_correctness("Total = 286397.02", 286397.02, 0.001) == pytest.approx(1.0)


def test_numeric_within_tolerance():
    assert _numeric_correctness("approx 286000", 286397.02, 0.01) == pytest.approx(1.0)


def test_numeric_partial_match():
    # rel_diff ≈ 2.2% (280000 vs 286397), pakai tolerance=0.005 → 5x=0.025 > rel_diff → 0.5
    assert _numeric_correctness("Total = 280000", 286397.02, 0.005) == pytest.approx(0.5)


def test_numeric_wrong():
    assert _numeric_correctness("Total = 100", 286397.02, 0.001) == pytest.approx(0.0)


def test_numeric_no_number_returns_none():
    assert _numeric_correctness("tidak ada angka", 286397.02, 0.001) is None


# ── grade end-to-end ──────────────────────────────────────────────────────────


def test_grade_correct_answer():
    result = _make_result("Total Sales = $2,297,200.86", confidence_label="HIGH")
    gold = _make_gold(2297200.86, 0.001)
    sc = grade(result, gold)
    assert isinstance(sc, Scorecard)
    assert sc.correctness == pytest.approx(1.0)
    assert sc.hallucination_flag is False
    assert sc.question_id == "q_test"


def test_grade_wrong_answer_flags_hallucination():
    result = _make_result("Total = 999.99", confidence_label="HIGH", verified=True)
    gold = _make_gold(2297200.86, 0.001)
    sc = grade(result, gold)
    assert sc.correctness == pytest.approx(0.0)
    assert sc.hallucination_flag is True  # HIGH confidence tapi salah


def test_grade_wrong_answer_low_confidence_no_halluc():
    result = _make_result("Total = 999.99", confidence_label="LOW")
    gold = _make_gold(2297200.86, 0.001)
    sc = grade(result, gold)
    assert sc.correctness == pytest.approx(0.0)
    assert sc.hallucination_flag is False  # LOW confidence → tidak di-flag sebagai halusinasi


def test_grade_llm_judge_fallback():
    """Bila numeric ekstrak gagal dan generate disediakan → LLM judge dipanggil."""
    calls: list[str] = []

    def fake_generate(prompt: str) -> str:
        calls.append(prompt)
        return "5"  # score sempurna

    result = _make_result("Jawaban teks tanpa angka jelas", confidence_label="HIGH")
    gold = GoldQuestion(
        id="q_text",
        category="diagnostic",
        question="Sub-kategori apa yang merugi?",
        gold_answer="Tables, Bookcases, Supplies",
        gold_code="...",
        expected_value=0.0,
        allowed_tolerance=0.0,
    )
    sc = grade(result, gold, generate=fake_generate)
    assert len(calls) == 1  # LLM judge dipanggil
    assert sc.correctness == pytest.approx(1.0)  # score 5 → 1.0


def test_grade_scorecard_fields():
    result = _make_result("Total = 100", duration_ms=3000, cost_usd=0.002, n_tools=3)
    gold = _make_gold(100.0, 0.001)
    sc = grade(result, gold)
    assert sc.tool_calls == 3
    assert sc.time_to_insight == pytest.approx(3.0)
    assert sc.cost_usd == pytest.approx(0.002)


# ── _verification_accuracy ────────────────────────────────────────────────────


def test_verif_accuracy_true_positive():
    # passed=True, correctness>=0.5 → 1.0
    result = _make_result("Total = 286397.02", verified=True)
    assert _verification_accuracy(result, 1.0) == pytest.approx(1.0)


def test_verif_accuracy_true_negative():
    # passed=False, correctness<0.5 → 1.0 (verification caught the error)
    result = _make_result("Total = 999", verified=False)
    assert _verification_accuracy(result, 0.0) == pytest.approx(1.0)


def test_verif_accuracy_false_pass():
    # passed=True, correctness<0.5 → 0.0 (verification missed the error)
    result = _make_result("Total = 999", verified=True)
    assert _verification_accuracy(result, 0.0) == pytest.approx(0.0)


def test_verif_accuracy_no_verification():
    result = _make_result("Total = 286397.02", verified=None)
    assert _verification_accuracy(result, 1.0) == pytest.approx(0.0)


# ── aggregate (metrics.py) ────────────────────────────────────────────────────


def test_aggregate_empty():
    summary = aggregate([])
    assert summary.total == 0
    assert summary.avg_correctness == pytest.approx(0.0)


def test_aggregate_correct_values():
    scorecards = [
        Scorecard(run_id="r1", question_id="q1", correctness=1.0, cost_usd=0.001,
                  tool_calls=2, time_to_insight=2.0, hallucination_flag=False, verification_accuracy=1.0),
        Scorecard(run_id="r2", question_id="q2", correctness=0.0, cost_usd=0.002,
                  tool_calls=4, time_to_insight=4.0, hallucination_flag=True, verification_accuracy=0.0),
    ]
    summary = aggregate(scorecards)
    assert summary.total == 2
    assert summary.avg_correctness == pytest.approx(0.5)
    assert summary.total_cost_usd == pytest.approx(0.003)
    assert summary.hallucination_rate == pytest.approx(0.5)
    assert summary.avg_tool_calls == pytest.approx(3.0)
    assert summary.run_ids == ["r1", "r2"]
