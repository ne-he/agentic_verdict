"""Planner — ubah pertanyaan NL jadi rencana langkah eksplisit (list[PlanStep]).

Rencana ini juga menyetir progress bar UI (Blueprint Tier A #2). Pakai Gemini untuk
menghasilkan plan terstruktur (JSON). Fungsi `generate` di-inject agar bisa di-mock saat test
(hemat kuota) — default-nya memanggil Gemini.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from app.core.config import get_settings
from app.core.schemas import PlanStep

# generate: prompt -> raw text (diharapkan JSON array of steps).
GenerateFn = Callable[[str], str]

_DEFAULT_TOOLS = ["inspect_schema", "write_and_execute", "make_chart"]

_PROMPT = """\
Kamu adalah perencana untuk agen analisis data. Pecah pertanyaan user menjadi
langkah-langkah eksplisit dan berurutan. Langkah PERTAMA harus selalu inspect_schema.

Tools yang tersedia: {tools}

Aturan output:
- Balas HANYA JSON array (tanpa teks lain, tanpa code fence).
- Tiap elemen: {{"description": "<apa yang dilakukan>", "tool": "<salah satu tool>"}}.
- 3-7 langkah. Ringkas dan konkret.

Dataset: {dataset_id}
Pertanyaan: {question}
{extra}"""

# Instruksi tambahan saat intent = causal (BLUEPRINT D2).
CAUSAL_PLAN_NOTE = (
    "CATATAN: Pertanyaan ini KAUSAL. Rencana WAJIB memakai causal_route lalu "
    "causal_analyze untuk menghitung efek — JANGAN pakai write_and_execute untuk "
    "menghitung efek kausal. write_and_execute hanya untuk eksplorasi pendukung."
)


def build_prompt(
    question: str, dataset_id: str, tool_names: list[str], extra: str = ""
) -> str:
    return _PROMPT.format(
        tools=", ".join(tool_names),
        dataset_id=dataset_id,
        question=question,
        extra=(extra + "\n") if extra else "",
    )


def _strip_fences(text: str) -> str:
    """Buang ```json ... ``` kalau model membungkus output."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return fence.group(1).strip() if fence else text


def parse_plan(raw: str, tool_names: list[str]) -> list[PlanStep]:
    """Parse JSON plan jadi list[PlanStep] tervalidasi."""
    data = json.loads(_strip_fences(raw))
    if isinstance(data, dict) and "steps" in data:
        data = data["steps"]
    if not isinstance(data, list) or not data:
        raise ValueError("Plan harus berupa JSON array tidak kosong.")

    steps: list[PlanStep] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict) or "description" not in item:
            raise ValueError(f"Langkah ke-{i} tidak valid: {item!r}")
        tool = item.get("tool") or tool_names[0]
        if tool not in tool_names:
            tool = "write_and_execute"  # fallback aman
        steps.append(PlanStep(id=i, description=str(item["description"]), tool=tool))
    return steps


class Planner:
    def __init__(self, generate: GenerateFn | None = None, model: str | None = None) -> None:
        self._generate = generate or self._default_generate
        self._model = model or get_settings().gemini_model

    def plan(
        self,
        question: str,
        dataset_id: str,
        tool_names: list[str] | None = None,
        extra: str = "",
    ) -> list[PlanStep]:
        tools = tool_names or _DEFAULT_TOOLS
        raw = self._generate(build_prompt(question, dataset_id, tools, extra))
        return parse_plan(raw, tools)

    # Default: panggil Gemini (tak dipakai saat test karena generate di-inject).
    def _default_generate(self, prompt: str) -> str:  # pragma: no cover - butuh API key
        from google import genai
        from google.genai import types

        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY belum di-set di .env")
        client = genai.Client(api_key=settings.gemini_api_key)
        resp = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return resp.text or ""
