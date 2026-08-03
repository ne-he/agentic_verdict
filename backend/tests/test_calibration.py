"""Kalibrasi grader (brief 04, Prompt B): logika + dua script CLI.

Yang diuji: matematika kappa, konversi label, export CSV, dan yang paling penting
PENOLAKAN untuk mengarang angka saat label manusia belum ada.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.core.schemas import AnalysisResult, Scorecard
from app.db import repository
from app.db.session import configure_database, create_tables
from app.eval import calibration as cal
from app.eval.calibration_report import main as report_main
from app.eval.calibration_report import read_pairs, render_markdown
from app.eval.export_calibration import FIELDNAMES, collect_rows, write_csv
from app.eval.export_calibration import main as export_main


def _pairs(spec: list[tuple[str, str]], category: str = "descriptive") -> list[cal.Pair]:
    return [
        cal.Pair(run_id=f"run_{i}", question_id=f"q{i:03d}", category=category, auto=a, human=h)
        for i, (a, h) in enumerate(spec)
    ]


# ── Logika ───────────────────────────────────────────────────────────────────


def test_to_label_thresholds():
    assert cal.to_label(1.0) == "benar"
    assert cal.to_label(0.95) == "benar"
    assert cal.to_label(0.5) == "partial"
    assert cal.to_label(0.0) == "salah"


def test_normalize_label_accepts_human_variants():
    assert cal.normalize_label("Benar") == "benar"
    assert cal.normalize_label(" SEBAGIAN ") == "partial"
    assert cal.normalize_label("wrong") == "salah"
    assert cal.normalize_label("") is None
    assert cal.normalize_label("entah") is None


def test_agreement_rate_basic():
    pairs = _pairs([("benar", "benar"), ("benar", "salah"), ("salah", "salah"), ("partial", "partial")])
    assert cal.agreement_rate(pairs) == pytest.approx(0.75)


def test_kappa_is_one_on_perfect_agreement_with_spread():
    pairs = _pairs([("benar", "benar"), ("salah", "salah"), ("partial", "partial")] * 3)
    assert cal.cohens_kappa(pairs) == pytest.approx(1.0)


def test_kappa_is_zero_when_agreement_is_pure_chance():
    """Dua rater yang sama-sama selalu bilang 'benar' punya agreement 100% tapi kappa
    tidak terdefinisi, itu justru inti kenapa kappa dipakai, bukan agreement mentah."""
    pairs = _pairs([("benar", "benar")] * 10)
    assert cal.agreement_rate(pairs) == 1.0
    assert cal.cohens_kappa(pairs) is None  # expected agreement = 1 → penyebut nol


def test_kappa_negative_when_worse_than_chance():
    pairs = _pairs([("benar", "salah"), ("salah", "benar")] * 5)
    kappa = cal.cohens_kappa(pairs)
    assert kappa is not None and kappa < 0
    assert "acak" in cal.interpret_kappa(kappa)


def test_kappa_none_on_empty():
    assert cal.cohens_kappa([]) is None
    assert cal.interpret_kappa(None) == "tidak terdefinisi"


def test_breakdown_per_category():
    pairs = _pairs([("benar", "benar"), ("benar", "salah")], category="descriptive")
    pairs += _pairs([("salah", "salah")], category="statistical")
    stats = {s.category: s for s in cal.breakdown(pairs)}
    assert stats["descriptive"].n == 2 and stats["descriptive"].agreement == pytest.approx(0.5)
    assert stats["statistical"].n == 1 and stats["statistical"].agreement == pytest.approx(1.0)


def test_confusion_matrix_counts():
    pairs = _pairs([("benar", "partial"), ("benar", "partial"), ("salah", "salah")])
    m = cal.confusion(pairs)
    assert m["benar"]["partial"] == 2
    assert m["salah"]["salah"] == 1
    assert m["partial"]["benar"] == 0


def test_report_is_empty_when_no_human_labels():
    report = cal.build_report([], n_rows_total=20)
    assert report.is_empty
    assert report.n_labeled == 0
    assert report.kappa is None


# ── Export CSV ───────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_db(tmp_path):
    configure_database(f"sqlite:///{(tmp_path / 'cal.db').as_posix()}")
    create_tables()
    try:
        yield tmp_path
    finally:
        configure_database(None)


def _seed(n: int) -> None:
    for i in range(n):
        run_id = f"run_cal{i:03d}"
        repository.save_run(
            AnalysisResult(
                run_id=run_id,
                answer_markdown=f"Total = {1000 + i}",
                code="df.sum()",
                dataset_id="superstore",
            ),
            question=f"Pertanyaan ke-{i}?",
        )
        repository.save_scorecard(
            Scorecard(run_id=run_id, question_id="q001", correctness=1.0 if i % 2 else 0.0)
        )


def test_export_writes_csv_with_empty_human_label(seeded_db):
    _seed(5)
    rows = collect_rows(n=10)
    assert len(rows) == 5
    assert all(r["human_label"] == "" for r in rows)
    assert all(r["auto_label"] in cal.LABELS for r in rows)
    # Kategori diambil dari gold set lewat question_id.
    assert all(r["category"] for r in rows)

    out = seeded_db / "sample.csv"
    write_csv(rows, out)
    with out.open(encoding="utf-8-sig", newline="") as f:
        read_back = list(csv.DictReader(f))
    assert list(read_back[0].keys()) == FIELDNAMES
    assert len(read_back) == 5


def test_export_respects_n_flag(seeded_db):
    _seed(7)
    assert len(collect_rows(n=3)) == 3
    assert len(collect_rows(n=None)) == 7


def test_export_fails_loudly_on_empty_run_history(seeded_db, capsys):
    """run_history kosong → exit 1 dengan instruksi, bukan CSV kosong yang menyesatkan."""
    out = seeded_db / "empty.csv"
    code = export_main(["--n", "10", "--out", str(out)])
    assert code == 1
    assert not out.exists()
    assert "run_history KOSONG" in capsys.readouterr().err


# ── Report CLI ───────────────────────────────────────────────────────────────


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})


def _row(run_id: str, auto: str, human: str = "", category: str = "descriptive") -> dict[str, str]:
    return {
        "run_id": run_id, "question_id": "q001", "category": category,
        "dataset_id": "superstore", "question": "q?", "gold_answer": "g",
        "agent_answer": "a", "auto_correctness": "1.000", "auto_label": auto,
        "human_label": human,
    }


def test_report_refuses_to_run_without_human_labels(tmp_path, capsys):
    """INTI: tanpa label manusia, script menolak mengeluarkan angka."""
    csv_path = tmp_path / "unlabeled.csv"
    _write_csv(csv_path, [_row("r1", "benar"), _row("r2", "salah")])
    out = tmp_path / "report.md"

    code = report_main(["--csv", str(csv_path), "--out", str(out)])
    assert code == 1
    assert not out.exists()
    assert "Belum ada label manusia" in capsys.readouterr().err


def test_report_allow_empty_writes_waiting_status(tmp_path):
    csv_path = tmp_path / "unlabeled.csv"
    _write_csv(csv_path, [_row("r1", "benar")])
    out = tmp_path / "report.md"

    assert report_main(["--csv", str(csv_path), "--out", str(out), "--allow-empty"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "MENUNGGU LABEL MANUSIA" in text
    # Tidak boleh ada angka agreement yang dikarang.
    assert "Agreement rate" not in text


def test_report_computes_numbers_when_labeled(tmp_path):
    csv_path = tmp_path / "labeled.csv"
    _write_csv(
        csv_path,
        [
            _row("r1", "benar", "benar"),
            _row("r2", "benar", "salah"),
            _row("r3", "salah", "salah"),
            _row("r4", "partial", "partial", category="statistical"),
        ],
    )
    out = tmp_path / "report.md"
    assert report_main(["--csv", str(csv_path), "--out", str(out)]) == 0

    pairs, total, _ = read_pairs(csv_path)
    assert total == 4 and len(pairs) == 4
    report = cal.build_report(pairs, total)
    assert report.agreement == pytest.approx(0.75)

    text = out.read_text(encoding="utf-8")
    assert "75.0%" in text
    assert "Cohen's kappa" in text
    assert "statistical" in text
    assert "grader bilang **benar**, manusia bilang **salah**: 1 kasus" in text


def test_report_skips_rows_with_unrecognized_label(tmp_path):
    csv_path = tmp_path / "messy.csv"
    _write_csv(csv_path, [_row("r1", "benar", "benar"), _row("r2", "benar", "mungkin")])
    pairs, total, warnings = read_pairs(csv_path)
    assert total == 2 and len(pairs) == 1
    assert any("tidak dikenal" in w for w in warnings)


def test_rendered_report_carries_teacher_as_judge_caveat(tmp_path):
    pairs = _pairs([("benar", "benar"), ("salah", "benar")])
    report = cal.build_report(pairs, n_rows_total=2)
    text = render_markdown(report, Path("x.csv"))
    assert "teacher-sebagai-judge" in text
    assert "n=2 itu kecil" in text
