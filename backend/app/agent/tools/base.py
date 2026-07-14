"""Kerangka tool + registry untuk ReAct loop & Gemini function calling.

Tiap tool = subclass `Tool` dgn `name`, `description`, `parameters` (JSON schema utk Gemini),
dan `run()`. Nambah tool = register class baru (extensible). MVP cukup 3 tool.
`dataset_id` di-inject oleh loop (konteks run), BUKAN argumen dari LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ToolRunResult(BaseModel):
    """Hasil eksekusi satu tool (observasi yang diumpan balik ke loop)."""

    output: str = ""
    chart_paths: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Tool(ABC):
    """Kontrak tool. `parameters` = JSON schema object utk argumen yang DIISI LLM."""

    name: str
    description: str
    parameters: dict  # {"type":"object","properties":{...},"required":[...]}

    @abstractmethod
    def run(self, *, dataset_id: str, **kwargs) -> ToolRunResult:
        """Jalankan tool. dataset_id dari konteks run; kwargs dari LLM (sesuai parameters)."""

    def to_function_declaration(self) -> dict:
        """Format function declaration buat Gemini function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Kumpulan tool ter-register, di-key nama."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' sudah terdaftar.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' tidak terdaftar. Ada: {list(self._tools)}")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)

    def function_declarations(self) -> list[dict]:
        """Semua function declaration utk dikirim ke Gemini."""
        return [t.to_function_declaration() for t in self._tools.values()]
