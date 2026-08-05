# Dockerfile untuk Hugging Face Spaces (Docker Space) — backend ANALYST.
# HF Spaces mengharapkan app listen di app_port (lihat frontmatter README.md → 7860).
# Frontend TIDAK di sini (itu di Vercel). Datasets ikut supaya agen bisa baca.

FROM python:3.11-slim

# libgomp1 = runtime OpenMP yang dibutuhkan scipy. rm cache biar image kecil.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps dulu (layer cache: tidak re-install tiap ganti kode).
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Kode backend + datasets. PROJECT_ROOT = /app (config.py parents[3]).
COPY backend backend
COPY datasets datasets

# Sandbox subprocess butuh dir tmp/artifacts writable (USE_DOCKER=false di HF).
RUN mkdir -p backend/sandbox/tmp backend/sandbox/artifacts \
    && chmod -R 777 backend/sandbox

ENV USE_DOCKER=false \
    GEMINI_MODEL=gemini-2.0-flash \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/mpl

# Jalankan dari backend/ supaya package `app` ke-resolve.
WORKDIR /app/backend
EXPOSE 7860

# Bentuk shell (bukan exec) supaya ${PORT} benar-benar diekspansi. Render menyuntik
# PORT sendiri (10000) dan menganggap service mati kalau tidak ada yang listen di
# sana; 7860 dipakai sebagai fallback supaya `docker run` lokal tetap jalan apa adanya.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}
