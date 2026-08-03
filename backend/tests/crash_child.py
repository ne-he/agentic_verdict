"""Anak proses untuk test crash-recovery: jalankan run agent lalu MATI di tengah.

Dipanggil oleh tests/test_durable_state.py sebagai subprocess:

    python tests/crash_child.py <db_url> <run_id>

Setelah dua tool call tersimpan, proses membunuh dirinya dengan `os._exit(1)`.
`os._exit` sengaja dipilih, bukan `sys.exit`: tidak ada unwind stack, tidak ada
`finally`, tidak ada flush atexit. Jadi satu-satunya alasan state bisa selamat
adalah karena checkpointer beneran commit ke SQLite tiap langkah, bukan karena
ada cleanup yang baik hati di akhir.

File ini BUKAN test (namanya tidak diawali `test_`), jadi pytest tidak mengumpulkannya.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.checkpoint import SqliteCheckpointer  # noqa: E402
from app.agent.react_loop import ReactLoop  # noqa: E402
from app.db.session import configure_database, create_tables  # noqa: E402

# Skrip aksi yang sama persis dengan yang dipakai test di sisi parent.
# Dua tool call pertama dijalankan di sini; sisanya urusan proses yang me-resume.
ACTIONS = [
    {"thought": "lihat skema", "action": "inspect_schema", "args": {}},
    {"thought": "lihat skema lagi", "action": "inspect_schema", "args": {}},
]

CRASH_AFTER_STEPS = 2


class CrashingLLM:
    """Balas plan, lalu aksi berurutan. Setelah N aksi habis → bunuh proses."""

    def __init__(self) -> None:
        self._actions = list(ACTIONS)
        self._served = 0

    def __call__(self, prompt: str) -> str:
        if "perencana" in prompt:
            return json.dumps(
                [
                    {"description": "inspect schema", "tool": "inspect_schema"},
                    {"description": "hitung total", "tool": "write_and_execute"},
                ]
            )
        if self._actions:
            self._served += 1
            return json.dumps(self._actions.pop(0))
        # Aksi habis = dua langkah sudah tersimpan. Simulasikan crash keras di sini:
        # persis di tengah run, sebelum model sempat memberi jawaban final.
        sys.stdout.write(f"CRASHING_AFTER={self._served}\n")
        sys.stdout.flush()
        os._exit(1)


def main() -> int:
    db_url, run_id = sys.argv[1], sys.argv[2]
    configure_database(db_url)
    create_tables()

    loop = ReactLoop(generate=CrashingLLM(), checkpointer=SqliteCheckpointer())
    loop.run("Berapa total penjualan?", "superstore", run_id=run_id)
    # Tidak boleh sampai sini. Kalau iya, berarti crash-nya tidak terjadi.
    sys.stdout.write("UNEXPECTED_COMPLETION\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
