"""Self-Verify — verifikasi nyata, BUKAN "minta LLM cek ulang" (Blueprint Tier A #4).

Tiga mekanisme:
  1. Numerical cross-check (WAJIB): angka kunci dari agent (method A, hasil sandbox pandas)
     dihitung ULANG independen via DuckDB SQL (method B), lalu dibandingkan dgn toleransi.
  2. Sanity check: aturan domain (mis. total revenue >= 0).
  3. Row-level contradiction (opsional, LLM): cari maks 3 baris yang berpotensi bertentangan
     dengan kesimpulan. `generate` di-inject agar bisa di-mock saat test.

DuckDB SQL = query terparametrisasi pada dataframe (bukan exec Python) -> aman, tak melanggar
Aturan #6 (kode Python LLM tetap hanya jalan di sandbox).
"""

from __future__ import annotations

import json
import re
from typing import Callable

from app.core.datasets import get_encoding, resolve_path
from app.core.schemas import VerificationResult

GenerateFn = Callable[[str], str]

# Toleransi relatif default untuk menganggap dua angka "setuju".
DEFAULT_TOLERANCE = 0.01
_EPS = 1e-9


def compare_numbers(a: float, b: float, tolerance: float = DEFAULT_TOLERANCE) -> tuple[float, bool]:
    """Bandingkan dua angka. Return (agreement[0..1], within_tolerance)."""
    a, b = float(a), float(b)
    denom = max(abs(a), abs(b), _EPS)
    rel_diff = abs(a - b) / denom
    within = rel_diff <= tolerance
    agreement = 1.0 if within else max(0.0, 1.0 - rel_diff)
    return round(agreement, 4), within


def _duckdb_scalar(dataset_id: str, sql: str) -> float:
    """Jalankan SQL agregat pada dataset (tabel `t`) via DuckDB, ambil 1 nilai skalar."""
    import duckdb
    import pandas as pd

    frame = pd.read_csv(resolve_path(dataset_id), encoding=get_encoding(dataset_id))
    con = duckdb.connect()
    try:
        con.register("t", frame)
        row = con.execute(sql).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        raise ValueError(f"SQL verifikasi tidak menghasilkan nilai: {sql!r}")
    return float(row[0])


def run_sanity_checks(rules: list[tuple[str, bool]] | None) -> list[str]:
    """rules = [(deskripsi, ok)]. Return daftar deskripsi yang GAGAL (ok=False)."""
    if not rules:
        return []
    return [desc for desc, ok in rules if not ok]


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1).strip() if m else text


def row_level_contradiction(
    conclusion: str, sample_rows: list[dict], generate: GenerateFn
) -> list[str]:
    """Strategi 2: LLM cari maks 3 baris yang berpotensi kontradiktif dgn kesimpulan."""
    prompt = (
        "Kesimpulan agen: " + conclusion + "\n\n"
        "Berikut beberapa baris data (JSON). Temukan MAKS 3 baris yang tampak BERTENTANGAN "
        "dengan kesimpulan. Balas HANYA JSON array berisi string alasan singkat "
        "(array kosong [] jika tidak ada).\n\n"
        + json.dumps(sample_rows, ensure_ascii=False)
    )
    try:
        data = json.loads(_strip_fences(generate(prompt)))
    except Exception:  # noqa: BLE001 - LLM output tak valid -> tak ada kontradiksi terdeteksi
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data[:3]]


class SelfVerifier:
    def __init__(self, tolerance: float = DEFAULT_TOLERANCE) -> None:
        self._tolerance = tolerance

    def verify_numeric(
        self,
        dataset_id: str,
        key_value: float,
        verification_sql: str,
        *,
        sanity_rules: list[tuple[str, bool]] | None = None,
        tolerance: float | None = None,
    ) -> VerificationResult:
        """Cross-check angka kunci agent vs recompute DuckDB + sanity check domain."""
        tol = tolerance if tolerance is not None else self._tolerance
        contradictions: list[str] = []

        try:
            value_b = _duckdb_scalar(dataset_id, verification_sql)
            agreement, within = compare_numbers(key_value, value_b, tol)
            method_b = f"duckdb_sql: {value_b:.6g}"
            if not within:
                contradictions.append(
                    f"Cross-check tidak cocok: agent={key_value:.6g} vs duckdb={value_b:.6g} "
                    f"(toleransi {tol:.1%})."
                )
        except Exception as e:  # noqa: BLE001 - kegagalan recompute = verifikasi tak meyakinkan
            agreement, within = 0.0, False
            method_b = f"duckdb_sql ERROR: {e}"
            contradictions.append(f"Method B gagal dihitung: {e}")

        contradictions.extend(run_sanity_checks(sanity_rules))
        passed = within and not run_sanity_checks(sanity_rules)
        return VerificationResult(
            method_a=f"agent_pandas: {float(key_value):.6g}",
            method_b=method_b,
            agreement=agreement,
            contradictions=contradictions,
            passed=passed,
        )
