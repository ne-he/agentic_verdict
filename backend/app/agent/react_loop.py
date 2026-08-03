"""ReAct loop (Custom) — orkestrasi: Planner -> loop(pilih tool -> eksekusi -> observasi) -> jawaban.

Protokol: tiap giliran model membalas JSON, salah satu dari:
  {"thought": "...", "action": "<tool>", "args": {...}}   -> kita eksekusi tool, umpan balik observasi
  {"final": "<jawaban markdown>", "code": "<kode kunci>"}  -> selesai

Tiga aturan produksi agent yang berlaku di loop ini:
  1. TOOL MINIMUM: registry dipangkas per intent (lihat agent/tools/__init__.py).
  2. STEP BUDGET & TIMEOUT: batas iterasi (max_tool_calls), batas perkiraan token
     (max_tokens), dan batas wall-clock per run (timeout_s). Ketiganya punya default
     yang terdokumentasi di docs/AGENT_RUNTIME.md.
  3. ALASAN TERMINASI: tiap run mencatat kenapa dia berhenti (lihat agent/termination.py),
     ikut tersimpan ke run history dan tampil di UI.

Durable state: kalau `checkpointer` diberikan, state loop ditulis ke SQLite TIAP LANGKAH,
bukan cuma di akhir. Run yang mati di tengah bisa dilanjutkan lewat `resume(run_id)`.

Kode LLM hanya jalan via tool -> sandbox (Aturan #6).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.bundle import build_analysis_bundle
from app.agent.checkpoint import NullCheckpointer, RunCheckpointer, StepRecord
from app.agent.confidence import tool_execution_success
from app.agent.intent import IntentDecision, classify_intent
from app.agent.llm import GenerateFn, make_gemini_generate
from app.agent.planner import CAUSAL_PLAN_NOTE, Planner
from app.agent.self_verify import SelfVerifier
from app.agent.tools import (
    CAUSAL_TOOL_NAMES,
    ToolRegistry,
    build_registry_for_intent,
)
from app.causal.grounding import check_grounding, render_template
from app.causal.schemas import CausalResult
from app.causal.service import compute_causal_confidence
from app.core.schemas import AnalysisResult, PlanStep, SSEEvent, ToolCall, VerificationResult

EventFn = Callable[[SSEEvent], None]

# Default budget per run (aturan produksi #2). Alasan angkanya di docs/AGENT_RUNTIME.md.
DEFAULT_MAX_TOOL_CALLS = 12
DEFAULT_MAX_TOKENS = 200_000
DEFAULT_TIMEOUT_S = 300.0

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


def _observation_line(tool: str, args: dict, output: str, error: str) -> str:
    """Blok transcript untuk satu tool call. Dipakai saat jalan normal DAN saat resume."""
    observation = f"ERROR: {error}" if error else output
    return f"\n[Aksi] {tool}({json.dumps(args, ensure_ascii=False)})\n[Observasi] {observation}\n"


@dataclass
class _LoopState:
    """Seluruh state yang dibutuhkan loop untuk jalan atau dilanjutkan.

    Dipakai dua arah: dibangun segar oleh `run()`, atau direkonstruksi dari
    checkpoint oleh `resume()`. Loop-nya sendiri (`_execute`) tidak tahu bedanya.
    """

    run_id: str
    question: str
    dataset_id: str
    causal_roles: dict | None
    intent: IntentDecision
    plan: list[PlanStep]
    registry: ToolRegistry
    transcript_head: str
    transcript_tail: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    code_pieces: list[str] = field(default_factory=list)
    chart_paths: list[str] = field(default_factory=list)
    causal_payload: dict | None = None
    tokens: int = 0
    steps_done: int = 0
    prior_elapsed_ms: int = 0

    @property
    def transcript(self) -> str:
        return self.transcript_head + self.transcript_tail


class RunNotResumable(Exception):
    """Run tidak ada di checkpoint, atau statusnya sudah selesai."""


class ReactLoop:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        generate: GenerateFn | None = None,
        planner: Planner | None = None,
        model: str | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        checkpointer: RunCheckpointer | None = None,
    ) -> None:
        # registry=None → dipangkas per intent (aturan produksi #1).
        # registry eksplisit → dihormati apa adanya (caller tahu apa yang dia mau).
        self._fixed_registry = registry
        self._generate = generate or make_gemini_generate(model)
        self._planner = planner or Planner(generate=self._generate, model=model)
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._ckpt: RunCheckpointer = checkpointer or NullCheckpointer()

    # ── API publik ────────────────────────────────────────────────────────────

    def run(
        self,
        question: str,
        dataset_id: str,
        on_event: EventFn | None = None,
        causal_roles: dict | None = None,
        run_id: str | None = None,
    ) -> AnalysisResult:
        run_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        emit = on_event or (lambda _e: None)

        # 0) Intent classification (D2) — deterministik, transparan di investigation log.
        intent = classify_intent(question)
        emit(SSEEvent(type="intent", data=intent.model_dump()))

        registry = self._registry_for(intent.intent)

        # 1) Plan (juga menyetir progress UI).
        plan_extra = CAUSAL_PLAN_NOTE if intent.intent == "causal" else ""
        plan: list[PlanStep] = self._planner.plan(
            question, dataset_id, registry.names(), extra=plan_extra
        )
        emit(SSEEvent(type="plan", data={"steps": [s.model_dump() for s in plan]}))

        state = _LoopState(
            run_id=run_id,
            question=question,
            dataset_id=dataset_id,
            causal_roles=causal_roles,
            intent=intent,
            plan=plan,
            registry=registry,
            transcript_head=self._build_transcript_head(
                question, dataset_id, intent, plan, registry, causal_roles
            ),
        )

        # Checkpoint header DULUAN: kalau proses mati sebelum langkah pertama pun,
        # run-nya tetap terdaftar sebagai "running" dan bisa di-resume.
        self._ckpt.start(
            run_id=run_id,
            question=question,
            dataset_id=dataset_id,
            causal_roles=causal_roles,
            intent=intent.intent,
            intent_data=intent.model_dump(),
            plan=plan,
            transcript_head=state.transcript_head,
        )
        return self._execute(state, emit)

    def resume(self, run_id: str, on_event: EventFn | None = None) -> AnalysisResult:
        """Lanjutkan run dari langkah terakhir yang tersimpan di checkpoint.

        Raise RunNotResumable kalau run_id tidak dikenal atau statusnya sudah selesai.
        """
        emit = on_event or (lambda _e: None)
        saved = self._ckpt.load(run_id)
        if saved is None:
            raise RunNotResumable(f"run '{run_id}' tidak ada di checkpoint")
        if saved.status != "running":
            raise RunNotResumable(
                f"run '{run_id}' statusnya '{saved.status}', bukan 'running', tidak perlu resume"
            )

        intent = IntentDecision.model_validate(saved.intent_data) if saved.intent_data else (
            IntentDecision(intent="descriptive")
        )
        registry = self._registry_for(saved.intent)

        # Rekonstruksi transcript dari run_steps: step record adalah sumber kebenaran,
        # bukan variabel di memori proses yang sudah mati.
        tail = ""
        code_pieces: list[str] = []
        chart_paths: list[str] = []
        causal_payload: dict | None = None
        for step in saved.steps:
            if step.kind == "tool":
                tail += _observation_line(step.tool, step.args, step.output, step.error)
                if step.tool in ("write_and_execute", "make_chart") and step.args.get("code"):
                    code_pieces.append(str(step.args["code"]))
                chart_paths.extend(step.chart_paths)
                if step.tool == "causal_analyze" and not step.error and step.output:
                    try:
                        causal_payload = json.loads(step.output)
                    except json.JSONDecodeError:
                        causal_payload = None
            else:
                tail += step.output

        state = _LoopState(
            run_id=run_id,
            question=saved.question,
            dataset_id=saved.dataset_id,
            causal_roles=saved.causal_roles,
            intent=intent,
            plan=saved.plan,
            registry=registry,
            transcript_head=saved.transcript_head,
            transcript_tail=tail,
            tool_calls=saved.tool_calls(),
            code_pieces=code_pieces,
            chart_paths=chart_paths,
            causal_payload=causal_payload,
            tokens=saved.tokens,
            steps_done=saved.steps_done,
            prior_elapsed_ms=saved.elapsed_ms,
        )

        self._ckpt.bump_resume_count(run_id)
        emit(SSEEvent(type="intent", data=intent.model_dump()))
        emit(SSEEvent(type="plan", data={"steps": [s.model_dump() for s in state.plan]}))
        emit(
            SSEEvent(
                type="step",
                data={
                    "tool": "resume",
                    "args": {"run_id": run_id, "steps_replayed": state.steps_done},
                },
            )
        )
        return self._execute(state, emit)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _registry_for(self, intent: str) -> ToolRegistry:
        if self._fixed_registry is not None:
            return self._fixed_registry
        return build_registry_for_intent(intent)

    def _build_transcript_head(
        self,
        question: str,
        dataset_id: str,
        intent: IntentDecision,
        plan: list[PlanStep],
        registry: ToolRegistry,
        causal_roles: dict | None,
    ) -> str:
        causal_note = ""
        if intent.intent == "causal":
            causal_note = (
                _CAUSAL_CONFIRMED.format(roles=json.dumps(causal_roles, ensure_ascii=False))
                if causal_roles
                else _CAUSAL_UNCONFIRMED
            )
        return (
            _SYSTEM.format(tool_docs=_tool_docs(registry))
            + causal_note
            + f"\n\nDataset: {dataset_id}\nPertanyaan: {question}\n"
            + "Rencana: " + " | ".join(f"{s.id}.{s.description}" for s in plan) + "\n"
        )

    def _execute(self, state: _LoopState, emit: EventFn) -> AnalysisResult:  # noqa: C901
        started = time.monotonic()
        answer = ""
        final_code = ""
        verify_key_value: Any = None
        verify_sql: Any = None
        termination_reason = "step_budget"
        step_index = state.steps_done

        while step_index < self._max_tool_calls:
            elapsed = time.monotonic() - started
            if elapsed > self._timeout_s:
                answer = (
                    f"Berhenti: melewati batas waktu {self._timeout_s:.0f} detik. "
                    "Hasil parsial dari observasi di atas."
                )
                termination_reason = "timeout"
                break

            state.tokens += _approx_tokens(state.transcript)
            if state.tokens > self._max_tokens:
                answer = "Berhenti: melewati budget token. Hasil parsial dari observasi di atas."
                termination_reason = "token_budget"
                break

            raw = self._generate(state.transcript + "\nBalas JSON:")
            state.tokens += _approx_tokens(raw)
            try:
                action = json.loads(_strip_fences(raw))
            except json.JSONDecodeError:
                obs = "\n[Observasi] Output bukan JSON valid. Balas JSON sesuai protokol.\n"
                state.transcript_tail += obs
                self._ckpt.record_step(
                    state.run_id,
                    StepRecord(
                        step_index=step_index,
                        kind="invalid_response",
                        output=obs,
                        tokens_after=state.tokens,
                    ),
                )
                step_index += 1
                continue

            if action.get("final"):
                answer = str(action["final"])
                final_code = str(action.get("code") or "")
                verify_key_value = action.get("key_value")
                verify_sql = action.get("verify_sql")
                termination_reason = "completed"
                break

            tool_name = action.get("action") or action.get("tool")
            args = action.get("args") or {}
            if tool_name not in state.registry.names():
                obs = (
                    f"\n[Observasi] Tool '{tool_name}' tidak ada. "
                    f"Pilih: {state.registry.names()}\n"
                )
                state.transcript_tail += obs
                self._ckpt.record_step(
                    state.run_id,
                    StepRecord(
                        step_index=step_index,
                        kind="unknown_tool",
                        output=obs,
                        tokens_after=state.tokens,
                    ),
                )
                step_index += 1
                continue

            emit(SSEEvent(type="step", data={"tool": tool_name, "args": args}))
            # Context kausal di-inject per-call (thread-safe), bukan dari argumen LLM.
            if tool_name in CAUSAL_TOOL_NAMES:
                args.pop("_confirmed_roles", None)  # LLM tidak boleh memalsukan konfirmasi
                result = state.registry.get(tool_name).run(
                    dataset_id=state.dataset_id, _confirmed_roles=state.causal_roles, **args
                )
            else:
                result = state.registry.get(tool_name).run(dataset_id=state.dataset_id, **args)
            if tool_name == "causal_analyze" and result.ok:
                try:
                    state.causal_payload = json.loads(result.output)
                    emit(SSEEvent(type="causal", data=state.causal_payload))
                except json.JSONDecodeError:
                    state.causal_payload = None
            elif tool_name == "causal_route" and result.ok:
                try:
                    emit(SSEEvent(type="causal", data=json.loads(result.output)))
                except json.JSONDecodeError:
                    pass
            state.tool_calls.append(
                ToolCall(
                    tool=tool_name,
                    input=args,
                    output=result.output or None,
                    error=result.error,
                )
            )
            if tool_name in ("write_and_execute", "make_chart") and args.get("code"):
                state.code_pieces.append(str(args["code"]))
            if result.chart_paths:
                state.chart_paths.extend(result.chart_paths)
                emit(SSEEvent(type="chart", data={"paths": result.chart_paths}))

            emit(SSEEvent(type="tool", data={"tool": tool_name, "ok": result.ok}))
            state.transcript_tail += _observation_line(
                tool_name, args, result.output, result.error or ""
            )

            # Checkpoint SETELAH tool jalan & observasi masuk transcript.
            # Urutan ini penting: yang tersimpan harus persis state yang dipakai
            # iterasi berikutnya, supaya resume tidak mengulang efek samping tool.
            self._ckpt.record_step(
                state.run_id,
                StepRecord(
                    step_index=step_index,
                    kind="tool",
                    tool=tool_name,
                    args=args,
                    output=result.output or "",
                    error=result.error or "",
                    chart_paths=list(result.chart_paths),
                    tokens_after=state.tokens,
                ),
            )
            step_index += 1
        else:
            answer = answer or "Berhenti: mencapai batas iterasi tool tanpa jawaban final."
            termination_reason = "step_budget"

        state.steps_done = step_index
        final_code = final_code or "\n\n".join(state.code_pieces)

        # Self-verify silang kalau agent menyertakan key_value + verify_sql.
        verification: VerificationResult | None = None
        if verify_sql and verify_key_value is not None:
            try:
                verification = SelfVerifier().verify_numeric(
                    state.dataset_id, float(verify_key_value), str(verify_sql)
                )
                emit(SSEEvent(type="verify", data=verification.model_dump()))
            except Exception:  # noqa: BLE001 - verifikasi gagal != analisis gagal
                verification = None

        # Jalur kausal: number-grounding (P1/D4) + confidence kausal (D5).
        answer_grounded = True
        causal_confidence = None
        if state.causal_payload is not None:
            try:
                causal_result = CausalResult.model_validate(state.causal_payload)
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
                    tool_execution_success=tool_execution_success(state.tool_calls),
                )

        duration_ms = state.prior_elapsed_ms + int((time.monotonic() - started) * 1000)
        result = build_analysis_bundle(
            run_id=state.run_id,
            dataset_id=state.dataset_id,
            answer_markdown=answer,
            code=final_code,
            chart_paths=state.chart_paths,
            verification=verification,
            tool_calls=state.tool_calls,
            tokens=state.tokens,
            duration_ms=duration_ms,
        )
        result = result.model_copy(
            update={
                "intent": state.intent.intent,
                "causal": state.causal_payload,
                "causal_confidence": (
                    causal_confidence.model_dump() if causal_confidence else None
                ),
                "answer_grounded": answer_grounded,
                "termination_reason": termination_reason,
            }
        )
        self._ckpt.finish(
            run_id=state.run_id,
            status="completed",
            termination_reason=termination_reason,
            tokens=state.tokens,
            elapsed_ms=duration_ms,
        )
        if causal_confidence is not None:
            emit(SSEEvent(type="confidence", data={"causal": causal_confidence.model_dump()}))
        if result.confidence is not None:
            emit(SSEEvent(type="confidence", data=result.confidence.model_dump()))
        emit(SSEEvent(type="final", data=result.model_dump()))
        return result
