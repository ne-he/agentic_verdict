"""Registry tool default untuk VERDICT ANALYST.

Aturan produksi #1, TOOL MINIMUM: deskripsi tiap tool ikut dikirim di SETIAP
request ke model. Tool yang tidak relevan itu dua kali rugi: bayar token per
request, dan menambah peluang model salah pilih. Jadi registry dipangkas per
intent, bukan dikirim semua sekaligus.

  descriptive -> inspect_schema, write_and_execute, make_chart
  causal      -> inspect_schema, write_and_execute, causal_route,
                 causal_analyze, causal_refute

`write_and_execute` tetap ada di jalur kausal karena eksplorasi pendukung
(cek distribusi, cek jumlah baris per arm) memang perlu. Yang DILARANG bukan
tool-nya, melainkan memakainya untuk menghitung efek kausal, dan itu sudah
dijaga prompt + number-grounding check.
"""

from __future__ import annotations

from app.agent.tools.base import Tool, ToolRegistry, ToolRunResult
from app.agent.tools.causal_analyze import CausalAnalyzeTool
from app.agent.tools.causal_refute import CausalRefuteTool
from app.agent.tools.causal_route import CausalRouteTool
from app.agent.tools.execute import MakeChartTool, WriteAndExecuteTool
from app.agent.tools.inspect_schema import InspectSchemaTool

# Tool yang menerima context kausal (_confirmed_roles) dari loop.
CAUSAL_TOOL_NAMES = {"causal_route", "causal_analyze", "causal_refute"}

# Konstruktor tiap tool, di-key nama. Sumber tunggal supaya subset di bawah
# tidak bisa menyebut tool yang tidak ada.
_TOOL_FACTORIES = {
    "inspect_schema": InspectSchemaTool,
    "write_and_execute": WriteAndExecuteTool,
    "make_chart": MakeChartTool,
    "causal_route": CausalRouteTool,
    "causal_analyze": CausalAnalyzeTool,
    "causal_refute": CausalRefuteTool,
}

# Subset tool per intent (aturan produksi #1).
TOOLSETS: dict[str, tuple[str, ...]] = {
    "descriptive": ("inspect_schema", "write_and_execute", "make_chart"),
    "causal": (
        "inspect_schema",
        "write_and_execute",
        "causal_route",
        "causal_analyze",
        "causal_refute",
    ),
}


def build_registry(names: tuple[str, ...] | list[str]) -> ToolRegistry:
    """Bangun registry berisi tool dengan nama yang diminta (urut sesuai `names`)."""
    registry = ToolRegistry()
    for name in names:
        factory = _TOOL_FACTORIES.get(name)
        if factory is None:
            raise KeyError(f"Tool '{name}' tidak dikenal. Ada: {list(_TOOL_FACTORIES)}")
        registry.register(factory())
    return registry


def build_registry_for_intent(intent: str) -> ToolRegistry:
    """Registry yang sudah dipangkas sesuai intent. Intent asing → set deskriptif."""
    return build_registry(TOOLSETS.get(intent, TOOLSETS["descriptive"]))


def build_default_registry() -> ToolRegistry:
    """Registry lengkap: 3 tool deskriptif + 3 tool kausal (BLUEPRINT D6).

    Masih dipakai test kontrak tool dan pemanggil yang memang butuh semuanya.
    ReactLoop TIDAK memakai ini lagi secara default, dia memangkas per intent.
    """
    return build_registry(tuple(_TOOL_FACTORIES))


__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolRunResult",
    "InspectSchemaTool",
    "WriteAndExecuteTool",
    "MakeChartTool",
    "CausalRouteTool",
    "CausalAnalyzeTool",
    "CausalRefuteTool",
    "CAUSAL_TOOL_NAMES",
    "TOOLSETS",
    "build_registry",
    "build_registry_for_intent",
    "build_default_registry",
]
