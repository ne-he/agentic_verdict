"""FastAPI entrypoint untuk ANALYST.

Jalankan dev:  uvicorn app.main:app --reload   (dari folder backend/)
Endpoint agent: /analyze (SSE), /run/{id}, /eval/dashboard, /datasets (lihat app/api/routes.py).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router as api_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: jalankan migrasi DB (create_all idempotent) → setup Neon/SQLite otomatis."""
    try:
        from app.db.session import create_tables

        create_tables()
        print("[startup] migrasi DB selesai — tabel siap.")
    except Exception as exc:  # noqa: BLE001 - app tetap boot walau DB belum siap
        # Jangan matikan app (health check tetap hijau); endpoint DB akan error sampai DB benar.
        print(f"[startup] WARN: migrasi DB gagal: {exc}")
    yield


app = FastAPI(
    title="ANALYST — Verified Analytics Agent",
    version=__version__,
    description="Ask questions. See the evidence. Verify every number.",
    lifespan=lifespan,
)

# CORS: domain frontend dibaca dari env ALLOWED_ORIGINS (koma-separated).
# Default = localhost dev. Di produksi set ke domain Vercel, mis:
#   ALLOWED_ORIGINS=https://analyst-xxxx.vercel.app
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins = os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check sederhana."""
    return {"status": "ok"}
