"""Script 1 dari 2: export jawaban agent dari run history ke CSV untuk dilabeli manusia.

Pemakaian:
  python -m app.eval.export_calibration --n 150 --out reports/calibration_sample.csv
  python -m app.eval.export_calibration --n 20                 # sebanyak yang tersedia
  python -m app.eval.export_calibration --all

Kolom `human_label` sengaja DIKOSONGKAN. Isi manual dengan salah satu dari:
  benar | partial | salah
Kolom `human_note` opsional, untuk catatan kenapa kamu tidak setuju dengan grader.

Jangan mengurutkan atau memfilter berdasarkan skor grader sebelum melabeli.
Kalau kamu cuma melabeli baris yang grader-nya sudah bilang benar, agreement
yang keluar akan tinggi dan tidak berarti apa-apa.

Setelah CSV diisi, jalankan:
  python -m app.eval.calibration_report --csv reports/calibration_sample.csv \\
      --out ../docs/EVAL_CALIBRATION.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from app.core.schemas import RunRecord
from app.db import repository
from app.eval.calibration import to_label
from app.eval.loader import load_all_questions

FIELDNAMES = [
    "run_id",
    "question_id",
    "category",
    "dataset_id",
    "question",
    "gold_answer",
    "agent_answer",
    "auto_correctness",
    "auto_label",
    "hallucination_flag",
    "termination_reason",
    "human_label",   # DIISI MANUSIA: benar | partial | salah
    "human_note",    # DIISI MANUSIA: opsional
]


def _gold_index(gold_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """question_id → {category, question, gold_answer} dari file gold set."""
    index: dict[str, dict[str, str]] = {}
    try:
        for _gold_set, q in load_all_questions(gold_dir):
            index[q.id] = {
                "category": q.category,
                "question": q.question,
                "gold_answer": q.gold_answer,
            }
    except Exception:  # noqa: BLE001 - gold set rusak tidak boleh menggagalkan export
        pass
    return index


def collect_rows(n: int | None = None, gold_dir: Path | None = None) -> list[dict[str, str]]:
    """Rakit baris CSV dari run_history + scorecards. Kosong kalau run_history kosong."""
    limit = n if n is not None else 100_000
    runs: list[RunRecord] = repository.list_run_records(limit=limit)
    scorecards = repository.scorecard_map([r.run_id for r in runs])
    gold = _gold_index(gold_dir)

    rows: list[dict[str, str]] = []
    for run in runs:
        sc = scorecards.get(run.run_id)
        question_id = sc["question_id"] if sc else ""
        meta = gold.get(question_id, {})
        correctness = sc["correctness"] if sc else None
        rows.append(
            {
                "run_id": run.run_id,
                "question_id": question_id,
                "category": meta.get("category", ""),
                "dataset_id": run.dataset_id,
                "question": run.question,
                "gold_answer": meta.get("gold_answer", ""),
                "agent_answer": (run.answer_markdown or "").replace("\r", " "),
                "auto_correctness": "" if correctness is None else f"{correctness:.3f}",
                "auto_label": "" if correctness is None else to_label(correctness),
                "hallucination_flag": str(sc["hallucination_flag"]) if sc else "",
                "termination_reason": run.termination_reason,
                "human_label": "",
                "human_note": "",
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.eval.export_calibration",
        description="Export jawaban agent ke CSV untuk dilabeli manusia",
    )
    parser.add_argument("--n", type=int, default=150,
                        help="Jumlah run yang diambil (default 150; ambil sebanyak yang ada)")
    parser.add_argument("--all", action="store_true", help="Ambil semua run yang tersedia")
    parser.add_argument("--out", type=Path, default=Path("reports/calibration_sample.csv"))
    parser.add_argument("--gold-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    repository.init_db()
    requested = None if args.all else args.n
    rows = collect_rows(requested, args.gold_dir)

    if not rows:
        n_scorecards = len(repository.list_scorecards(limit=100_000))
        print(
            "run_history KOSONG, tidak ada jawaban agent yang bisa diekspor.\n"
            f"(scorecards di DB: {n_scorecards} baris, tapi scorecard cuma menyimpan SKOR, "
            "bukan teks jawaban.)\n\n"
            "Isi run_history dulu dengan menjalankan eval batch:\n"
            "  python -m app.eval.run_batch\n"
            "atau lewat UI/API /analyze. Baru export lagi.",
            file=sys.stderr,
        )
        return 1

    write_csv(rows, args.out)
    print(f"Ditulis {len(rows)} baris ke {args.out}")
    if requested is not None and len(rows) < requested:
        print(
            f"CATATAN: diminta {requested} sampel, yang tersedia di run_history cuma {len(rows)}. "
            "Tulis n yang sebenarnya di laporan, jangan angka yang diminta."
        )
    print("\nLangkah berikutnya:")
    print(f"  1. Buka {args.out}, isi kolom human_label: benar | partial | salah")
    print("  2. python -m app.eval.calibration_report --csv "
          f"{args.out} --out ../docs/EVAL_CALIBRATION.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
