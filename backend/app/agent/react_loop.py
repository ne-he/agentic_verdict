"""ReAct loop (Custom) — orkestrasi: Planner -> loop(pilih tool -> eksekusi -> observasi) -> jawaban.

Protokol: tiap giliran model membalas JSON, salah satu dari:
  {"thought": "...", "action": "<tool>", "args": {...}}   -> kita eksekusi tool, umpan balik observasi
  {"final": "<jawaban markdown>", "code": "<kode kunci>"}  -> selesai

Guard: batas jumlah tool call (default 12) dan budget token (perkiraan) supaya tak infinite/boros.
Kode LLM hanya jalan via tool -> sandbox (Aturan #6).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Callable

from app.agent.bundle import build_analysis_bundle
from app.agent.confidence import tool_execution_success
from app.agent.intent import classify_intent
from app.agent.llm import GenerateFn, make_gemini_generate
from app.agent.planner import CAUSAL_PLAN_NOTE, Planner
from app.agent.self_verify import SelfVerifier
from app.agent.tools import CAUSAL_TOOL_NAMES, ToolRegistry, build_default_registry
from app.causal.grounding import check_grounding, render_template
from app.causal.schemas import CausalResult
from app.causal.service import compute_causal_confidence
from app.core.schemas import AnalysisResult, PlanStep, SSEEvent, ToolCall, VerificationResult

EventFn = Callable[[SSEEvent], None]

_SYSTEM = """\
Kamu ANALYST, agen analisis data yang teliti. Jawab pertanyaan user HANYA berdasarkan
data, lewat tools. Jangan mengarang angka. Kalau data tidak mendukung, katakan apa adanya.

Tools tersedia:
{tool_docs}

Protokol — balas SATU objek JSON saja (tanpa code fence), salah satu bentuk:
1) Memanggil tool:
   {{"thought": "alasan singkat", "action": "<nama_tool>", "args": {{...sesuai parameter tool...}}}}
2) Jawaban final (setelah cukup bukti):
   {{"final": "<jawaban ringkas markdown, sertakan angka kunci>", "code": "<kode python utama>",
     "key_value": <angka kunci jawaban sebagai number, opsional>,
     "verify_sql": "<SQL DuckDB utk menghitung ULANG key_value; nama tabel dataset = t, opsional>"}}

Selalu mulai dengan inspect_schema. Gunakan write_and_execute untuk menghitung (WAJIB print hasil).
Setelah angka didapat, beri "final". Kalau jawaban berupa SATU angka kunci, sertakan key_value +
verify_sql (mis. "SELECT SUM(\\"Sales\\") FROM t") supaya bisa diverifikasi silang.
Jangan memanggil tool lebih dari perlu.
"""

# Instruksi tambahan saat intent = causal (BLUEPRINT D2/D3/P1).
_CAUSAL_UNCONFIRMED = """
PERTANYAAN INI KAUSAL. Aturan jalur kausal (WAJIB):
- Panggil causal_route untuk mengusulkan mapping kolom + metode. JANGAN panggil causal_analyze —
  mapping BELUM dikonfirmasi user.
- Jawaban final: sampaikan usulan mapping (treatment/outcome/covariates), metode yang diusulkan
  router beserta alasannya, lalu minta user KONFIRMASI mapping lewat panel Causal.
- DILARANG menghitung/menyebut angka efek kausal sendiri (via write_and_execute atau tebakan).
"""

_CAUSAL_CONFIRMED = """
PERTANYAAN INI KAUSAL dan mapping kolom SUDAH dikonfirmasi user: {roles}
Aturan jalur kausal (WAJIB):
- Panggil causal_route (mapping terkonfirmasi dipakai otomatis), lalu causal_analyze.
- SEMUA angka efek berasal dari output causal_analyze — kutip persis, JANGAN menghitung sendiri
  dan JANGAN membulatkan berlebihan. Jawaban final akan dicek number-grounding terhadap hasil engine.
- Jawaban final: efek + CI + signifikansi, alasan metode dari router, status asumsi, dan keputusan
  (deploy/hold) dari engine.
"""


def _tool_docs(registry: ToolRegistry) -> str:
    lines = []
    for decl in registry.function_declarations():
        params = ", ".join(decl["parameters"].get("properties", {}).keys()) or "(tanpa argumen)"
        lines.append(f"- {decl['name']}({params}): {decl['description']}")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1).strip() if m else text


def _approx_tokens(text: str) -> int:
    """Perkiraan kasar token (~4 char/token). Untuk budget guard M1; akuntansi presisi di M3."""
    return max(1, len(text) // 4)


class ReactLoop:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        generate: GenerateFn | None = None,
        planner: Planner | None = None,
        model: str | None = None,
        max_tool_calls: int = 12,
        max_tokens: int = 200_000,
    ) -> None:
        self._registry = registry or build_default_registry()
        self._generate = generate or make_gemini_generate(model)
        self._planner = planner or Planner(generate=self._generate, model=model)
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens

    def run(
        self,
        question: str,
        dataset_id: str,
        on_event: EventFn | None = None,
        causal_roles: dict | None = None,
    ) -> AnalysisResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        emit = on_event or (lambda _e: None)

        # 0) Intent classification (D2) — deterministik, transparan di investigation log.
        intent = classify_intent(question)
        emit(SSEEvent(type="intent", data=intent.model_dump()))

        # 1) Plan (juga menyetir progress UI).
        plan_extra = CAUSAL_PLAN_NOTE if intent.intent == "causal" else ""
        plan: list[PlanStep] = self._planner.plan(
            question, dataset_id, self._registry.names(), extra=plan_extra
        )
        emit(SSEEvent(type="plan", data={"steps": [s.model_dump() for s in plan]}))

        # 2) Tool loop.
        tool_calls: list[ToolCall] = []
        code_pieces: list[str] = []
        chart_paths: list[str] = []
        causal_payload: dict | None = None   # CausalResult dari causal_analyze
        tokens = 0
        causal_note = ""
        if intent.intent == "causal":
            causal_note = (
                _CAUSAL_CONFIRMED.format(roles=json.dumps(causal_roles, ensure_ascii=False))
                if causal_roles
                else _CAUSAL_UNCONFIRMED
            )
        transcript = (
            _SYSTEM.format(tool_docs=_tool_docs(self._registry))
            + causal_note
            + f"\n\nDataset: {dataset_id}\nPertanyaan: {question}\n"
            + "Rencana: " + " | ".join(f"{s.id}.{s.description}" for s in plan) + "\n"
        )

        answer = ""
        final_code = ""
        verify_key_value = None
        verify_sql = None
        for _ in range(self._max_tool_calls):
            tokens += _approx_tokens(transcript)
            if tokens > self._max_tokens:
                answer = "Berhenti: melewati budget token. Hasil parsial dari observasi di atas."
                break

            raw = self._generate(transcript + "\nBalas JSON:")
            tokens += _approx_tokens(raw)
            try:
                action = json.loads(_strip_fences(raw))
            except json.JSONDecodeError:
                transcript += f"\n[Observasi] Output bukan JSON valid. Balas JSON sesuai protokol.\n"
                continue

            if action.get("final"):
                answer = str(action["final"])
                final_code = str(action.get("code") or "")
                verify_key_value = action.get("key_value")
                verify_sql = action.get("verify_sql")
                break

            tool_name = action.get("action") or action.get("tool")
            args = action.get("args") or {}
            if tool_name not in self._registry.names():
                transcript += f"\n[Observasi] Tool '{tool_name}' tidak ada. Pilih: {self._registry.names()}\n"
                continue

            emit(SSEEvent(type="step", data={"tool": tool_name, "args": args}))
            # Context kausal di-inject per-call (thread-safe), bukan dari argumen LLM.
            if tool_name in CAUSAL_TOOL_NAMES:
                args.pop("_confirmed_roles", None)  # LLM tidak boleh memalsukan konfirmasi
                result = self._registry.get(tool_name).run(
                    dataset_id=dataset_id, _confirmed_roles=causal_roles, **args
                )
            else:
                result = self._registry.get(tool_name).run(dataset_id=dataset_id, **args)
            if tool_name == "causal_analyze" and result.ok:
                try:
                    causal_payload = json.loads(result.output)
                    emit(SSEEvent(type="causal", data=causal_payload))
                except json.JSONDecodeError:
                    causal_payload = None
            elif tool_name == "causal_route" and result.ok:
                try:
                    emit(SSEEvent(type="causal", data=json.loads(result.output)))
                except json.JSONDecodeError:
                    pass
            observation = result.error and f"ERROR: {result.error}" or result.output
            tool_calls.append(
                ToolCall(
                    tool=tool_name,
                    input=args,
                    output=result.output or None,
                    error=result.error,
                )
            )
            if tool_name in ("write_and_execute", "make_chart") and args.get("code"):
                code_pieces.append(str(args["code"]))
            if result.chart_paths:
                chart_paths.extend(result.chart_paths)
                emit(SSEEvent(type="chart", data={"paths": result.chart_paths}))

            emit(SSEEvent(type="tool", data={"tool": tool_name, "ok": result.ok}))
            transcript += f"\n[Aksi] {tool_name}({json.dumps(args, ensure_ascii=False)})\n[Observasi] {observation}\n"
        else:
            answer = answer or "Berhenti: mencapai batas iterasi tool tanpa jawaban final."

        final_code = final_code or "\n\n".join(code_pieces)

        # Self-verify silang kalau agent menyertakan key_value + verify_sql.
        verification: VerificationResult | None = None
        if verify_sql and verify_key_value is not None:
            try:
                verification = SelfVerifier().verify_numeric(
                    dataset_id, float(verify_key_value), str(verify_sql)
                )
                emit(SSEEvent(type="verify", data=verification.model_dump()))
            except Exception:  # noqa: BLE001 - verifikasi gagal != analisis gagal
                verification = None

        # Jalur kausal: number-grounding (P1/D4) + confidence kausal (D5).
        answer_grounded = True
        causal_confidence = None
        if causal_payload is not None:
            try:
                causal_result = CausalResult.model_validate(causal_payload)
            except Exception:  # noqa: BLE001 - payload rusak -> perlakukan spt tanpa hasil kausal
                causal_result = None
            if causal_result is not None:
                grounded, ungrounded = check_grounding(answer, causal_result)
                if not grounded:
                    # Prosa LLM memuat angka yang tak ada di hasil engine → fallback
                    # template deterministik. Lebih baik jujur daripada halu.
                    answer = (
                        render_template(causal_result)
                        + "\n\n> ⚠️ Narasi otomatis diganti template deterministik karena "
                        + f"angka berikut tidak ditemukan di hasil engine: {', '.join(ungrounded)}."
                    )
                    answer_grounded = False
                causal_confidence = compute_causal_confidence(
                    router_decision=causal_result.router_decision,
                    assumptions=causal_result.assumptions,
                    verification_agreement=(
                        verification.agreement if verification is not None else None
                    ),
                    tool_execution_success=tool_execution_success(tool_calls),
                )

        result = build_analysis_bundle(
            run_id=run_id,
            dataset_id=dataset_id,
            answer_markdown=answer,
            code=final_code,
            chart_paths=chart_paths,
            verification=verification,
            tool_calls=tool_calls,
            tokens=tokens,
        )
        result = result.model_copy(
            update={
                "intent": intent.intent,
                "causal": causal_payload,
                "causal_confidence": (
                    causal_confidence.model_dump() if causal_confidence else None
                ),
                "answer_grounded": answer_grounded,
            }
        )
        if causal_confidence is not None:
            emit(SSEEvent(type="confidence", data={"causal": causal_confidence.model_dump()}))
        if result.confidence is not None:
            emit(SSEEvent(type="confidence", data=result.confidence.model_dump()))
        emit(SSEEvent(type="final", data=result.model_dump()))
        return result
