"""CLI ANALYST — jalankan ReAct loop end-to-end di terminal (gate M1).

Contoh:
  python -m app.cli --dataset superstore --q "Berapa total penjualan keseluruhan?"
"""

from __future__ import annotations

import argparse
import sys

from app.agent.react_loop import ReactLoop
from app.core.datasets import list_datasets
from app.core.schemas import SSEEvent


def _print_event(ev: SSEEvent) -> None:
    if ev.type == "plan":
        print("\n=== RENCANA ===")
        for s in ev.data["steps"]:
            print(f"  {s['id']}. [{s['tool']}] {s['description']}")
        print("\n=== EKSEKUSI ===")
    elif ev.type == "step":
        print(f"  -> {ev.data['tool']}({ev.data.get('args', {})})")
    elif ev.type == "tool":
        print(f"     {'ok' if ev.data['ok'] else 'ERROR'}")
    elif ev.type == "chart":
        print(f"     chart: {ev.data['paths']}")
    elif ev.type == "verify":
        ok = "PASS" if ev.data["passed"] else "FAIL"
        print(f"\n=== VERIFIKASI [{ok}] ===")
        print(f"  A: {ev.data['method_a']}")
        print(f"  B: {ev.data['method_b']}")
        print(f"  agreement: {ev.data['agreement']}")
        for c in ev.data["contradictions"]:
            print(f"  ! {c}")
    elif ev.type == "confidence":
        d = ev.data
        print(f"\n=== CONFIDENCE: {d['label']} ({d['final']}) ===")
        print(
            f"  consistency={d['answer_consistency']} verify={d['verification_agreement']} "
            f"tool={d['tool_execution_success']} coverage={d['data_coverage']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="ANALYST ReAct CLI")
    parser.add_argument("--dataset", required=True, help=f"dataset_id. Tersedia: {list_datasets()}")
    parser.add_argument("--q", "--question", dest="question", required=True, help="pertanyaan NL")
    parser.add_argument("--max-tool-calls", type=int, default=12)
    args = parser.parse_args(argv)

    if args.dataset not in list_datasets():
        print(f"dataset '{args.dataset}' tidak dikenal. Tersedia: {list_datasets()}", file=sys.stderr)
        return 2

    loop = ReactLoop(max_tool_calls=args.max_tool_calls)
    result = loop.run(args.question, args.dataset, on_event=_print_event)

    print("\n=== JAWABAN ===")
    print(result.answer_markdown)
    print("\n=== KODE (reproducible) ===")
    print(result.code or "(tidak ada kode)")
    if result.chart_paths:
        print("\n=== CHART ===")
        for p in result.chart_paths:
            print(f"  {p}")
    print(f"\n[run_id={result.run_id} tool_calls={len(result.tool_calls)} ~tokens={result.tokens}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
