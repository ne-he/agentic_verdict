"""Bundle reproducible — rakit AnalysisResult lengkap + cek reproducibility.

Bundle = jawaban + kode + chart + verification + confidence + snapshot dataset.
Snapshot = hash file dataset saat run (provenance: tombol "Re-run this analysis" di UI nanti
bisa pastikan dataset belum berubah). `rerun_code` mengeksekusi ulang kode di sandbox untuk
membuktikan hasil sama (Blueprint Tier A #6).
"""

from __future__ import annotations

import hashlib

from app.agent.confidence import compute_confidence
from app.core.datasets import get_encoding, resolve_path
from app.core.schemas import AnalysisResult, ToolCall, VerificationResult
from app.sandbox.runner import SandboxResult, run_code

_LOADER = "import pandas as pd\ndf = pd.read_csv(DATASET_PATH, encoding='{enc}')\n"


def dataset_snapshot(dataset_id: str) -> str:
    """SHA-256 (12 char) dari file dataset — id snapshot stabil & deterministik."""
    path = resolve_path(dataset_id)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:12]}"


def build_analysis_bundle(
    *,
    run_id: str,
    dataset_id: str,
    answer_markdown: str,
    code: str,
    chart_paths: list[str] | None = None,
    verification: VerificationResult | None = None,
    tool_calls: list[ToolCall] | None = None,
    tokens: int = 0,
    duration_ms: int = 0,
    data_coverage: float = 1.0,
) -> AnalysisResult:
    """Rakit AnalysisResult lengkap + hitung confidence + lampirkan snapshot dataset."""
    tool_calls = tool_calls or []
    confidence = compute_confidence(
        verification=verification, tool_calls=tool_calls, data_coverage=data_coverage
    )
    return AnalysisResult(
        run_id=run_id,
        answer_markdown=answer_markdown,
        code=code,
        dataset_id=dataset_id,
        dataset_snapshot=dataset_snapshot(dataset_id),
        chart_paths=chart_paths or [],
        verification=verification,
        confidence=confidence,
        tool_calls=tool_calls,
        tokens=tokens,
        duration_ms=duration_ms,
    )


def rerun_code(code: str, dataset_id: str) -> SandboxResult:
    """Jalankan ulang kode bundle di sandbox (df ter-load) untuk verifikasi reproducibility."""
    enc = get_encoding(dataset_id)
    full = _LOADER.format(enc=enc) + code
    return run_code(full, str(resolve_path(dataset_id)))
