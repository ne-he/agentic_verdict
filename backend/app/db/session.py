"""Engine + session factory (T3.4).

DATABASE_URL dari config (default SQLite analyst.db).
Memanggil create_tables() sekali saat startup untuk buat tabel yang belum ada.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PROJECT_ROOT, get_settings
from app.db.models import Base

_engine = None
_SessionLocal = None
_url_override: str | None = None


def configure_database(url: str | None) -> None:
    """Arahkan engine ke URL lain (dipakai test ke DB sementara). url=None → reset ke default .env."""
    global _engine, _SessionLocal, _url_override
    _url_override = url
    _engine = None
    _SessionLocal = None


def _normalize_sqlite_url(url: str) -> str:
    """Path SQLite relatif → absolut terhadap PROJECT_ROOT (anti-bug tergantung CWD).

    `sqlite:///./backend/analyst.db` akan resolve ke file yang sama apa pun direktori
    kerja (uvicorn dari backend/, pytest dari backend/, dll). Sekaligus pastikan
    folder induknya ada.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    raw = url[len(prefix) :]
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        # Sudah absolut (POSIX '/...' atau Windows 'C:...').
        path = Path(raw)
    else:
        path = (PROJECT_ROOT / raw).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{path.as_posix()}"


def _get_engine():
    global _engine
    if _engine is None:
        url = _url_override or get_settings().database_url
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            url = _normalize_sqlite_url(url)
        _engine = create_engine(url, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


# Kolom yang ditambahkan setelah rilis pertama. create_all() cuma bikin tabel baru,
# tidak menambah kolom ke tabel lama, jadi DB yang sudah ada perlu ALTER manual.
# Format: (nama tabel, nama kolom, definisi DDL).
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("run_history", "termination_reason", "VARCHAR(32) NOT NULL DEFAULT 'completed'"),
]


def _apply_column_migrations(engine) -> None:
    """Tambahkan kolom baru ke tabel lama (idempotent, aman dipanggil berulang).

    Sengaja dibuat minimal, bukan Alembic: repo ini cuma punya satu jenis
    perubahan skema (tambah kolom nullable/berdefault) dan DB-nya SQLite lokal.
    Kalau nanti pindah Postgres dengan perubahan yang lebih rumit, ganti ke Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def create_tables() -> None:
    """Buat semua tabel yang belum ada + migrasi kolom tambahan (idempotent)."""
    engine = _get_engine()
    Base.metadata.create_all(engine)
    _apply_column_migrations(engine)


def get_session() -> Session:
    """Buat session baru. Caller harus close() setelah selesai."""
    return get_session_factory()()
