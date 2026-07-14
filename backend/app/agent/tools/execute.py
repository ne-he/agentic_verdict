"""Tools eksekusi kode di sandbox: write_and_execute (analisis) & make_chart (PNG).

Keduanya menyuntik loader pandas sehingga kode LLM langsung punya `df` ter-load
dengan encoding dataset yang benar. Kode TIDAK pernah jalan di proses backend (Aturan #6).
"""

from __future__ import annotations

from app.agent.tools.base import Tool, ToolRunResult
from app.core.datasets import get_encoding, resolve_path
from app.sandbox.runner import run_code

# Disuntik di depan kode LLM: sediakan `df` siap pakai.
_LOADER = (
    "import pandas as pd\n"
    "df = pd.read_csv(DATASET_PATH, encoding='{enc}')\n"
)

# Disuntik di belakang kode chart: jaring pengaman kalau LLM lupa savefig.
_CHART_SAFETY = (
    "\nimport os as _os3, matplotlib.pyplot as _plt\n"
    "if not any(_f.endswith('.png') for _f in _os3.listdir('.')):\n"
    "    _plt.savefig('chart.png')\n"
)


def _build(dataset_id: str, code: str, *, chart: bool = False) -> tuple[str, str]:
    enc = get_encoding(dataset_id)
    path = str(resolve_path(dataset_id))
    full = _LOADER.format(enc=enc) + code
    if chart:
        full += _CHART_SAFETY
    return full, path


def _format_output(res) -> ToolRunResult:
    if res.timed_out:
        return ToolRunResult(output=res.stdout, error=res.stderr.strip() or "Timeout")
    if not res.ok:
        return ToolRunResult(output=res.stdout, error=res.stderr.strip() or f"exit {res.exit_code}")
    return ToolRunResult(output=res.stdout.strip(), chart_paths=res.chart_paths)


class WriteAndExecuteTool(Tool):
    name = "write_and_execute"
    description = (
        "Tulis kode Python (pandas/numpy/scipy/duckdb/sklearn) untuk menganalisis data, "
        "lalu jalankan di sandbox terisolasi. DataFrame sudah tersedia sebagai variabel `df`. "
        "WAJIB print() hasil yang ingin dilihat. Tidak ada akses internet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Kode Python. `df` sudah ter-load. Gunakan print() untuk output.",
            }
        },
        "required": ["code"],
    }

    def run(self, *, dataset_id: str, code: str = "", **kwargs) -> ToolRunResult:
        full, path = _build(dataset_id, code)
        return _format_output(run_code(full, path))


class MakeChartTool(Tool):
    name = "make_chart"
    description = (
        "Tulis kode matplotlib untuk membuat satu chart dan simpan sebagai PNG "
        "(mis. plt.savefig('chart.png')). `df` sudah tersedia. Mengembalikan path PNG."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Kode matplotlib. `df` sudah ter-load. Simpan via plt.savefig('chart.png').",
            }
        },
        "required": ["code"],
    }

    def run(self, *, dataset_id: str, code: str = "", **kwargs) -> ToolRunResult:
        full, path = _build(dataset_id, code, chart=True)
        res = _format_output(run_code(full, path))
        if res.ok and not res.chart_paths:
            return ToolRunResult(output=res.output, error="Tidak ada PNG yang dihasilkan.")
        if res.ok:
            res.output = f"Chart tersimpan: {res.chart_paths}\n{res.output}".strip()
        return res
