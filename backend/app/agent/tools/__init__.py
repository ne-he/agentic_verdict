"""Registry tool default untuk VERDICT ANALYST."""

from __future__ import annotations

from app.agent.tools.base import Tool, ToolRegistry, ToolRunResult
from app.agent.tools.causal_analyze import CausalAnalyzeTool
from app.agent.tools.causal_refute import CausalRefuteTool
from app.agent.tools.causal_route import CausalRouteTool
from app.agent.tools.execute import MakeChartTool, WriteAndExecuteTool
from app.agent.tools.inspect_schema import InspectSchemaTool

# Tool yang menerima context kausal (_confirmed_roles) dari loop.
CAUSAL_TOOL_NAMES = {"causal_route", "causal_analyze", "causal_refute"}


def build_default_registry() -> ToolRegistry:
    """Registry lengkap: 3 tool deskriptif + 3 tool kausal (BLUEPRINT D6)."""
    registry = ToolRegistry()
    registry.register(InspectSchemaTool())
    registry.register(WriteAndExecuteTool())
    registry.register(MakeChartTool())
    registry.register(CausalRouteTool())
    registry.register(CausalAnalyzeTool())
    registry.register(CausalRefuteTool())
    return registry


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
    "build_default_registry",
]
