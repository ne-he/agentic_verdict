"""Aggregate metrics untuk batch eval (T3.2).

Menerima list Scorecard → BatchSummary dengan semua metrik dirata-rata.
"""

from __future__ import annotations

from app.core.schemas import BatchSummary, Scorecard


def aggregate(scorecards: list[Scorecard]) -> BatchSummary:
    """Hitung BatchSummary dari list Scorecard.

    Semua metrik adalah rata-rata sederhana kecuali total_cost_usd (sum)
    dan hallucination_rate (fraksi 0–1).
    """
    n = len(scorecards)
    if n == 0:
        return BatchSummary(
            total=0,
            avg_correctness=0.0,
            total_cost_usd=0.0,
            hallucination_rate=0.0,
            avg_tool_calls=0.0,
            avg_time_to_insight=0.0,
        )
    return BatchSummary(
        total=n,
        avg_correctness=sum(s.correctness for s in scorecards) / n,
        total_cost_usd=sum(s.cost_usd for s in scorecards),
        hallucination_rate=sum(1 for s in scorecards if s.hallucination_flag) / n,
        avg_tool_calls=sum(s.tool_calls for s in scorecards) / n,
        avg_time_to_insight=sum(s.time_to_insight for s in scorecards) / n,
        run_ids=[s.run_id for s in scorecards],
    )
