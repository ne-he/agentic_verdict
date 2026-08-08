"""Entry point Hugging Face Space (SDK gradio, hardware ZeroGPU) untuk backend VERDICT ANALYST.

Kenapa gradio + ZeroGPU dan bukan Docker: pembuatan Docker Space (dan Gradio Space
di hardware `cpu-basic`) sekarang butuh langganan PRO, sementara akun gratis masih
boleh menghosting 2 ZeroGPU Space, dan ZeroGPU hanya kompatibel dengan SDK gradio.
`Dockerfile` sengaja dipertahankan supaya self-host tetap bisa tanpa menyusun ulang
konfigurasi dari nol.

DUA ATURAN ZeroGPU YANG MENENTUKAN BENTUK FILE INI (keduanya bikin Space mati waktu
dilanggar, pelajaran yang sudah dibayar di Space `ne-he/phisguard-api`):

1. Aplikasi WAJIB dinyalakan lewat mekanisme Gradio (`.launch()`), bukan
   `uvicorn.run()` manual. Uvicorn manual bikin ZeroGPU tidak pernah aktif.
2. WAJIB ada minimal satu fungsi ber-`@spaces.GPU` yang ter-register, kalau tidak
   runtime menolak start dengan "No @spaces.GPU function detected".

Jembatannya `gradio.Server`: subclass FastAPI resmi milik Gradio yang boleh menerima
route sendiri, tapi tetap dinyalakan lewat `.launch()`. Jadi rute API asli tetap ada
di root (`/health`, `/analyze`, ...) sehingga `NEXT_PUBLIC_API_URL` di Vercel tidak
perlu prefix apa pun, sekaligus ZeroGPU senang.

GPU-nya sendiri tidak dipakai untuk kerja beneran: beban proyek ini murni CPU
(pandas, scipy, duckdb) plus panggilan jaringan ke Gemini. Fungsi `gpu_probe()` di
bawah cuma tiket masuk syarat nomor 2, tidak pernah dipanggil frontend, jadi kuota
GPU harian (5 menit untuk akun gratis) praktis tidak tersentuh.

Nama file ini BUKAN `app.py` karena backend punya package bernama `app`
(`backend/app/`). Kalau entry point-nya `app.py` di root, `import app.main` akan
menabrak file entry point itu, bukan package-nya. Frontmatter `README.md` menunjuk
ke sini lewat `app_file: space_app.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Package `app` hanya ke-resolve kalau backend/ ada di sys.path. Di Dockerfile hal ini
# ditangani `WORKDIR /app/backend`; di Space, cwd-nya root repo.
sys.path.insert(0, str(ROOT / "backend"))

# Setara blok ENV di Dockerfile. Pakai setdefault supaya Variables / Secrets yang
# diisi di setelan Space tetap menang.
os.environ.setdefault("USE_DOCKER", "false")  # Space bukan Docker-in-Docker → sandbox subprocess
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")  # home di Space tidak selalu writable
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# Tidak ada UI Blocks di sini, jadi SSR (server Node.js) cuma memperumit lifecycle
# di ZeroGPU. Harus diset SEBELUM gradio di-import.
os.environ["GRADIO_SSR_MODE"] = "False"

# Dua folder ini ditulisi subprocess sandbox. Di Docker dibuat lewat `RUN mkdir`.
for _sub in ("sandbox/tmp", "sandbox/artifacts"):
    (ROOT / "backend" / _sub).mkdir(parents=True, exist_ok=True)

import spaces  # noqa: E402  (import setelah sys.path & env disiapkan)
from gradio import Server  # noqa: E402

from app.api.routes import router as api_router  # noqa: E402
from app.main import health  # noqa: E402

# `gradio.Server` tidak menjalankan lifespan FastAPI milik kita, jadi migrasi DB yang
# biasanya jalan di lifespan `app.main` dipanggil eager di sini. create_tables()
# idempotent. Kalau gagal, app tetap boot: /health tetap hijau dan endpoint DB yang
# akan mengeluh, sama seperti perilaku lifespan aslinya.
try:
    from app.db.session import create_tables

    create_tables()
    print("[startup] migrasi DB selesai — tabel siap.")
except Exception as exc:  # noqa: BLE001 - app tetap boot walau DB belum siap
    print(f"[startup] WARN: migrasi DB gagal: {exc}")

app = Server()

# Rute dipasang lewat router dan fungsi yang SAMA dengan yang dipakai `app.main`,
# bukan ditulis ulang di sini, supaya endpoint tidak perlu didaftarkan di dua tempat.
# `api_router` isinya seluruh endpoint agent (/analyze, /runs, /datasets, ...), dan
# `/health` menyusul karena di `app.main` ia dideklarasikan langsung di app, bukan di
# router. Paritasnya dijaga backend/tests/test_space_app.py.
#
# Sengaja TIDAK menyalin `app.main.app.routes` satu per satu: sejak FastAPI 0.141
# `include_router` tidak lagi meratakan rute ke `app.routes` melainkan membungkusnya
# jadi satu objek `_IncludedRouter`, jadi penyalinan berbasis isinya gampang patah.
app.include_router(api_router)
app.add_api_route("/health", health, methods=["GET"])

# CORS TIDAK ditambahkan di sini. `gradio.Server` sudah memasang CORS-nya sendiri yang
# memantulkan Origin di host non-localhost seperti *.hf.space. Menumpuk CORSMiddleware
# kedua di atasnya bikin header Access-Control-Allow-Origin dobel, dan browser menolak
# respons dengan header itu lebih dari satu. Konsekuensinya `ALLOWED_ORIGINS` tidak
# berpengaruh di Space; env itu tetap dipakai kalau self-host lewat Dockerfile.


@app.api(name="gpu_probe")
@spaces.GPU
def gpu_probe() -> dict[str, str]:
    """Ada semata-mata supaya runtime ZeroGPU mau start (lihat aturan 2 di docstring).

    Backend ini CPU-only dan frontend tidak pernah memanggil fungsi ini, jadi kuota
    GPU harian tidak terpakai. Isinya dibuat sekadar status supaya kalau ada yang
    iseng memanggilnya, jawabannya jujur, bukan error.
    """
    return {"status": "ok", "note": "backend CPU-only; GPU tidak dipakai"}


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
