"""Acceptance T2.1 — self-verify.

Cocok -> passed=True, agreement tinggi. Sengaja salah -> kontradiksi terdeteksi, passed=False.
Cross-check pakai DuckDB in-process (tak butuh Docker).
"""

import json

from app.agent.self_verify import (
    SelfVerifier,
    compare_numbers,
    row_level_contradiction,
    run_sanity_checks,
)

DATASET = "superstore"
TOTAL_SALES = 2297200.86
TOTAL_SALES_SQL = 'SELECT SUM("Sales") FROM t'


def test_compare_numbers_match_and_mismatch():
    agr, within = compare_numbers(100.0, 100.0)
    assert within and agr == 1.0
    agr2, within2 = compare_numbers(100.0, 200.0)
    assert not within2 and agr2 < 1.0


def test_compare_handles_zero():
    agr, within = compare_numbers(0.0, 0.0)
    assert within and agr == 1.0


def test_cross_check_match_passes():
    v = SelfVerifier()
    res = v.verify_numeric(DATASET, TOTAL_SALES, TOTAL_SALES_SQL)
    assert res.passed is True
    assert res.agreement >= 0.99
    assert res.contradictions == []


def test_cross_check_wrong_value_detected():
    v = SelfVerifier()
    res = v.verify_numeric(DATASET, 9_999_999.0, TOTAL_SALES_SQL)
    assert res.passed is False
    assert res.agreement < 0.5
    assert any("cross-check" in c.lower() for c in res.contradictions)


def test_sanity_rule_failure_blocks_pass():
    v = SelfVerifier()
    # Angka cross-check cocok, tapi aturan domain dilanggar -> passed=False.
    res = v.verify_numeric(
        DATASET,
        TOTAL_SALES,
        TOTAL_SALES_SQL,
        sanity_rules=[("total revenue harus >= 0", False)],
    )
    assert res.passed is False
    assert "total revenue harus >= 0" in res.contradictions


def test_run_sanity_checks():
    assert run_sanity_checks([("a", True), ("b", False)]) == ["b"]
    assert run_sanity_checks(None) == []


def test_bad_sql_marks_unverified():
    v = SelfVerifier()
    res = v.verify_numeric(DATASET, TOTAL_SALES, "SELECT nonexistent_fn() FROM t")
    assert res.passed is False
    assert res.contradictions


def test_row_level_contradiction_with_mock_llm():
    rows = [{"Region": "West", "Profit": -50}, {"Region": "West", "Profit": 200}]

    def fake_generate(prompt: str) -> str:
        assert "West" in prompt
        return json.dumps(["Baris West profit -50 bertentangan dgn klaim West paling untung"])

    out = row_level_contradiction("West paling untung", rows, fake_generate)
    assert len(out) == 1 and "West" in out[0]


def test_row_level_contradiction_empty_on_bad_llm():
    out = row_level_contradiction("apa pun", [{"x": 1}], lambda p: "bukan json")
    assert out == []
