"""Acceptance T0.2 — instansiasi tiap model dengan contoh valid + export JSON schema."""

import pytest
from pydantic import ValidationError

from app.core.export_schemas import build_schemas
from app.core.schemas import (
    EXPORTED_MODELS,
    AnalysisResult,
    AnalyzeRequest,
    ConfidenceBreakdown,
    PlanStep,
    Scorecard,
    SSEEvent,
    ToolCall,
    VerificationResult,
)


def test_analyze_request():
    req = AnalyzeRequest(question="Total sales?", dataset_id="superstore")
    assert req.session_id is None
    assert req.dataset_id == "superstore"


def test_plan_step_default_status():
    step = PlanStep(id=1, description="inspect schema", tool="inspect_schema")
    assert step.status == "pending"


def test_tool_call():
    tc = ToolCall(tool="write_and_execute", input={"code": "df.shape"}, output="(9994, 21)", duration_ms=120)
    assert tc.error is None
    assert tc.input["code"] == "df.shape"


def test_verification_result():
    vr = VerificationResult(
        method_a="pandas: 2297200.86",
        method_b="duckdb: 2297200.86",
        agreement=1.0,
        contradictions=[],
        passed=True,
    )
    assert vr.passed is True


def test_confidence_breakdown():
    cb = ConfidenceBreakdown(
        answer_consistency=0.9,
        verification_agreement=1.0,
        tool_execution_success=1.0,
        data_coverage=0.8,
        final=0.93,
        label="HIGH",
    )
    assert cb.label == "HIGH"


def test_analysis_result_minimal():
    res = AnalysisResult(run_id="run_001", answer_markdown="Total Sales = **$2.29M**", code="df['Sales'].sum()")
    assert res.chart_paths == []
    assert res.tool_calls == []
    assert res.confidence is None


def test_sse_event():
    ev = SSEEvent(type="plan", data={"steps": 5})
    assert ev.type == "plan"


def test_scorecard():
    sc = Scorecard(run_id="run_001", correctness=1.0, cost_usd=0.0003, tool_calls=4)
    assert sc.hallucination_flag is False


def test_invalid_confidence_label_rejected():
    with pytest.raises(ValidationError):
        ConfidenceBreakdown(
            answer_consistency=0.5,
            verification_agreement=0.5,
            tool_execution_success=0.5,
            data_coverage=0.5,
            final=0.5,
            label="VERY_HIGH",  # bukan literal valid
        )


def test_agreement_out_of_range_rejected():
    with pytest.raises(ValidationError):
        VerificationResult(method_a="a", method_b="b", agreement=1.5, passed=True)


def test_build_schemas_covers_all_models():
    schemas = build_schemas()
    assert len(schemas) == len(EXPORTED_MODELS)
    for model in EXPORTED_MODELS:
        assert model.__name__ in schemas
        assert "properties" in schemas[model.__name__]
