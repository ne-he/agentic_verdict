"""Pengaturan terpusat — semua secret & konfigurasi dibaca dari env (lihat .env.example).

ATURAN: jangan ada API key / nilai sensitif yang di-hardcode di sini.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Root project (dua level di atas file ini: backend/app/core -> backend -> root).
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Konfigurasi aplikasi. Diisi dari environment / file .env di root project."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"

    # Database
    database_url: str = "sqlite:///./backend/analyst.db"

    # Sandbox
    use_docker: bool = True
    sandbox_image: str = "analyst-sandbox:latest"
    sandbox_timeout_sec: int = 30
    sandbox_mem_mb: int = 512
    sandbox_cpus: int = 2

    # Data
    datasets_dir: str = "datasets"

    @property
    def datasets_path(self) -> Path:
        """Path absolut ke folder datasets."""
        return PROJECT_ROOT / self.datasets_dir


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton settings (cache sederhana, hindari baca .env berulang)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
