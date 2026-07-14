"""Acceptance T4.4 — katalog multi-dataset (aktif berdasarkan keberadaan file)."""

from __future__ import annotations

import pytest

from app.core import datasets as ds


def test_catalog_has_three_planned():
    """Katalog mendaftarkan 3 dataset terencana (superstore, olist, hr_attrition)."""
    ids = ds.catalog_ids()
    assert {"superstore", "olist", "hr_attrition"}.issubset(set(ids))


def test_superstore_active():
    """superstore.csv ada → masuk daftar aktif."""
    assert "superstore" in ds.list_datasets()


def test_inactive_when_file_missing():
    """Dataset terencana tanpa file CSV TIDAK muncul di list_datasets (tapi tetap di katalog)."""
    active = ds.list_datasets()
    # olist/hr belum ada datanya (kerjaan manual) → tidak aktif, tapi terdaftar di katalog.
    for ds_id in ("olist", "hr_attrition"):
        assert ds_id in ds.catalog_ids()
        if ds_id in active:
            # Kalau Nehemiah sudah menaruh filenya, harus benar-benar ada.
            assert ds.resolve_path(ds_id).exists()


def test_resolve_missing_dataset_raises():
    """resolve_path untuk dataset tanpa file → FileNotFoundError dengan pesan jelas."""
    if "olist" not in ds.list_datasets():
        with pytest.raises(FileNotFoundError, match="belum ada"):
            ds.resolve_path("olist")


def test_unknown_dataset_raises():
    with pytest.raises(ds.UnknownDatasetError):
        ds.resolve_path("tidak_ada_di_katalog")


def test_label_and_encoding():
    assert ds.get_encoding("superstore") == "latin-1"
    assert "Superstore" in ds.get_label("superstore")
