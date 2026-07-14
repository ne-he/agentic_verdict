"""Computed Confidence (Blueprint §4.5) — DIHITUNG, bukan ditebak LLM.

final = 0.40·answer_consistency + 0.30·verification_agreement
      + 0.20·tool_execution_success + 0.10·data_coverage
label = HIGH (>=0.8) / MEDIUM (0.5–0.8) / LOW (<0.5)

Tiap komponen punya makna eksplisit (bukan magic number):
- answer_consistency: jawaban internal konsisten — diturunkan dari kontradiksi yang ditemukan
  self-verify (atau di-override kalau ada pengukuran konsistensi multi-sample).
- verification_agreement: kesepakatan cross-check method A vs B (VerificationResult.agreement).
- tool_execution_success: proporsi tool call yang sukses (tanpa error).
- data_coverage: fraksi data relevan yang benar-benar dipakai (default 1.0 = full dataset).
"""

from __future__ import annotations

from app.core.schemas import ConfidenceBreakdown, ToolCall, VerificationResult

# Bobot (Blueprint §4.5). Jumlah = 1.0.
W_CONSISTENCY = 0.40
W_VERIFICATION = 0.30
W_TOOL = 0.20
W_COVERAGE = 0.10

# Tiap kontradiksi mengurangi konsistensi sebesar ini.
_CONTRADICTION_PENALTY = 0.5
# Jika tak ada verifikasi sama sekali, pakai nilai netral (bukan 0, bukan 1).
_NEUTRAL = 0.5


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def tool_execution_success(tool_calls: list[ToolCall]) -> float:
    """Proporsi tool call tanpa error. Tak ada tool -> 1.0 (tak ada kegagalan)."""
    if not tool_calls:
        return 1.0
    ok = sum(1 for tc in tool_calls if tc.error is None)
    return ok / len(tool_calls)


def answer_consistency_from_verification(verification: VerificationResult | None) -> float:
    """Turunkan konsistensi dari kontradiksi self-verify. Tanpa verifikasi -> netral."""
    if verification is None:
        return _NEUTRAL
    base = 1.0 - _CONTRADICTION_PENALTY * len(verification.contradictions)
    return _clamp(base)


def label_for(final: float) -> str:
    if final >= 0.8:
        return "HIGH"
    if final >= 0.5:
        return "MEDIUM"
    return "LOW"


def compute_confidence(
    *,
    verification: VerificationResult | None,
    tool_calls: list[ToolCall] | None = None,
    answer_consistency: float | None = None,
    data_coverage: float = 1.0,
) -> ConfidenceBreakdown:
    """Hitung confidence terstruktur + label, lengkap dgn breakdown tiap komponen."""
    tool_calls = tool_calls or []

    consistency = (
        _clamp(answer_consistency)
        if answer_consistency is not None
        else answer_consistency_from_verification(verification)
    )
    veri_agreement = verification.agreement if verification is not None else _NEUTRAL
    tool_success = tool_execution_success(tool_calls)
    coverage = _clamp(data_coverage)

    final = _clamp(
        W_CONSISTENCY * consistency
        + W_VERIFICATION * veri_agreement
        + W_TOOL * tool_success
        + W_COVERAGE * coverage
    )
    return ConfidenceBreakdown(
        answer_consistency=round(consistency, 4),
        verification_agreement=round(veri_agreement, 4),
        tool_execution_success=round(tool_success, 4),
        data_coverage=round(coverage, 4),
        final=round(final, 4),
        label=label_for(final),
    )
