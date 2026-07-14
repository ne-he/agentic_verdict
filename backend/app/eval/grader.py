"""Grader: nilai AnalysisResult vs GoldQuestion → Scorecard (T3.2).

Correctness graded:
  1. Numerik: ekstrak angka dari answer_markdown, bandingkan ke expected_value
     dengan allowed_tolerance → 1.0 tepat, 0.5 approach benar angka salah, 0.0 salah.
  2. LLM judge (fallback): Gemini skala 1–5 dinormalisasi ke 0.0–1.0.
     Hanya dipanggil jika numeric check gagal ekstrak angka DAN generate disediakan.
"""

from __future__ import annotations

import re
from typing import Callable

from app.core.schemas import AnalysisResult, GoldQuestion, Scorecard

GenerateFn = Callable[[str], str]


def _extract_first_number(text: str) -> float | None:
    """Ekstrak angka pertama (termasuk negatif, desimal, koma ribuan) dari teks."""
    cleaned = text.replace("$", "").replace("%", "")
    # Coba format koma ribuan dulu (e.g. 2,297,200.86)
    m = re.search(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            pass
    # Fallback: angka biasa dengan desimal opsional
    m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _numeric_correctness(
    answer_markdown: str, expected: float, tolerance: float
) -> float | None:
    """Hitung correctness via toleransi numerik.

    Return None kalau tidak bisa ekstrak angka dari answer_markdown.
    """
    extracted = _extract_first_number(answer_markdown)
    if extracted is None:
        return None
    if expected == 0:
        return 1.0 if abs(extracted) <= max(tolerance, 1e-9) else 0.0
    rel_diff = abs(extracted - expected) / abs(expected)
    if rel_diff <= tolerance:
        return 1.0
    if rel_diff <= tolerance * 5:  # approach benar, angka agak meleset
        return 0.5
    return 0.0


def _llm_correctness(
    question: str,
    gold_answer: str,
    agent_answer: str,
    generate: GenerateFn,
) -> float:
    """LLM judge: Gemini nilai 1–5 → normalisasi ke 0.0–1.0.

    Prompt meminta integer 1–5:
      1 = salah total, 3 = approach benar angka salah, 5 = tepat sesuai gold.
    """
    prompt = (
        "Nilai jawaban agent untuk pertanyaan analitik berikut.\n\n"
        f"Pertanyaan: {question}\n"
        f"Jawaban gold (benar): {gold_answer}\n"
        f"Jawaban agent: {agent_answer}\n\n"
        "Beri nilai bulat 1–5 (1=salah total, 3=approach benar angka meleset, 5=tepat). "
        "Balas HANYA angka integer antara 1 dan 5, tanpa penjelasan."
    )
    raw = generate(prompt).strip()
    try:
        score = int(re.search(r"[1-5]", raw).group())
        return (score - 1) / 4  # 1→0.0, 3→0.5, 5→1.0
    except Exception:
        return 0.5  # neutral fallback bila LLM tidak kooperatif


def _hallucination_flag(result: AnalysisResult, correctness: float) -> bool:
    """True kalau agent 'yakin tapi salah': confidence HIGH/MEDIUM + correctness rendah.

    Ini yang disebut Blueprint sebagai "confident but wrong" — klaim sesuatu
    yang tidak ada di data atau self-verify gagal tapi agent tetap percaya diri.
    """
    if correctness >= 0.5:
        return False
    if result.confidence is None:
        return False
    return result.confidence.label in ("HIGH", "MEDIUM")


def _verification_accuracy(result: AnalysisResult, correctness: float) -> float:
    """Seberapa akurat verification menangkap atau mengkonfirmasi kebenaran.

    Skema:
      - verification passed + jawaban benar  → 1.0 (true positive)
      - verification failed + jawaban salah  → 1.0 (true negative: error terdeteksi)
      - verification passed + jawaban salah  → 0.0 (false pass: miss error)
      - verification failed + jawaban benar  → 0.5 (false alarm: over-cautious)
      - tidak ada verification               → 0.0
    """
    if result.verification is None:
        return 0.0
    passed = result.verification.passed
    correct = correctness >= 0.5
    if passed and correct:
        return 1.0
    if not passed and not correct:
        return 1.0
    if passed and not correct:
        return 0.0
    return 0.5  # not passed tapi correct → false alarm


def grade(
    result: AnalysisResult,
    gold: GoldQuestion,
    generate: GenerateFn | None = None,
) -> Scorecard:
    """Grade satu AnalysisResult terhadap GoldQuestion.

    Urutan: numeric tolerance check → LLM judge (jika generate ada) → neutral 0.5.
    """
    correctness = _numeric_correctness(
        result.answer_markdown, gold.expected_value, gold.allowed_tolerance
    )
    if correctness is None and generate is not None:
        correctness = _llm_correctness(
            gold.question, gold.gold_answer, result.answer_markdown, generate
        )
    if correctness is None:
        correctness = 0.5  # tidak bisa dinilai

    return Scorecard(
        run_id=result.run_id,
        question_id=gold.id,
        correctness=correctness,
        cost_usd=result.cost_usd,
        tool_calls=len(result.tool_calls),
        time_to_insight=result.duration_ms / 1000.0,
        hallucination_flag=_hallucination_flag(result, correctness),
        verification_accuracy=_verification_accuracy(result, correctness),
    )
