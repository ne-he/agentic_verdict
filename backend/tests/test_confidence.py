"""Acceptance T2.2 — computed confidence.

Verifikasi tinggi -> HIGH + breakdown. Kontradiksi -> MEDIUM/LOW.
"""

from app.agent.confidence import (
    answer_consistency_from_verification,
    compute_confidence,
    label_for,
    tool_execution_success,
)
from app.core.schemas import ToolCall, VerificationResult


def _verify(agreement: float, contradictions=None, passed=True) -> VerificationResult:
    return VerificationResult(
        method_a="a",
        method_b="b",
        agreement=agreement,
        contradictions=contradictions or [],
        passed=passed,
    )


def test_high_confidence_all_good():
    tools = [ToolCall(tool="inspect_schema"), ToolCall(tool="write_and_execute")]
    cb = compute_confidence(verification=_verify(1.0), tool_calls=tools, data_coverage=1.0)
    assert cb.final == 1.0
    assert cb.label == "HIGH"
    # breakdown explainable, jumlah komponen berbobot == final
    assert cb.verification_agreement == 1.0
    assert cb.tool_execution_success == 1.0


def test_contradiction_lowers_to_medium_or_low():
    cb = compute_confidence(
        verification=_verify(0.2, contradictions=["cross-check mismatch"], passed=False),
        tool_calls=[ToolCall(tool="write_and_execute")],
    )
    assert cb.label in {"MEDIUM", "LOW"}
    assert cb.answer_consistency < 1.0


def test_severe_failure_is_low():
    cb = compute_confidence(
        verification=_verify(0.0, contradictions=["x", "y"], passed=False),
        tool_calls=[
            ToolCall(tool="write_and_execute", error="boom"),
            ToolCall(tool="write_and_execute"),
        ],
    )
    assert cb.label == "LOW"
    assert cb.final < 0.5


def test_weights_formula_exact():
    # consistency=1 (0 kontradiksi), agreement=0.5, tools 1/2 ok, coverage=0.5
    cb = compute_confidence(
        verification=_verify(0.5),
        tool_calls=[ToolCall(tool="a", error="e"), ToolCall(tool="b")],
        data_coverage=0.5,
    )
    expected = 0.40 * 1.0 + 0.30 * 0.5 + 0.20 * 0.5 + 0.10 * 0.5
    assert abs(cb.final - round(expected, 4)) < 1e-6


def test_tool_success_helper():
    assert tool_execution_success([]) == 1.0
    assert tool_execution_success([ToolCall(tool="a"), ToolCall(tool="b", error="x")]) == 0.5


def test_consistency_from_verification():
    assert answer_consistency_from_verification(None) == 0.5
    assert answer_consistency_from_verification(_verify(1.0)) == 1.0
    assert answer_consistency_from_verification(_verify(1.0, ["c1"])) == 0.5


def test_label_boundaries():
    assert label_for(0.8) == "HIGH"
    assert label_for(0.79) == "MEDIUM"
    assert label_for(0.5) == "MEDIUM"
    assert label_for(0.49) == "LOW"


def test_no_verification_uses_neutral():
    cb = compute_confidence(verification=None, tool_calls=[ToolCall(tool="a")])
    assert cb.verification_agreement == 0.5
    assert cb.answer_consistency == 0.5
