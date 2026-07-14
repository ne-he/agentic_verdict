"""Intent classification (BLUEPRINT D2): DESCRIPTIVE vs CAUSAL.

Deterministik (regex keyword ID+EN) — bukan LLM: gratis, cepat, bisa di-test,
dan tidak menambah round-trip. Default saat ragu = DESCRIPTIVE (konservatif):
salah masuk jalur kausal itu mahal (minta mapping + asumsi); salah masuk
deskriptif cuma kurang dalam. Sinyal yang cocok DIKEMBALIKAN agar bisa
ditampilkan di investigation log (transparansi = DNA projek).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["descriptive", "causal"]

# Pola sinyal kausal. Cukup SATU match → CAUSAL.
_CAUSAL_PATTERNS: list[tuple[str, str]] = [
    (r"\bmenyebabkan\b|\bpenyebab\b|\bdisebabkan\b", "kata sebab-akibat eksplisit"),
    (r"\bgara-?gara\b|\bakibat\b", "kata sebab-akibat eksplisit"),
    (r"\befek\b|\bdampak\b|\bberdampak\b", "menanyakan efek/dampak"),
    (r"\bpengaruh\b|\bberpengaruh\b|\bmempengaruhi\b|\bmemengaruhi\b", "menanyakan pengaruh"),
    (r"\bkausal\b|\bcausal\b|\bcause[sd]?\b", "istilah kausal eksplisit"),
    (r"\bimpact\b|\beffect of\b", "menanyakan efek/dampak (EN)"),
    (r"\ba/?b[ -]?test\b|\beksperimen\b|\bexperiment\b|\buji coba\b", "konteks eksperimen/A-B test"),
    (r"\btreatment\b|\bperlakuan\b|\bkontrol vs\b|\bvs kontrol\b", "konteks treatment vs control"),
    (r"\blift\b|\buplift\b", "menanyakan lift eksperimen"),
    (
        # "apakah X menaikkan/menurunkan Y" — pertanyaan efek intervensi
        r"\bapakah\b.{0,60}\b(menaik|meningkat|menurun|mengurang|memperbaik|mendorong|menambah)",
        "pola 'apakah X menaikkan/menurunkan Y'",
    ),
    (r"\bdoes\b.{0,60}\b(increase|decrease|reduce|improve|boost|drive)\b", "pola 'does X increase Y' (EN)"),
]


class IntentDecision(BaseModel):
    intent: Intent
    signals: list[str] = Field(default_factory=list)  # transparansi utk investigation log
    note: str = ""


def classify_intent(question: str) -> IntentDecision:
    q = question.lower()
    signals = [label for pattern, label in _CAUSAL_PATTERNS if re.search(pattern, q)]
    # dedup sambil jaga urutan
    signals = list(dict.fromkeys(signals))
    if signals:
        return IntentDecision(
            intent="causal",
            signals=signals,
            note="Pertanyaan terdeteksi kausal — jalur causal engine (LLM tidak menghitung angka).",
        )
    return IntentDecision(
        intent="descriptive",
        signals=[],
        note=(
            "Tidak ada sinyal kausal — jalur deskriptif. Kalau maksudmu efek kausal "
            "X→Y, sebut kata 'efek/dampak/menyebabkan' dan tandai kolom treatment-nya."
        ),
    )
