"""Menjaga requirements.txt di root tetap sama dengan backend/requirements.txt.

Kenapa dua file ini kembar, bukan yang satu meng-`-r` yang lain: pada tahap pip
install, Hugging Face Space TIDAK menyalin isi repo. Yang di-mount cuma satu file
`requirements.txt` di root, sendirian, ke `/tmp/requirements.txt`. Jadi
`-r backend/requirements.txt` di-resolve jadi `/tmp/backend/requirements.txt`
yang tidak ada, dan build mati dengan "Could not open requirements file".

Duplikasi seperti itu biasanya melenceng diam-diam: seseorang menaikkan versi di
satu file, lupa yang satunya, lalu Space jalan dengan dependensi berbeda dari yang
diuji CI. Test ini mengubah kegagalan senyap itu jadi test merah.

Kalau menambah atau menaikkan dependensi: ubah `backend/requirements.txt`, lalu
samakan `requirements.txt` di root.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_REQS = REPO_ROOT / "backend" / "requirements.txt"
ROOT_REQS = REPO_ROOT / "requirements.txt"


def _pins(path: Path) -> list[str]:
    """Baris dependensi saja: komentar dan baris kosong dibuang."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [s for line in lines if (s := line.strip()) and not s.startswith("#")]


def test_kedua_requirements_ada():
    assert BACKEND_REQS.is_file(), f"tidak ketemu: {BACKEND_REQS}"
    assert ROOT_REQS.is_file(), f"tidak ketemu: {ROOT_REQS}"


def test_daftar_dependensi_identik():
    backend, root = _pins(BACKEND_REQS), _pins(ROOT_REQS)
    assert root == backend, (
        "requirements.txt di root melenceng dari backend/requirements.txt.\n"
        f"  cuma di root    : {sorted(set(root) - set(backend))}\n"
        f"  cuma di backend : {sorted(set(backend) - set(root))}\n"
        "Samakan keduanya, lihat docstring file ini soal kenapa harus kembar."
    )


def test_root_tidak_memakai_include_relatif():
    """`-r` ke path repo tidak akan resolve di build Space, lihat docstring."""
    offenders = [p for p in _pins(ROOT_REQS) if p.startswith(("-r", "--requirement"))]
    assert not offenders, (
        f"requirements.txt di root memakai include relatif: {offenders}. "
        "Build Space cuma me-mount file ini sendirian, jadi path repo tidak ada di sana."
    )
