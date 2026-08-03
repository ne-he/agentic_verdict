"""Loader + skema adversarial eval set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CASES_PATH = Path(__file__).parent / "cases.json"

CATEGORIES: tuple[str, ...] = (
    "false_premise",
    "disguised_causal",
    "missing_column",
    "wrong_number_in_question",
)


class DetectSpec(BaseModel):
    """Aturan deteksi deterministik untuk satu kasus.

    Sengaja tidak pakai LLM judge di sini. Kalau grader-nya sendiri LLM, kita cuma
    menumpuk asumsi di atas asumsi (EVAL_DESIGN bagian 4). Keyword + toleransi
    numerik memang kasar, tapi hasilnya bisa direproduksi persis oleh orang lain.
    """

    # Minimal satu dari daftar ini harus muncul di jawaban (case-insensitive).
    must_contain_any: list[str] = Field(default_factory=list)
    # Angka yang harus muncul di jawaban (toleransi relatif).
    must_contain_value: float | None = None
    value_tolerance: float = 0.01
    # Kalau salah satu muncul, kasus dianggap JEBOL (agent menelan angka palsu).
    fail_if_contains_any: list[str] = Field(default_factory=list)
    # Intent yang diharapkan router (khusus kategori disguised_causal).
    expect_intent: str | None = None
    # True = lulus berarti agent menolak menjawab, bukan menjawab dengan benar.
    must_abstain: bool = False


class AdversarialCase(BaseModel):
    id: str
    category: str
    dataset_id: str
    question: str
    why_adversarial: str
    pass_if: str
    detect: DetectSpec


class AdversarialSet(BaseModel):
    note: str = ""
    dataset_facts: dict[str, Any] = Field(default_factory=dict)
    cases: list[AdversarialCase]

    def by_category(self) -> dict[str, list[AdversarialCase]]:
        out: dict[str, list[AdversarialCase]] = {}
        for case in self.cases:
            out.setdefault(case.category, []).append(case)
        return out

    def sample(self, per_category: int | None = None) -> list[AdversarialCase]:
        """Ambil N kasus pertama per kategori. None = semua.

        Dipakai saat kuota LLM tipis: lebih baik jalan 4 kasus dan menulis n=4
        secara eksplisit daripada mengklaim angka dari 12 kasus yang tak pernah jalan.
        """
        if per_category is None:
            return list(self.cases)
        picked: list[AdversarialCase] = []
        for cases in self.by_category().values():
            picked.extend(cases[:per_category])
        return picked


def load_cases(path: Path | None = None) -> AdversarialSet:
    """Baca + validasi adversarial set. Raise ValueError dengan pesan jelas kalau rusak."""
    path = path or CASES_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Gagal baca adversarial set '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON tidak valid di '{path.name}': {exc}") from exc

    aset = AdversarialSet.model_validate(raw)
    unknown = {c.category for c in aset.cases} - set(CATEGORIES)
    if unknown:
        raise ValueError(f"Kategori tidak dikenal di '{path.name}': {sorted(unknown)}")
    return aset
