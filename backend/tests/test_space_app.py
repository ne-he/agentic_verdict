"""Menjaga entry point Hugging Face Space (`space_app.py`) tetap sepadan dengan API asli.

`space_app.py` tidak memakai objek FastAPI dari `app.main` apa adanya. Ia membangun
`gradio.Server` (subclass FastAPI milik Gradio) lalu memasang router yang sama ke
sana, karena ZeroGPU menuntut app dinyalakan lewat `.launch()` Gradio dan menuntut
ada minimal satu fungsi ber-`@spaces.GPU`. Perbedaan bentuk itu bikin dua hal bisa
melenceng diam-diam, dan dua-duanya baru ketahuan setelah deploy:

1. Endpoint baru ditambahkan di `app.main` tapi tidak ikut terpasang di Space.
2. Fungsi `@spaces.GPU` terhapus, lalu Space menolak start dengan
   "No @spaces.GPU function detected".

Test ini di-skip kalau `gradio` belum terpasang, karena itu dependensi Space, bukan
dependensi backend (`backend/requirements.txt` tidak memuatnya, HF memasangnya
sendiri sesuai `sdk_version` di frontmatter README.md).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPACE_APP = REPO_ROOT / "space_app.py"

gradio = pytest.importorskip("gradio", reason="gradio hanya terpasang di Space")
pytest.importorskip("spaces", reason="spaces hanya terpasang di Space")


@pytest.fixture(scope="module")
def space_module():
    """Import space_app.py tanpa menjalankannya sebagai script.

    Blok `.launch()` di sana dijaga `if __name__ == "__main__"`, dan di sini nama
    modulnya bukan itu, jadi server tidak ikut naik saat test.
    """
    spec = importlib.util.spec_from_file_location("space_app_undertest", SPACE_APP)
    module = importlib.util.module_from_spec(spec)
    sys.modules["space_app_undertest"] = module
    spec.loader.exec_module(module)
    return module


def test_semua_endpoint_api_ikut_terpasang(space_module):
    from app.main import app as api

    seharusnya = set(api.openapi()["paths"])
    terpasang = set(space_module.app.openapi()["paths"])
    kurang = sorted(seharusnya - terpasang)
    assert not kurang, (
        f"endpoint ini ada di app.main tapi tidak dilayani Space: {kurang}. "
        "Daftarkan di space_app.py, kalau tidak endpoint-nya hilang setelah deploy."
    )


def test_health_masih_dilayani(space_module):
    """/health dideklarasikan langsung di app.main, bukan di api_router.

    Artinya ia TIDAK ikut terbawa `include_router` dan harus dipasang terpisah.
    Endpoint ini juga yang dipakai untuk verifikasi manual setelah deploy.
    """
    assert "/health" in space_module.app.openapi()["paths"]


def test_ada_fungsi_ber_dekorator_gpu(space_module):
    """Tanpa ini ZeroGPU menolak start, walau backend-nya CPU-only."""
    probe = getattr(space_module, "gpu_probe", None)
    assert probe is not None, "gpu_probe() hilang dari space_app.py"
    assert callable(probe)


def test_tidak_menumpuk_cors_middleware(space_module):
    """CORS sudah disediakan gradio saat `.launch()`; yang kedua bikin header dobel.

    Browser menolak respons yang punya lebih dari satu Access-Control-Allow-Origin,
    jadi menambah CORSMiddleware sendiri di space_app.py justru mematikan frontend.
    """
    from fastapi.middleware.cors import CORSMiddleware

    terpasang = [m.cls for m in space_module.app.user_middleware]
    assert CORSMiddleware not in terpasang, (
        "space_app.py memasang CORSMiddleware sendiri. Gradio sudah memasang CORS-nya "
        "saat .launch(), jadi ini bikin Access-Control-Allow-Origin dobel dan ditolak browser."
    )
