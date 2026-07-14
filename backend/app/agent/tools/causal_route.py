"""Tool: causal_route — usulkan mapping kolom + jalankan router metode kausal.

Output = RouterDecision (metode, confidence, reasons, assumptions) + usulan roles
+ flag needs_confirmation. Analisis TIDAK jalan dari tool ini — hanya routing.
Konfirmasi mapping oleh user adalah gate sebelum causal_analyze (D3).
"""
from __future__ import annotations

import json

from app.agent.tools.base import Tool, ToolRunResult
from app.causal import service
from app.causal.router.classifier import route
from app.causal.schemas import ColumnRoles, DeclaredType


class CausalRouteTool(Tool):
    name = "causal_route"
    description = (
        "Untuk pertanyaan KAUSAL: usulkan mapping kolom (treatment/outcome/covariates) dan "
        "tentukan metode kausal yang valid (router transparan: metode + alasan + asumsi). "
        "Panggil ini SEBELUM causal_analyze. Argumen roles boleh kosong — tool akan "
        "mengusulkan sendiri dari isi dataset."
    )
    parameters = {
        "type": "object",
        "properties": {
            "treatment": {"type": "string", "description": "kolom grup/perlakuan (2 arm), null jika tidak ada"},
            "outcome": {"type": "string", "description": "kolom metrik hasil yang dianalisis"},
            "covariates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "kolom kovariat pra-treatment untuk cek balance",
            },
            "declared_type": {
                "type": "string",
                "enum": ["auto", "randomized", "observational", "timeseries"],
                "description": "deklarasi user soal jenis data; default auto",
            },
        },
        "required": [],
    }

    def run(self, *, dataset_id: str, _confirmed_roles: dict | None = None, **kwargs) -> ToolRunResult:
        try:
            df = service.load_dataset(dataset_id)

            if _confirmed_roles:
                roles_dict = dict(_confirmed_roles)
                confirmed = True
            else:
                proposal = service.suggest_roles(df)
                # argumen LLM (kalau ada & valid) menimpa heuristik
                for key in ("treatment", "outcome"):
                    val = kwargs.get(key)
                    if val and val in df.columns:
                        proposal[key] = val
                covs = kwargs.get("covariates")
                if covs:
                    proposal["covariates"] = [c for c in covs if c in df.columns]
                roles_dict = proposal
                confirmed = False

            if not roles_dict.get("outcome"):
                return ToolRunResult(
                    error=(
                        "outcome tidak teridentifikasi — sebutkan kolom outcome di argumen "
                        f"(kolom tersedia: {list(df.columns)})"
                    )
                )

            roles = ColumnRoles(**{k: v for k, v in roles_dict.items() if v is not None})
            declared = DeclaredType(kwargs.get("declared_type") or "auto")
            decision = route(df, roles, declared)

            payload = {
                "roles": roles.model_dump(),
                "needs_confirmation": not confirmed,
                "router_decision": decision.model_dump(mode="json"),
            }
            if not confirmed:
                payload["instruction"] = (
                    "Mapping BELUM dikonfirmasi user. Sampaikan usulan mapping + metode + alasan "
                    "di jawaban final dan minta user konfirmasi (jangan panggil causal_analyze)."
                )
            return ToolRunResult(output=json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        except Exception as e:  # noqa: BLE001 - observasi error dikembalikan ke loop
            return ToolRunResult(error=f"{type(e).__name__}: {e}")
