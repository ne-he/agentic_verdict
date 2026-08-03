"""Alasan terminasi run agent (aturan produksi #3).

Kenapa ini ada file sendiri: alasan berhenti dipakai di tiga tempat (loop, DB,
API/UI) dan gampang jadi string bebas yang tidak konsisten. Satu vocabulary,
satu penjelasan bahasa manusia, dipakai semua lapisan.

Ini metadata debugging yang paling sering dilewat orang: tanpa ini, run yang
kena batas langkah kelihatan sama persis dengan run yang beneran selesai,
padahal jawabannya beda kualitas.
"""

from __future__ import annotations

from typing import Literal

TerminationReason = Literal[
    "completed",      # model mengembalikan jawaban final
    "step_budget",    # kena batas jumlah iterasi tool
    "token_budget",   # kena batas perkiraan token
    "timeout",        # kena batas waktu wall-clock per run
    "tool_error",     # dihentikan karena tool gagal beruntun
    "cancelled",      # dibatalkan user / client memutus koneksi
    "crashed",        # proses mati di tengah; ketahuan dari state yang masih "running"
]

ALL_REASONS: tuple[str, ...] = (
    "completed",
    "step_budget",
    "token_budget",
    "timeout",
    "tool_error",
    "cancelled",
    "crashed",
)

# Penjelasan singkat bahasa manusia, dipakai UI dan laporan.
REASON_LABEL: dict[str, str] = {
    "completed": "Selesai normal",
    "step_budget": "Berhenti: batas langkah tercapai",
    "token_budget": "Berhenti: budget token habis",
    "timeout": "Berhenti: melewati batas waktu",
    "tool_error": "Berhenti: tool gagal beruntun",
    "cancelled": "Dibatalkan",
    "crashed": "Proses mati di tengah run",
}

# Alasan yang menandakan jawaban kemungkinan belum lengkap.
INCOMPLETE_REASONS: frozenset[str] = frozenset(
    {"step_budget", "token_budget", "timeout", "tool_error", "cancelled", "crashed"}
)


def label(reason: str) -> str:
    """Terjemahkan kode alasan jadi kalimat pendek. Kode tak dikenal dikembalikan apa adanya."""
    return REASON_LABEL.get(reason, reason)


def is_incomplete(reason: str) -> bool:
    """True kalau alasan berhenti menandakan run tidak tuntas."""
    return reason in INCOMPLETE_REASONS
