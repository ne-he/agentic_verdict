"""Tool: inspect_schema — kolom, tipe, jumlah baris, sample 5 baris (via DuckDB)."""

from __future__ import annotations

import json

from app.agent.tools.base import Tool, ToolRunResult
from app.core.datasets import get_encoding, resolve_path


class InspectSchemaTool(Tool):
    name = "inspect_schema"
    description = (
        "Periksa struktur dataset: nama kolom, tipe data, jumlah baris, dan 5 baris contoh. "
        "Selalu panggil ini PERTAMA sebelum menulis kode analisis."
    )
    parameters = {"type": "object", "properties": {}, "required": []}

    def run(self, *, dataset_id: str, **kwargs) -> ToolRunResult:
        # pandas baca file (encoding-aware; DuckDB 1.1 read_csv belum punya param encoding),
        # DuckDB infer tipe kolom dari relasi yang di-register.
        import duckdb
        import pandas as pd

        try:
            path = resolve_path(dataset_id)
            enc = get_encoding(dataset_id)
            frame = pd.read_csv(path, encoding=enc)
            con = duckdb.connect()
            try:
                con.register("t", frame)
                desc = con.execute("DESCRIBE SELECT * FROM t").fetchall()
            finally:
                con.close()

            sample_df = frame.head(5)
            payload = {
                "dataset_id": dataset_id,
                "n_rows": int(len(frame)),
                "n_columns": len(desc),
                "columns": [{"name": row[0], "type": row[1]} for row in desc],
                "sample_rows": json.loads(
                    sample_df.to_json(orient="records", date_format="iso")
                ),
            }
            return ToolRunResult(output=json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception as e:  # noqa: BLE001 - observasi error dikembalikan ke loop
            return ToolRunResult(error=f"{type(e).__name__}: {e}")
