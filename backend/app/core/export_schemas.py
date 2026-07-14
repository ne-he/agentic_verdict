"""Export JSON schema dari model Pydantic ke frontend/lib/schemas.json.

Jalankan:  python -m app.core.export_schemas   (dari backend/)
FE pakai file ini untuk men-generate / memvalidasi `frontend/lib/types.ts`.
"""

from __future__ import annotations

import json

from app.core.config import PROJECT_ROOT
from app.core.schemas import EXPORTED_MODELS

OUTPUT_PATH = PROJECT_ROOT / "frontend" / "lib" / "schemas.json"


def build_schemas() -> dict[str, dict]:
    """Kumpulkan JSON schema tiap model exported, di-key nama class."""
    return {model.__name__: model.model_json_schema() for model in EXPORTED_MODELS}


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schemas = build_schemas()
    OUTPUT_PATH.write_text(json.dumps(schemas, indent=2), encoding="utf-8")
    print(f"Wrote {len(schemas)} schemas -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
