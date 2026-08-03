"""Script 2 dari 2: hitung agreement + Cohen's kappa dari CSV yang sudah dilabeli manusia.

Pemakaian:
  python -m app.eval.calibration_report --csv reports/calibration_sample.csv \\
      --out ../docs/EVAL_CALIBRATION.md

Aturan yang tidak boleh dilanggar (dari brief 04, Prompt B):
kalau agreement-nya rendah, JANGAN diam-diam tuning grader sampai angkanya naik.
Tulis angka aslinya, lalu tulis di mana grader dan manusia paling sering beda
pendapat. Analisis ketidaksepakatan itu jauh lebih bernilai daripada angka
agreement tinggi yang didapat dengan cara mencurigakan.

Script ini menolak menulis angka kalau kolom human_label masih kosong semua.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from app.eval.calibration import (
    LABELS,
    CalibrationReport,
    Pair,
    build_report,
    normalize_label,
    to_label,
)


def read_pairs(csv_path: Path) -> tuple[list[Pair], int, list[str]]:
    """Baca CSV → (pasangan terlabeli, total baris, peringatan)."""
    warnings: list[str] = []
    pairs: list[Pair] = []
    total = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            human = normalize_label(row.get("human_label", ""))
            if human is None:
                if (row.get("human_label") or "").strip():
                    warnings.append(
                        f"baris {total}: human_label '{row['human_label']}' tidak dikenal, dilewati"
                    )
                continue
            auto = (row.get("auto_label") or "").strip().lower()
            if auto not in LABELS:
                raw = (row.get("auto_correctness") or "").strip()
                if not raw:
                    warnings.append(f"baris {total}: tidak ada label otomatis, dilewati")
                    continue
                try:
                    auto = to_label(float(raw))
                except ValueError:
                    warnings.append(f"baris {total}: auto_correctness '{raw}' tidak terbaca")
                    continue
            pairs.append(
                Pair(
                    run_id=row.get("run_id", ""),
                    question_id=row.get("question_id", ""),
                    category=row.get("category", ""),
                    auto=auto,
                    human=human,
                )
            )
    return pairs, total, warnings


def render_markdown(report: CalibrationReport, csv_path: Path) -> str:
    lines: list[str] = []
    lines.append("# Kalibrasi Grader: VERDICT ANALYST")
    lines.append("")
    lines.append(
        f"*Dihasilkan `python -m app.eval.calibration_report --csv {csv_path.name}` "
        f"pada {date.today().isoformat()}.*"
    )
    lines.append("")
    lines.append(
        "Yang diukur: seberapa sejalan grader otomatis (`app/eval/grader.py`) dengan "
        "penilaian manusia atas jawaban agent yang sama. Tanpa angka ini, eval harness "
        "cuma opini mesin."
    )
    lines.append("")

    if report.is_empty:
        lines.append("## Status: MENUNGGU LABEL MANUSIA")
        lines.append("")
        lines.append(
            f"CSV punya {report.n_rows_total} baris, tapi belum ada satu pun kolom "
            "`human_label` yang terisi. Tidak ada angka agreement maupun kappa yang "
            "bisa dilaporkan."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("## Hasil")
    lines.append("")
    lines.append(f"- Baris di CSV: **{report.n_rows_total}**")
    lines.append(f"- Sudah dilabeli manusia (n): **{report.n_labeled}**")
    lines.append(f"- Agreement rate: **{report.agreement:.1%}**")
    kappa = "tidak terdefinisi" if report.kappa is None else f"{report.kappa:.3f}"
    lines.append(f"- Cohen's kappa: **{kappa}** ({report.kappa_interpretation})")
    lines.append("")
    if report.n_labeled < 50:
        lines.append(
            f"> Catatan kejujuran: n={report.n_labeled} itu kecil. Baca hasilnya sebagai "
            "arah, bukan kesimpulan."
        )
        lines.append("")

    lines.append("## Per kategori pertanyaan")
    lines.append("")
    lines.append("| Kategori | n | Agreement | Kappa |")
    lines.append("|---|---:|---:|---:|")
    for stat in report.by_category:
        k = "-" if stat.kappa is None else f"{stat.kappa:.3f}"
        lines.append(f"| {stat.category} | {stat.n} | {stat.agreement:.1%} | {k} |")
    lines.append("")

    lines.append("## Matriks bingung (baris = grader otomatis, kolom = manusia)")
    lines.append("")
    lines.append("| auto \\\\ human | " + " | ".join(LABELS) + " |")
    lines.append("|---|" + "---:|" * len(LABELS))
    for a in LABELS:
        cells = " | ".join(str(report.confusion[a][h]) for h in LABELS)
        lines.append(f"| **{a}** | {cells} |")
    lines.append("")

    lines.append("## Di mana grader dan manusia paling sering beda")
    lines.append("")
    if not report.disagreements:
        lines.append("Tidak ada ketidaksepakatan pada sampel ini.")
    else:
        from collections import Counter

        patterns = Counter((p.auto, p.human) for p in report.disagreements)
        for (a, h), count in patterns.most_common():
            lines.append(f"- grader bilang **{a}**, manusia bilang **{h}**: {count} kasus")
        lines.append("")
        lines.append("Run yang perlu dilihat manual:")
        for p in report.disagreements[:15]:
            lines.append(
                f"- `{p.run_id}` ({p.question_id or 'tanpa qid'}, {p.category or '-'}): "
                f"auto={p.auto}, human={p.human}"
            )
    lines.append("")
    lines.append("## Caveat yang wajib ikut dibaca")
    lines.append("")
    lines.append(
        "- Grader otomatis memakai Gemini untuk kasus yang tidak bisa dinilai numerik, "
        "dan agent yang dinilai juga memakai Gemini. Itu kasus teacher-sebagai-judge: "
        "sebagian agreement bisa datang dari kesamaan keluarga model, bukan dari kebenaran."
    )
    lines.append(
        "- Label manusia di sini dari satu orang. Tanpa rater kedua, tidak ada "
        "inter-rater agreement, jadi tidak ada cara tahu seberapa berisik label acuannya."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.eval.calibration_report",
        description="Hitung agreement + Cohen's kappa grader vs manusia",
    )
    parser.add_argument("--csv", type=Path, required=True,
                        help="CSV hasil export_calibration yang sudah diisi manusia")
    parser.add_argument("--out", type=Path, default=None, help="Tulis laporan markdown ke sini")
    parser.add_argument("--allow-empty", action="store_true",
                        help="Tetap tulis laporan berstatus MENUNGGU LABEL MANUSIA")
    args = parser.parse_args(argv)

    if not args.csv.exists():
        print(f"CSV tidak ditemukan: {args.csv}", file=sys.stderr)
        return 2

    pairs, total, warnings = read_pairs(args.csv)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    report = build_report(pairs, n_rows_total=total)

    if report.is_empty and not args.allow_empty:
        print(
            f"Belum ada label manusia di {args.csv} ({total} baris, 0 terisi).\n"
            "Isi kolom human_label dengan: benar | partial | salah, lalu jalankan lagi.\n"
            "Pakai --allow-empty kalau memang mau menulis laporan berstatus menunggu.",
            file=sys.stderr,
        )
        return 1

    print(f"n dilabeli       : {report.n_labeled} dari {report.n_rows_total} baris")
    print(f"Agreement rate   : {report.agreement:.1%}")
    print(
        "Cohen's kappa    : "
        + ("tidak terdefinisi" if report.kappa is None else f"{report.kappa:.3f}")
        + f" ({report.kappa_interpretation})"
    )
    for stat in report.by_category:
        print(f"  - {stat.category:<16} n={stat.n:<4} agreement={stat.agreement:.1%}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render_markdown(report, args.csv), encoding="utf-8")
        print(f"Laporan -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
