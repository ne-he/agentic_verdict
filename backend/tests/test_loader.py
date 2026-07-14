"""Acceptance T3.1 — Gold set loader & schema validator.

Test:
- loader baca superstore.json (20 Q) dengan benar
- loader baca direktori berisi beberapa file JSON
- field kurang → ValueError dengan pesan jelas
- JSON tidak valid → ValueError
- Dummy: 3 contoh gold question inline (dibuat di tmp_path)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.loader import load_all_questions, load_gold_set
from app.core.schemas import GoldSet, GoldQuestion

# ── Dummy gold set yang dipakai di test ──────────────────────────────────────

_DUMMY_BASE = {
    "dataset_id": "demo",
    "dataset_file": "datasets/demo.csv",
    "encoding": "utf-8",
}

DUMMY_Q1 = {
    "id": "d001",
    "category": "descriptive",
    "question": "Berapa total baris?",
    "gold_answer": "1000 baris",
    "gold_code": "len(df)",
    "expected_value": 1000.0,
    "allowed_tolerance": 0.0,
}

DUMMY_Q2 = {
    "id": "d002",
    "category": "diagnostic",
    "question": "Kolom apa yang punya nilai null terbanyak?",
    "gold_answer": "Column X dengan 50 null",
    "gold_code": "df.isnull().sum().idxmax()",
    "expected_value": 50.0,
    "allowed_tolerance": 0.01,
}

DUMMY_Q3 = {
    "id": "d003",
    "category": "edge_case",
    "question": "Berapa total penjualan di tahun 1800?",
    "gold_answer": "Tidak ada data untuk 1800.",
    "gold_code": "df[df.year==1800]['sales'].sum()",
    "expected_value": 0.0,
    "allowed_tolerance": 0.0,
    "is_trap": True,
    "trap_note": "Data mulai 2010, bukan 1800.",
}

_DUMMY_GOLD_SET = {**_DUMMY_BASE, "questions": [DUMMY_Q1, DUMMY_Q2, DUMMY_Q3]}


# ── Helper ────────────────────────────────────────────────────────────────────


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_load_superstore_gold_set():
    """Loader baca superstore.json (20 pertanyaan) tanpa error."""
    from app.eval.loader import GOLD_SET_DIR

    gs = load_gold_set(GOLD_SET_DIR / "superstore.json")
    assert gs.dataset_id == "superstore"
    assert len(gs.questions) == 20
    ids = [q.id for q in gs.questions]
    assert "q001" in ids and "q020" in ids


def test_load_superstore_question_fields():
    """Tiap pertanyaan superstore punya semua field wajib dengan tipe benar."""
    from app.eval.loader import GOLD_SET_DIR

    gs = load_gold_set(GOLD_SET_DIR / "superstore.json")
    for q in gs.questions:
        assert isinstance(q, GoldQuestion)
        assert q.id and q.question and q.gold_answer
        assert isinstance(q.expected_value, float)
        assert q.allowed_tolerance >= 0


def test_load_dummy_gold_set(tmp_path: Path):
    """Loader baca dummy gold set dengan 3 pertanyaan (termasuk is_trap)."""
    f = _write_json(tmp_path / "dummy.json", _DUMMY_GOLD_SET)
    gs = load_gold_set(f)
    assert gs.dataset_id == "demo"
    assert len(gs.questions) == 3
    trap = next(q for q in gs.questions if q.is_trap)
    assert trap.id == "d003" and trap.trap_note is not None


def test_load_all_questions_multiple_files(tmp_path: Path):
    """load_all_questions baca 2 file JSON → iterasi semua pertanyaan."""
    _write_json(tmp_path / "a.json", {**_DUMMY_BASE, "dataset_id": "ds_a", "questions": [DUMMY_Q1]})
    _write_json(tmp_path / "b.json", {**_DUMMY_BASE, "dataset_id": "ds_b", "questions": [DUMMY_Q2, DUMMY_Q3]})
    all_q = load_all_questions(tmp_path)
    assert len(all_q) == 3
    dataset_ids = {gs.dataset_id for gs, _ in all_q}
    assert dataset_ids == {"ds_a", "ds_b"}


def test_missing_required_field_raises_clear_error(tmp_path: Path):
    """ValueError dengan pesan informatif kalau field wajib kurang."""
    bad = {
        **_DUMMY_BASE,
        "questions": [
            {
                "id": "x001",
                "category": "descriptive",
                "question": "Test?",
                # gold_answer, gold_code, expected_value TIDAK ADA
            }
        ],
    }
    f = _write_json(tmp_path / "bad.json", bad)
    with pytest.raises(ValueError, match="Field bermasalah"):
        load_gold_set(f)


def test_invalid_json_raises_clear_error(tmp_path: Path):
    """ValueError dengan pesan informatif kalau JSON tidak valid."""
    f = tmp_path / "broken.json"
    f.write_text("{ini bukan json}", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON tidak valid"):
        load_gold_set(f)


def test_missing_dataset_id_raises_error(tmp_path: Path):
    """ValueError kalau field level root (dataset_id) hilang."""
    bad = {"questions": [DUMMY_Q1]}  # tanpa dataset_id
    f = _write_json(tmp_path / "nodataset.json", bad)
    with pytest.raises(ValueError, match="Field bermasalah"):
        load_gold_set(f)


def test_empty_gold_dir_returns_empty_list(tmp_path: Path):
    """Direktori kosong → list kosong, tidak error."""
    result = load_all_questions(tmp_path)
    assert result == []
