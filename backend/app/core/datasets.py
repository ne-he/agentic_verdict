"""Registry dataset: katalog dataset_id -> file + metadata (encoding, label).

Multi-dataset (T4.4): katalog mendaftarkan 3 dataset terencana (Blueprint §4 Tier B #10),
tapi `list_datasets()` HANYA mengembalikan yang file CSV-nya benar-benar ada di datasets/.
Jadi: drop `ecommerce_olist.csv` / `hr_attrition.csv` → dataset otomatis aktif di playground,
tanpa ubah kode. Sampai Nehemiah menaruh file-nya (kerjaan manual, lihat docs/03_MANUAL_TODO.md),
playground cuma menampilkan superstore.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

# Katalog SEMUA dataset terencana. Aktif/tidaknya ditentukan keberadaan file (lihat list_datasets).
DATASET_CATALOG: dict[str, dict[str, str]] = {
    "superstore": {
        "file": "superstore.csv",
        "encoding": "latin-1",
        "label": "Retail · Superstore",
    },
    "ab_marketing": {
        "file": "ab_marketing.csv",
        "encoding": "utf-8",
        "label": "Eksperimen · A/B Marketing (sintetik, ground-truth di ab_marketing.meta.json)",
    },
    "olist": {
        "file": "ecommerce_olist.csv",
        "encoding": "utf-8",
        "label": "E-commerce · Olist (Brazil)",
    },
    "hr_attrition": {
        "file": "hr_attrition.csv",
        "encoding": "utf-8",
        "label": "HR · IBM Attrition",
    },
}


class UnknownDatasetError(KeyError):
    """dataset_id tidak terdaftar di katalog."""


def _datasets_dir() -> Path:
    return get_settings().datasets_path


def _file_exists(meta: dict[str, str]) -> bool:
    return (_datasets_dir() / meta["file"]).exists()


def list_datasets() -> list[str]:
    """dataset_id yang AKTIF = terdaftar di katalog DAN file CSV-nya ada."""
    return [ds_id for ds_id, meta in DATASET_CATALOG.items() if _file_exists(meta)]


def catalog_ids() -> list[str]:
    """Semua dataset_id terencana (termasuk yang file-nya belum tersedia)."""
    return list(DATASET_CATALOG.keys())


def _meta(dataset_id: str) -> dict[str, str]:
    if dataset_id not in DATASET_CATALOG:
        raise UnknownDatasetError(
            f"dataset_id '{dataset_id}' tidak dikenal. Tersedia: {list_datasets()}"
        )
    return DATASET_CATALOG[dataset_id]


def resolve_path(dataset_id: str) -> Path:
    """Path absolut file dataset. Raise FileNotFoundError kalau file belum ada."""
    path = _datasets_dir() / _meta(dataset_id)["file"]
    if not path.exists():
        raise FileNotFoundError(
            f"File dataset '{dataset_id}' belum ada: {path}. "
            "Lihat docs/03_MANUAL_TODO.md (download CSV dari Kaggle)."
        )
    return path


def get_encoding(dataset_id: str) -> str:
    return _meta(dataset_id).get("encoding", "utf-8")


def get_label(dataset_id: str) -> str:
    return _meta(dataset_id).get("label", dataset_id)
