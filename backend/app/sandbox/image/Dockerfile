# Sandbox image untuk eksekusi kode hasil LLM — TERISOLASI.
# Build:  docker build -t analyst-sandbox backend/app/sandbox/image
# Lib di-whitelist (hanya yang dibutuhkan analitik). User non-root. No network saat run.
FROM python:3.11-slim

# Versi dipin (selaras dgn backend). Jangan pakai 'latest'.
RUN pip install --no-cache-dir \
    "pandas==2.2.*" \
    "numpy==2.0.*" \
    "matplotlib==3.9.*" \
    "scipy==1.14.*" \
    "duckdb==1.1.*" \
    "scikit-learn==1.5.*"

# Matplotlib headless (tanpa display) + cache di lokasi writable.
ENV MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl \
    HOME=/home/sandbox \
    PYTHONDONTWRITEBYTECODE=1

# User non-root.
RUN useradd --create-home --uid 1000 sandbox
USER sandbox
WORKDIR /work

# Default: tunjukkan lib whitelist bisa di-import.
CMD ["python", "-c", "import pandas,numpy,matplotlib,scipy,duckdb,sklearn;print('ok')"]
