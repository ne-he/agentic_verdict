"""Gold set loader & schema validator (T3.1).

Membaca semua *.json dari gold_set/ dan memvalidasi skema dengan Pydantic.
Pesan error eksplisit bila field kurang atau tipe salah.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from pydantic import ValidationError

from app.core.schemas import GoldQuestion, GoldSet

GOLD_SET_DIR = Path(__file__).parent / "gold_set"


def load_gold_set(path: Path) -> GoldSet:
    """Load dan validasi satu file gold set JSON.

    Raise ValueError dengan pesan jelas bila file tidak bisa dibaca
    atau skema tidak lengkap.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Gagal baca file '{path}': {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON tidak valid di '{path.name}': {exc}") from exc

    try:
        return GoldSet.model_validate(data)
    except ValidationError as exc:
        missing = [".".join(str(x) for x in e["loc"]) for e in exc.errors()]
        raise ValueError(
            f"Skema gold set tidak valid di '{path.name}'. "
            f"Field bermasalah: {missing}\nDetail:\n{exc}"
        ) from exc


def iter_questions(gold_dir: Path | None = None) -> Iterator[tuple[GoldSet, GoldQuestion]]:
    """Iterasi semua (GoldSet, GoldQuestion) dari setiap *.json di gold_dir.

    File diproses berurutan (sorted by name) supaya deterministic.
    """
    gold_dir = gold_dir or GOLD_SET_DIR
    for json_path in sorted(gold_dir.glob("*.json")):
        gold_set = load_gold_set(json_path)
        for question in gold_set.questions:
            yield gold_set, question


def load_all_questions(gold_dir: Path | None = None) -> list[tuple[GoldSet, GoldQuestion]]:
    """Kembalikan semua (GoldSet, GoldQuestion) sebagai list."""
    return list(iter_questions(gold_dir))
