"""Runner adversarial eval.

Pemakaian:
  python -m app.eval.adversarial.runner                       # semua kasus
  python -m app.eval.adversarial.runner --per-category 1      # subset hemat kuota
  python -m app.eval.adversarial.runner --category false_premise
  python -m app.eval.adversarial.runner --out reports/adv.json --markdown docs/ADVERSARIAL_EVAL.md

Butuh GEMINI_API_KEY dan kuota LLM. Tiap kasus = satu run agent penuh (planner +
beberapa tool call), jadi 12 kasus bisa memakan puluhan panggilan model.

Kalau kuota habis, runner TIDAK menulis angka apa pun: dia menandai kasusnya
"error" dan laporan yang keluar menyebut n yang sebenarnya. Lebih baik laporan
kosong yang jujur daripada angka yang tidak pernah dihitung.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Callable

from app.core.schemas import AnalysisResult
from app.eval.adversarial.loader import CATEGORIES, AdversarialCase, load_cases
from app.eval.adversarial.scorer import (
    AdversarialSummary,
    CaseOutcome,
    score_case,
    summarize,
)

RunFn = Callable[[str, str], AnalysisResult]


def _default_run_fn(model: str | None = None, max_tool_calls: int = 12) -> RunFn:
    from app.agent.checkpoint import SqliteCheckpointer
    from app.agent.react_loop import ReactLoop

    loop = ReactLoop(
        model=model, max_tool_calls=max_tool_calls, checkpointer=SqliteCheckpointer()
    )
    return lambda question, dataset_id: loop.run(question, dataset_id)


def run_adversarial(
    cases: list[AdversarialCase],
    run_fn: RunFn | None = None,
    delay_s: float = 2.0,
    verbose: bool = True,
) -> tuple[list[CaseOutcome], AdversarialSummary]:
    """Jalankan tiap kasus, nilai hasilnya, kembalikan (outcomes, summary)."""
    if run_fn is None:
        run_fn = _default_run_fn()

    outcomes: list[CaseOutcome] = []
    for i, case in enumerate(cases, start=1):
        if verbose:
            print(f"[{i:02d}/{len(cases)}] {case.id} ({case.category}): {case.question[:60]}...")
        result: AnalysisResult | None = None
        try:
            result = run_fn(case.question, case.dataset_id)
        except Exception as exc:  # noqa: BLE001 - satu kasus gagal != batch gagal
            if verbose:
                print(f"       ERROR: {exc}")
        outcome = score_case(case, result)
        outcomes.append(outcome)
        if verbose:
            print(f"       -> {outcome.outcome}  ({'; '.join(outcome.reasons[:2])})")
        if delay_s and i < len(cases):
            time.sleep(delay_s)  # jeda ramah rate limit free tier

    return outcomes, summarize(outcomes)


def rescore_from_json(path: Path) -> tuple[list[CaseOutcome], AdversarialSummary]:
    """Nilai ulang hasil run yang tersimpan, TANPA memanggil LLM lagi.

    Ada karena kuota free tier: kalau aturan deteksi diperbaiki, jangan bakar
    kuota cuma untuk mengulang jawaban yang sudah pernah didapat. Butuh field
    `answer_full` di JSON (ditulis runner versi 2 Agu 2026 ke atas).
    """
    from app.core.schemas import AnalysisResult

    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id = {c.id: c for c in load_cases().cases}
    outcomes: list[CaseOutcome] = []
    for row in payload.get("outcomes", []):
        case = by_id.get(row["case_id"])
        if case is None:
            continue
        if row.get("outcome") == "error":
            outcomes.append(CaseOutcome(**row))
            continue
        answer = row.get("answer_full") or row.get("answer_excerpt", "")
        stub = AnalysisResult(
            run_id=row.get("run_id", ""),
            answer_markdown=answer,
            code="",
            dataset_id=case.dataset_id,
            intent=row.get("intent") or "descriptive",
            termination_reason=row.get("termination_reason") or "completed",
        )
        outcomes.append(score_case(case, stub))
    return outcomes, summarize(outcomes)


def render_markdown(
    outcomes: list[CaseOutcome], summary: AdversarialSummary, command: str
) -> str:
    """Laporan markdown. Kalau semua kasus error, laporan menyebutnya apa adanya."""
    lines: list[str] = []
    lines.append("# Adversarial Eval: VERDICT ANALYST")
    lines.append("")
    lines.append(f"*Dihasilkan otomatis oleh `{command}` pada {date.today().isoformat()}.*")
    lines.append("")

    if summary.error == summary.n and summary.n > 0:
        lines.append("## Status: GAGAL DIJALANKAN")
        lines.append("")
        lines.append(
            f"Seluruh {summary.n} kasus error (kemungkinan besar kuota LLM habis). "
            "Tidak ada angka yang bisa dilaporkan."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("## Ringkasan")
    lines.append("")
    lines.append(f"- Kasus dijalankan (n): **{summary.n}**")
    lines.append(
        f"- Tertangkap (agent menolak premis / mengoreksi angka / abstain): "
        f"**{summary.caught}** ({summary.caught_rate:.0%})"
    )
    lines.append(
        f"- Jebol jadi jawaban percaya diri yang salah: "
        f"**{summary.confident_wrong}** ({summary.confident_wrong_rate:.0%})"
    )
    lines.append(f"- Tidak jelas: **{summary.unclear}**")
    lines.append(f"- Error / tidak jalan: **{summary.error}**")
    lines.append("")
    lines.append("## Per kategori")
    lines.append("")
    lines.append("| Kategori | n | Tertangkap | Jebol | Tidak jelas | Error |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat in CATEGORIES:
        row = summary.by_category.get(cat)
        if not row:
            continue
        lines.append(
            f"| {cat} | {row['n']} | {row['caught']} | {row['confident_wrong']} "
            f"| {row['unclear']} | {row['error']} |"
        )
    lines.append("")
    lines.append("## Detail per kasus")
    lines.append("")
    for o in outcomes:
        lines.append(f"### {o.case_id} ({o.category}) → **{o.outcome}**")
        lines.append("")
        if o.reasons:
            for r in o.reasons:
                lines.append(f"- {r}")
        if o.intent:
            lines.append(f"- intent={o.intent}, terminasi={o.termination_reason}")
        if o.answer_excerpt:
            lines.append("")
            lines.append("```")
            lines.append(o.answer_excerpt)
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.eval.adversarial.runner",
        description="Jalankan adversarial eval set terhadap agent",
    )
    parser.add_argument("--per-category", type=int, default=None,
                        help="Ambil N kasus pertama per kategori (hemat kuota LLM)")
    parser.add_argument("--category", type=str, default=None,
                        help=f"Batasi ke satu kategori: {', '.join(CATEGORIES)}")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Jeda detik antar kasus (ramah rate limit)")
    parser.add_argument("--model", type=str, default=None,
                        help="Override GEMINI_MODEL (mis. gemini-flash-lite-latest saat kuota tipis)")
    parser.add_argument("--max-tool-calls", type=int, default=12,
                        help="Batas langkah per kasus; turunkan untuk menghemat panggilan LLM")
    parser.add_argument("--out", type=Path, default=None, help="Tulis hasil mentah ke JSON")
    parser.add_argument("--markdown", type=Path, default=None, help="Tulis laporan markdown")
    parser.add_argument("--rescore", type=Path, default=None,
                        help="Nilai ulang JSON hasil run sebelumnya, tanpa memanggil LLM")
    args = parser.parse_args(argv)

    if args.rescore:
        if not args.rescore.exists():
            print(f"File tidak ditemukan: {args.rescore}", file=sys.stderr)
            return 2
        outcomes, summary = rescore_from_json(args.rescore)
    else:
        aset = load_cases()
        cases = aset.sample(args.per_category)
        if args.category:
            cases = [c for c in cases if c.category == args.category]
        if not cases:
            print("Tidak ada kasus yang cocok dengan filter.", file=sys.stderr)
            return 2

        outcomes, summary = run_adversarial(
            cases,
            run_fn=_default_run_fn(args.model, args.max_tool_calls),
            delay_s=args.delay,
        )

    print("\n" + "=" * 54)
    print("=== ADVERSARIAL EVAL ===")
    print("=" * 54)
    print(f"  n                : {summary.n}")
    print(f"  Tertangkap       : {summary.caught} ({summary.caught_rate:.0%})")
    print(f"  Jebol (confident): {summary.confident_wrong} ({summary.confident_wrong_rate:.0%})")
    print(f"  Tidak jelas      : {summary.unclear}")
    print(f"  Error            : {summary.error}")
    print("=" * 54)

    cmd = "python -m app.eval.adversarial.runner"
    if args.rescore:
        cmd += f" --rescore {args.rescore}"
    if args.per_category:
        cmd += f" --per-category {args.per_category}"
    if args.category:
        cmd += f" --category {args.category}"
    if args.model:
        cmd += f" --model {args.model}"
    if args.max_tool_calls != 12:
        cmd += f" --max-tool-calls {args.max_tool_calls}"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "summary": summary.model_dump(),
                    "outcomes": [o.model_dump() for o in outcomes],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON  -> {args.out}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(outcomes, summary, cmd), encoding="utf-8")
        print(f"Report-> {args.markdown}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
