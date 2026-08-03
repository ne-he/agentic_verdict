"""Kalibrasi grader ke penilaian manusia: Skill 4 (brief 04, Prompt B).

Kenapa ini ada. Eval harness repo ini menilai jawaban agent dengan dua jalur:
toleransi numerik (keras, bisa direproduksi) dan LLM judge Gemini (lunak, belum
pernah dibuktikan sejalan dengan manusia). Skor keduanya masuk ke `avg_correctness`
dengan bobot yang sama. Selama judge itu belum dikalibrasi, `avg_correctness` adalah
campuran antara pengukuran dan asumsi.

Ironinya tajam kalau dibiarkan: agent yang tugasnya menilai kejujuran analisis,
grader-nya sendiri belum pernah dibuktikan sejalan dengan penilaian manusia.

Modul ini berisi logika murni (tanpa I/O CLI) supaya bisa di-test tanpa DB:
  - `to_label()`      : correctness float → label 3 kelas
  - `agreement_rate()`: proporsi label yang sama persis
  - `cohens_kappa()`  : agreement yang sudah dikoreksi peluang kebetulan
  - `confusion()`     : matriks bingung auto vs manusia
  - `breakdown()`     : agreement per kategori pertanyaan

CLI-nya ada di app/eval/export_calibration.py dan app/eval/calibration_report.py.

CATATAN PENTING: tidak ada satu pun angka agreement di repo ini yang boleh
ditulis tanpa CSV yang sudah diisi manusia. Kalau CSV-nya kosong, semua fungsi
di bawah mengembalikan n=0, bukan angka default.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence

from pydantic import BaseModel

# Tiga kelas label. Sengaja sama untuk grader otomatis dan manusia supaya
# perbandingannya apple-to-apple.
LABELS: tuple[str, str, str] = ("benar", "partial", "salah")

# Ambang konversi correctness (0.0–1.0) ke label. Ikut semantik grader:
# 1.0 = tepat, 0.5 = approach benar angka meleset, 0.0 = salah.
BENAR_THRESHOLD = 0.9
SALAH_THRESHOLD = 0.1


def to_label(correctness: float) -> str:
    """correctness float → salah satu dari LABELS."""
    if correctness >= BENAR_THRESHOLD:
        return "benar"
    if correctness <= SALAH_THRESHOLD:
        return "salah"
    return "partial"


def normalize_label(raw: str) -> str | None:
    """Normalisasi label isian manusia. Return None kalau kosong / tidak dikenal.

    Toleran terhadap variasi yang wajar diketik manusia: kapital, spasi,
    'sebagian', 'benar sebagian', 'wrong', 'correct'.
    """
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v:
        return None
    if v in ("benar", "correct", "true", "b", "1"):
        return "benar"
    if v in ("salah", "wrong", "false", "s", "0"):
        return "salah"
    if v in ("partial", "sebagian", "benar sebagian", "p", "0.5"):
        return "partial"
    return None


class Pair(BaseModel):
    """Satu baris terlabeli: penilaian grader otomatis vs penilaian manusia."""

    run_id: str = ""
    question_id: str = ""
    category: str = ""
    auto: str
    human: str


def agreement_rate(pairs: Sequence[Pair]) -> float:
    """Proporsi baris yang label otomatis dan manusianya sama persis."""
    if not pairs:
        return 0.0
    return sum(1 for p in pairs if p.auto == p.human) / len(pairs)


def confusion(pairs: Sequence[Pair]) -> dict[str, dict[str, int]]:
    """Matriks bingung: confusion[auto][human] = jumlah."""
    matrix = {a: {h: 0 for h in LABELS} for a in LABELS}
    for p in pairs:
        if p.auto in matrix and p.human in matrix[p.auto]:
            matrix[p.auto][p.human] += 1
    return matrix


def cohens_kappa(pairs: Sequence[Pair]) -> float | None:
    """Cohen's kappa untuk dua rater (grader otomatis vs manusia).

    Kenapa bukan agreement mentah saja: kalau 90 persen jawaban memang benar,
    grader yang selalu menjawab "benar" dapat agreement 90 persen tanpa
    mengukur apa pun. Kappa mengoreksi peluang kebetulan itu.

    Return None kalau tidak bisa dihitung (n=0, atau expected agreement = 1
    sehingga penyebutnya nol). None berarti "tidak terdefinisi", BUKAN nol.
    """
    n = len(pairs)
    if n == 0:
        return None
    observed = agreement_rate(pairs)
    auto_counts = Counter(p.auto for p in pairs)
    human_counts = Counter(p.human for p in pairs)
    expected = sum((auto_counts[l] / n) * (human_counts[l] / n) for l in LABELS)
    if abs(1.0 - expected) < 1e-12:
        return None
    return (observed - expected) / (1.0 - expected)


def interpret_kappa(kappa: float | None) -> str:
    """Terjemahan kasar kappa ke bahasa manusia (skala Landis & Koch)."""
    if kappa is None:
        return "tidak terdefinisi"
    if kappa < 0:
        return "lebih buruk dari tebakan acak"
    if kappa < 0.21:
        return "sangat lemah"
    if kappa < 0.41:
        return "lemah"
    if kappa < 0.61:
        return "sedang"
    if kappa < 0.81:
        return "kuat"
    return "sangat kuat"


class CategoryStat(BaseModel):
    category: str
    n: int
    agreement: float
    kappa: float | None = None


def breakdown(pairs: Sequence[Pair]) -> list[CategoryStat]:
    """Agreement + kappa per kategori pertanyaan, urut nama kategori."""
    groups: dict[str, list[Pair]] = {}
    for p in pairs:
        groups.setdefault(p.category or "(tanpa kategori)", []).append(p)
    return [
        CategoryStat(
            category=cat,
            n=len(items),
            agreement=agreement_rate(items),
            kappa=cohens_kappa(items),
        )
        for cat, items in sorted(groups.items())
    ]


class CalibrationReport(BaseModel):
    """Hasil kalibrasi lengkap. n=0 berarti belum ada label manusia sama sekali."""

    n_rows_total: int
    n_labeled: int
    agreement: float
    kappa: float | None
    kappa_interpretation: str
    by_category: list[CategoryStat]
    confusion: dict[str, dict[str, int]]
    disagreements: list[Pair]

    @property
    def is_empty(self) -> bool:
        return self.n_labeled == 0


def build_report(pairs: Iterable[Pair], n_rows_total: int) -> CalibrationReport:
    """Rakit laporan kalibrasi dari pasangan label yang SUDAH terisi."""
    items = list(pairs)
    kappa = cohens_kappa(items)
    return CalibrationReport(
        n_rows_total=n_rows_total,
        n_labeled=len(items),
        agreement=agreement_rate(items),
        kappa=kappa,
        kappa_interpretation=interpret_kappa(kappa),
        by_category=breakdown(items),
        confusion=confusion(items),
        disagreements=[p for p in items if p.auto != p.human],
    )
