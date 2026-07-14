"""Tool: causal_refute — robustness/refutation test. KONTRAK M1, implementasi M3.

Kontraknya didefinisikan sekarang (BLUEPRINT D6) supaya schema API & frontend stabil.
Placebo treatment, random common cause, dan sensitivity analysis butuh jalur
observational (DoWhy) yang baru dibangun di M3 (Docker only).
"""
from __future__ import annotations

from app.agent.tools.base import Tool, ToolRunResult


class CausalRefuteTool(Tool):
    name = "causal_refute"
    description = (
        "Uji ketahanan hasil kausal (placebo treatment, random common cause, sensitivity). "
        "BELUM tersedia di versi ini (roadmap M3) — jangan panggil kecuali user memaksa; "
        "kalau terpanggil, sampaikan apa adanya bahwa refutation menyusul di M3."
    )
    parameters = {
        "type": "object",
        "properties": {
            "checks": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["placebo", "random_common_cause", "subset", "e_value"],
                },
                "description": "daftar refutation check yang diminta",
            },
        },
        "required": [],
    }

    def run(self, *, dataset_id: str, _confirmed_roles: dict | None = None, **kwargs) -> ToolRunResult:
        return ToolRunResult(
            error=(
                "NotImplementedError: refutation suite (placebo / random common cause / "
                "sensitivity) dibangun di M3 bersama jalur observational (DoWhy, Docker). "
                "Sampaikan ini apa adanya ke user — jangan mengarang hasil refutation."
            )
        )
