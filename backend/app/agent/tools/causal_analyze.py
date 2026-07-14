"""Tool: causal_analyze — jalankan pipeline kausal penuh (deterministik).

GATE D3: hanya jalan kalau mapping kolom SUDAH dikonfirmasi user
(_confirmed_roles di-inject loop dari AnalyzeRequest.causal_roles).
LLM tidak pernah menghitung angka (P1) — tool ini mengembalikan CausalResult
utuh; narasi final agent akan dicek number-grounding terhadap object ini.
"""
from __future__ import annotations

import json

from app.agent.tools.base import Tool, ToolRunResult
from app.causal import service
from app.causal.schemas import CausalOptions, ColumnRoles, DeclaredType, Method


class CausalAnalyzeTool(Tool):
    name = "causal_analyze"
    description = (
        "Jalankan analisis kausal penuh (efek + CI + p-value + power/MDE + cek asumsi + "
        "keputusan ship/hold) memakai mapping kolom yang SUDAH dikonfirmasi user. "
        "SEMUA angka dihitung engine deterministik — jangan hitung/ubah angka sendiri; "
        "kutip angka persis dari output tool ini."
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["ab_test", "observational", "timeseries"],
                "description": "override metode router (opsional; default ikut router)",
            },
            "cuped_pre_column": {
                "type": "string",
                "description": "kolom metrik pre-period untuk CUPED variance reduction (opsional)",
            },
            "declared_type": {
                "type": "string",
                "enum": ["auto", "randomized", "observational", "timeseries"],
            },
            "expected_ratio": {
                "type": "number",
                "description": "proporsi desain arm pertama utk cek SRM (default 0.5)",
            },
        },
        "required": [],
    }

    def run(self, *, dataset_id: str, _confirmed_roles: dict | None = None, **kwargs) -> ToolRunResult:
        if not _confirmed_roles:
            return ToolRunResult(
                error=(
                    "KONFIRMASI DIBUTUHKAN: mapping kolom belum dikonfirmasi user (D3). "
                    "Jangan panggil tool ini lagi — beri jawaban final berisi usulan mapping "
                    "dari causal_route dan minta user mengonfirmasi lewat panel Causal."
                )
            )
        try:
            roles = ColumnRoles(**{k: v for k, v in _confirmed_roles.items() if v is not None})
            options = CausalOptions(
                cuped=bool(kwargs.get("cuped_pre_column")),
                cuped_pre_column=kwargs.get("cuped_pre_column"),
                expected_ratio=kwargs.get("expected_ratio"),
            )
            declared = DeclaredType(kwargs.get("declared_type") or "auto")
            override = Method(kwargs["method"]) if kwargs.get("method") else None

            result = service.run_causal_analysis(
                dataset_id=dataset_id,
                roles=roles,
                options=options,
                declared_type=declared,
                override_method=override,
            )
            return ToolRunResult(
                output=json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
            )
        except NotImplementedError as e:
            return ToolRunResult(error=f"NotImplementedError: {e}")
        except Exception as e:  # noqa: BLE001 - observasi error dikembalikan ke loop
            return ToolRunResult(error=f"{type(e).__name__}: {e}")
