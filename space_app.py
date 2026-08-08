"""Entry point Hugging Face Space (SDK gradio) untuk backend VERDICT ANALYST.

Kenapa SDK gradio dan bukan docker: sejak sekitar 8 Juli 2026 pembuatan Docker Space
butuh langganan PRO, sementara akun gratis masih boleh menghosting 2 ZeroGPU Space dan
ZeroGPU hanya kompatibel dengan SDK gradio. GPU-nya sendiri TIDAK dipakai sama sekali:
beban kerja proyek ini murni CPU (pandas, scipy, duckdb) plus panggilan jaringan ke
Gemini, jadi tidak ada satu pun fungsi yang perlu `@spaces.GPU`. `Dockerfile` sengaja
dipertahankan supaya self-host atau balik ke Docker Space tetap bisa tanpa menyusun
ulang konfigurasi dari nol.

Nama file ini BUKAN `app.py` karena backend punya package bernama `app`
(`backend/app/`). Kalau entry point-nya `app.py` di root, `import app.main` akan
menabrak file entry point itu, bukan package-nya. Frontmatter `README.md` menunjuk ke
sini lewat `app_file: space_app.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Package `app` hanya ke-resolve kalau backend/ ada di sys.path. Di Dockerfile hal ini
# ditangani `WORKDIR /app/backend`; di Space, cwd-nya root repo.
sys.path.insert(0, str(ROOT / "backend"))

# Setara blok ENV di Dockerfile. Pakai setdefault supaya Variables / Secrets yang diisi
# di setelan Space tetap menang.
os.environ.setdefault("USE_DOCKER", "false")  # Space bukan Docker-in-Docker → sandbox subprocess
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl")  # home di Space tidak selalu writable
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# Dua folder ini ditulisi subprocess sandbox. Di Docker dibuat lewat `RUN mkdir`.
for _sub in ("sandbox/tmp", "sandbox/artifacts"):
    (ROOT / "backend" / _sub).mkdir(parents=True, exist_ok=True)

import gradio as gr  # noqa: E402  (import setelah sys.path & env disiapkan)
import uvicorn  # noqa: E402

from app.main import app as api  # noqa: E402

with gr.Blocks(title="VERDICT ANALYST — API") as status_page:
    gr.Markdown(
        "# VERDICT ANALYST\n\n"
        "Space ini **backend saja** (FastAPI + SSE). UI-nya di frontend Vercel.\n\n"
        "- Health check: [`/health`](/health)\n"
        "- Dokumentasi API: [`/docs`](/docs)\n"
    )

# Gradio di-mount KE DALAM FastAPI, bukan sebaliknya. Dengan begitu rute API tetap di
# root (`/health`, `/analyze`, ...) sehingga `NEXT_PUBLIC_API_URL` di Vercel tidak perlu
# prefix apa pun, dan halaman status gradio cuma nebeng di `/space`.
app = gr.mount_gradio_app(api, status_page, path="/space")

# Tanpa penjaga `if __name__ == "__main__"`: Space menjalankan file ini sebagai script,
# tapi kalau suatu saat runner-nya meng-import modul ini, server tetap harus naik.
uvicorn.run(
    app,
    host="0.0.0.0",
    port=int(os.getenv("PORT") or os.getenv("GRADIO_SERVER_PORT") or 7860),
)
