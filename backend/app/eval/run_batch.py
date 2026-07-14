"""Batch eval runner (T3.3).

Jalankan semua gold questions, grade tiap hasil, simpan scorecard ke DB,
cetak agregat di akhir.

Pemakaian:
  python -m app.eval.run_batch
  python -m app.eval.run_batch --gold-dir path/to/gold_set
  python -m app.eval.run_batch --max-questions 5   # untuk smoke test cepat
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable

from app.agent.react_loop import ReactLoop
from app.core.schemas import AnalysisResult, BatchSummary, GoldQuestion, GoldSet, Scorecard
from app.eval.grader import grade
from app.eval.loader import GOLD_SET_DIR, load_all_questions
from app.eval.metrics import aggregate

# Tipe untuk injectable ReactLoop factory (memudahkan unit test tanpa Gemini/Docker)
RunFn = Callable[[str, str], AnalysisResult]


def _default_run_fn() -> RunFn:
    """Buat RunFn default pakai ReactLoop nyata."""
    loop = ReactLoop()
    return lambda question, dataset_id: loop.run(question, dataset_id)


def run_batch(
    gold_dir: Path | None = None,
    max_questions: int | None = None,
    run_fn: RunFn | None = None,
    save_fn: Callable[[Scorecard], None] | None = None,
    verbose: bool = True,
) -> BatchSummary:
    """Jalankan batch eval dan kembalikan BatchSummary.

    Args:
        gold_dir:       direktori gold set JSON (default: app/eval/gold_set/).
        max_questions:  batasi jumlah pertanyaan (untuk smoke test).
        run_fn:         callable(question, dataset_id) → AnalysisResult (injectable untuk test).
        save_fn:        callable(Scorecard) → None untuk persist ke DB (injectable).
        verbose:        cetak progress ke stdout.
    """
    if run_fn is None:
        run_fn = _default_run_fn()

    all_questions = load_all_questions(gold_dir)
    if max_questions:
        all_questions = all_questions[:max_questions]

    if verbose:
        print(f"\n=== BATCH EVAL — {len(all_questions)} pertanyaan ===\n")

    scorecards: list[Scorecard] = []

    for i, (gold_set, gold_q) in enumerate(all_questions, start=1):
        if verbose:
            print(f"[{i:02d}/{len(all_questions)}] {gold_q.id}: {gold_q.question[:60]}...")

        t0 = time.monotonic()
        try:
            result = run_fn(gold_q.question, gold_set.dataset_id)
        except Exception as exc:
            if verbose:
                print(f"       ERROR: {exc}")
            # Buat result kosong supaya scoring tetap jalan (correctness=0)
            from app.agent.react_loop import ReactLoop as _RL
            result = AnalysisResult(
                run_id=f"error_{gold_q.id}_{int(time.monotonic()*1000)}",
                answer_markdown=f"[ERROR] {exc}",
                code="",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        sc = grade(result, gold_q)
        scorecards.append(sc)

        if save_fn is not None:
            save_fn(sc)

        if verbose:
            flag = "HALLUC" if sc.hallucination_flag else "ok"
            print(
                f"       correctness={sc.correctness:.2f}  "
                f"tools={sc.tool_calls}  "
                f"t={sc.time_to_insight:.1f}s  [{flag}]"
            )

    summary = aggregate(scorecards)

    if verbose:
        _print_summary(summary)

    return summary


def _print_summary(s: BatchSummary) -> None:
    print("\n" + "=" * 50)
    print("=== HASIL BATCH EVAL ===")
    print("=" * 50)
    print(f"  Total pertanyaan  : {s.total}")
    print(f"  Avg correctness   : {s.avg_correctness:.3f}")
    print(f"  Total cost        : ${s.total_cost_usd:.4f}")
    print(f"  Hallucination rate: {s.hallucination_rate:.1%}")
    print(f"  Avg tool calls    : {s.avg_tool_calls:.1f}")
    print(f"  Avg time-to-insight: {s.avg_time_to_insight:.1f}s")
    print("=" * 50)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.eval.run_batch",
        description="Jalankan batch eval semua gold questions",
    )
    parser.add_argument(
        "--gold-dir",
        type=Path,
        default=None,
        help=f"Direktori gold set JSON (default: {GOLD_SET_DIR})",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Batasi jumlah pertanyaan (untuk smoke test)",
    )
    args = parser.parse_args(argv)

    try:
        from app.db.repository import save_scorecard
        save_fn: Callable[[Scorecard], None] | None = save_scorecard
    except ImportError:
        save_fn = None

    run_batch(gold_dir=args.gold_dir, max_questions=args.max_questions, save_fn=save_fn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
