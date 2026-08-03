"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AnalysisResult,
  CausalConfidenceBreakdown,
  CausalRoles,
  CausalRouteProposal,
  ConfidenceBreakdown,
  DatasetInfo,
  IntentDecision,
  PlanStep,
  SSEEvent,
  VerificationResult,
} from "@/lib/types";
import { listDatasets, streamAnalyze } from "@/lib/api";
import {
  cn,
  terminationColorClass,
  terminationIsIncomplete,
  terminationLabel,
} from "@/lib/utils";
import { ConfidenceBadge } from "./confidence-badge";
import { ExecutionTrace, type TraceNode, toolLabel } from "./execution-trace";
import { WorkspaceTabs, type TabKey } from "./workspace-tabs";
import { RoleMappingModal } from "@/components/causal/role-mapping-modal";

interface SessionTurn {
  num: string;
  text: string;
  conf: string;
  confKind: "high" | "medium" | "low" | "pending";
  time: string;
}

const confKindFromLabel = (label?: string | null): SessionTurn["confKind"] => {
  if (label === "HIGH") return "high";
  if (label === "MEDIUM") return "medium";
  if (label === "LOW") return "low";
  return "pending";
};

const confColor: Record<SessionTurn["confKind"], string> = {
  high: "text-pass",
  medium: "text-warn",
  low: "text-fail",
  pending: "text-faint",
};

export function AnalyzeView() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [activeQuestion, setActiveQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamLog, setStreamLog] = useState<string[]>([]);
  const [trace, setTrace] = useState<TraceNode[]>([]);
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [confidence, setConfidence] = useState<ConfidenceBreakdown | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [chartPaths, setChartPaths] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>("summary");
  const [session, setSession] = useState<SessionTurn[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Jalur kausal (BLUEPRINT M2): proposal router, confidence kausal, mapping terkonfirmasi.
  const [causalProposal, setCausalProposal] = useState<CausalRouteProposal | null>(null);
  const [causalConfidence, setCausalConfidence] = useState<CausalConfidenceBreakdown | null>(null);
  const [confirmedRoles, setConfirmedRoles] = useState<CausalRoles | null>(null);
  const [mappingOpen, setMappingOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listDatasets()
      .then((ds) => {
        setDatasets(ds);
        if (ds.length) setDatasetId((cur) => cur || ds[0].dataset_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const handleEvent = useCallback((ev: SSEEvent) => {
    switch (ev.type) {
      case "intent": {
        const d = ev.data as unknown as IntentDecision;
        setStreamLog((l) => [
          ...l,
          `› intent: ${d.intent}${d.signals?.length ? ` (${d.signals.join(", ")})` : ""}`,
        ]);
        break;
      }
      case "causal": {
        // Dua bentuk payload: proposal router (needs_confirmation ada) atau CausalResult utuh.
        if ("needs_confirmation" in ev.data) {
          const p = ev.data as unknown as CausalRouteProposal;
          setCausalProposal(p);
          setStreamLog((l) => [
            ...l,
            `› router: ${p.router_decision.method} (conf ${p.router_decision.confidence.toFixed(2)})${p.needs_confirmation ? " · butuh konfirmasi mapping" : ""}`,
          ]);
        } else {
          setStreamLog((l) => [...l, "› causal engine selesai — angka dihitung deterministik"]);
        }
        break;
      }
      case "plan": {
        const steps = (ev.data.steps as PlanStep[]) ?? [];
        setTrace([{ label: "Planner", tool: "planner", status: "done" }]);
        setStreamLog((l) => [...l, `› plan ready · ${steps.length} langkah`]);
        break;
      }
      case "step": {
        const tool = String(ev.data.tool ?? "");
        setTrace((t) => [...t, { label: toolLabel(tool), tool, status: "running" }]);
        setStreamLog((l) => [...l, `→ ${tool}`]);
        break;
      }
      case "tool": {
        const ok = Boolean(ev.data.ok);
        setTrace((t) => {
          const copy = [...t];
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].status === "running") {
              copy[i] = { ...copy[i], status: ok ? "done" : "error" };
              break;
            }
          }
          return copy;
        });
        break;
      }
      case "chart": {
        const paths = (ev.data.paths as string[]) ?? [];
        setChartPaths((c) => [...c, ...paths]);
        setStreamLog((l) => [...l, `› ${paths.length} chart dirender`]);
        break;
      }
      case "verify": {
        const v = ev.data as unknown as VerificationResult;
        setVerification(v);
        setTrace((t) => [...t, { label: "Self-Verify", tool: "verify", status: v.passed ? "done" : "error" }]);
        setStreamLog((l) => [...l, `› verify ${v.passed ? "consistent" : "discrepancy"} (agreement ${v.agreement.toFixed(2)})`]);
        break;
      }
      case "confidence": {
        // Payload kausal dibungkus {causal: {...}} — pisahkan dari confidence standar.
        if ("causal" in ev.data) {
          setCausalConfidence(ev.data.causal as unknown as CausalConfidenceBreakdown);
        } else {
          setConfidence(ev.data as unknown as ConfidenceBreakdown);
        }
        break;
      }
      case "final": {
        const r = ev.data as unknown as AnalysisResult;
        setResult(r);
        setConfidence(r.confidence);
        setVerification(r.verification);
        setChartPaths(r.chart_paths ?? []);
        if (r.causal_confidence) setCausalConfidence(r.causal_confidence);
        if (r.intent === "causal") setActiveTab("causal");
        setTrace((t) => [...t, { label: "Answer", tool: "answer", status: "done" }]);
        setStreamLog((l) => [...l, "› jawaban tersusun. Selesai."]);
        setSession((s) => [
          ...s,
          {
            num: String(s.length + 1).padStart(2, "0"),
            text: r.answer_markdown.replace(/\*\*/g, "").slice(0, 120),
            conf: r.confidence ? `${r.confidence.label} ${Math.round(r.confidence.final * 100)}%` : "—",
            confKind: confKindFromLabel(r.confidence?.label),
            time: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
        break;
      }
      case "error": {
        setError(String(ev.data.message ?? "error tak diketahui"));
        break;
      }
    }
  }, []);

  const runQuestion = useCallback(
    async (rawQ: string, roles?: CausalRoles | null) => {
      const q = rawQ.trim();
      if (!q || !datasetId || streaming) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setActiveQuestion(q);
      setStreaming(true);
      setError(null);
      setStreamLog([]);
      setTrace([]);
      setVerification(null);
      setConfidence(null);
      setResult(null);
      setChartPaths([]);
      setCausalProposal(null);
      setCausalConfidence(null);
      setMappingOpen(false);
      setActiveTab("summary");

      try {
        await streamAnalyze(
          {
            question: q,
            dataset_id: datasetId,
            // roles eksplisit > mapping yang sudah dikonfirmasi sebelumnya (per dataset)
            causal_roles: roles !== undefined ? roles : confirmedRoles,
          },
          handleEvent,
          controller.signal,
        );
      } catch (e) {
        if (!controller.signal.aborted) setError(String(e));
      } finally {
        setStreaming(false);
        setQuestion("");
      }
    },
    [datasetId, streaming, handleEvent, confirmedRoles],
  );

  const submit = useCallback(() => runQuestion(question), [runQuestion, question]);

  // D3: usulan mapping masuk & belum terkonfirmasi → buka modal begitu run selesai.
  useEffect(() => {
    if (!streaming && causalProposal?.needs_confirmation && !result?.causal) {
      setMappingOpen(true);
    }
  }, [streaming, causalProposal, result]);

  const confirmMapping = useCallback(
    (roles: CausalRoles) => {
      setConfirmedRoles(roles);
      setMappingOpen(false);
      // Jalankan ulang pertanyaan yang sama dengan mapping terkonfirmasi.
      if (activeQuestion) void runQuestion(activeQuestion, roles);
    },
    [activeQuestion, runQuestion],
  );

  // Ganti dataset = mapping lama tidak berlaku.
  useEffect(() => {
    setConfirmedRoles(null);
    setCausalProposal(null);
  }, [datasetId]);

  const currentDataset = datasets.find((d) => d.dataset_id === datasetId);

  return (
    <div className="flex min-h-0 flex-1 flex-wrap items-stretch">
      {/* LEFT: investigation log */}
      <aside className="flex min-w-[340px] max-w-[480px] flex-[1_1_380px] flex-col border-r border-line bg-bg">
        <div className="border-b border-line">
          <div className="flex items-stretch">
            {datasets.map((ds) => (
              <button
                key={ds.dataset_id}
                onClick={() => setDatasetId(ds.dataset_id)}
                className={cn(
                  "border-r border-line px-[14px] py-[9px] font-mono text-[11px] transition-colors",
                  ds.dataset_id === datasetId
                    ? "bg-panel text-ink"
                    : "text-faint hover:text-muted",
                )}
              >
                {ds.dataset_id}
              </button>
            ))}
          </div>
          {currentDataset && (
            <div className="flex items-center gap-[10px] px-4 py-[9px] font-mono text-[10.5px] text-faint">
              <span className="text-ink">{currentDataset.file}</span>
              <span className="text-[#2a2a2a]">·</span>
              <span>{currentDataset.encoding}</span>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="px-4 pb-2 pt-[13px] text-[10px] uppercase tracking-[0.14em] text-faint">
            Investigation log
          </div>
          {session.length === 0 && (
            <div className="px-4 py-3 font-mono text-[12px] text-faint">
              Belum ada pertanyaan. Mulai di bawah ↓
            </div>
          )}
          {session.map((turn) => (
            <div key={turn.num} className="border-b border-line/60 px-4 py-3">
              <div className="flex gap-[13px]">
                <span className="flex-none pt-px font-mono text-[12px] text-accent">
                  {turn.num}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] leading-[1.5] text-ink">{turn.text}</div>
                  <div className="mt-[6px] flex items-center gap-[10px] font-mono text-[10.5px]">
                    <span className={cn("tracking-[0.03em]", confColor[turn.confKind])}>
                      {turn.conf}
                    </span>
                    <span className="text-[#3a3a3a]">·</span>
                    <span className="text-faint">{turn.time}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-line px-[14px] py-3">
          <div className="flex items-stretch border border-line2 bg-bg-soft">
            <span className="flex items-center pl-[11px] font-mono text-[13px] text-accent">
              &gt;
            </span>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="Tanya soal dataset ini…"
              disabled={streaming}
              className="min-w-0 flex-1 bg-transparent px-[10px] py-[11px] text-[13.5px] text-ink outline-none disabled:opacity-50"
            />
            <button
              onClick={submit}
              disabled={streaming || !question.trim()}
              title="Run analysis"
              className="w-[42px] flex-none border-l border-line2 bg-accent font-mono text-[16px] text-bg disabled:opacity-40"
            >
              →
            </button>
          </div>
          <div className="mt-[7px] font-mono text-[10px] text-[#4a4a4a]">
            ⏎ run · follow-up mempertahankan konteks dataset
          </div>
        </div>
      </aside>

      {/* RIGHT: workspace */}
      <section className="flex min-w-0 flex-[999_1_560px] flex-col bg-bg">
        <div className="flex flex-wrap items-center gap-[11px] border-b border-line px-[22px] py-[11px] font-mono text-[11px] text-faint">
          <span className="text-accent">{result ? `Run ${result.run_id}` : "Run —"}</span>
          <span className="text-[#2a2a2a]">|</span>
          <span>{result ? `${result.duration_ms} ms` : "— ms"}</span>
          <span className="text-[#2a2a2a]">|</span>
          <span>{result ? `${result.tokens} tok` : "— tok"}</span>
          <span className="text-[#2a2a2a]">|</span>
          <span>{currentDataset?.dataset_id ?? "—"}</span>
          {result && (
            <>
              <span className="text-[#2a2a2a]">|</span>
              <span
                title="Alasan run berhenti"
                className={cn(terminationColorClass(result.termination_reason))}
              >
                {terminationLabel(result.termination_reason)}
              </span>
            </>
          )}
        </div>

        {result && terminationIsIncomplete(result.termination_reason) && (
          <div className="border-b border-line bg-warn/10 px-[22px] py-[10px] font-mono text-[11.5px] text-warn">
            Run ini tidak selesai normal ({terminationLabel(result.termination_reason)}). Jawaban di
            bawah kemungkinan belum tuntas.
          </div>
        )}

        <div className="flex flex-wrap items-start justify-between gap-6 border-b border-line px-[22px] py-4">
          <div className="min-w-0 flex-1">
            <div className="mb-[7px] text-[10px] uppercase tracking-[0.14em] text-faint">
              Active question
            </div>
            <div className="max-w-[560px] text-[18px] font-semibold leading-[1.4] tracking-[-0.02em]">
              {activeQuestion || "—"}
            </div>
          </div>
          <ConfidenceBadge c={confidence} />
        </div>

        <ExecutionTrace nodes={trace} />

        {streaming && (
          <div className="border-b border-line px-[22px] py-[13px]">
            {streamLog.map((line, i) => (
              <div key={i} className="animate-fadein py-[2px] font-mono text-[11.5px] text-muted">
                {line}
              </div>
            ))}
            <div className="mt-[7px] h-[2px] overflow-hidden bg-line">
              <div className="h-full w-1/3 animate-grow bg-accent" />
            </div>
          </div>
        )}

        {error && (
          <div className="border-b border-line bg-fail/10 px-[22px] py-3 font-mono text-[12px] text-fail">
            error — {error}
          </div>
        )}

        <WorkspaceTabs
          active={activeTab}
          onTab={setActiveTab}
          result={result}
          verification={verification}
          chartPaths={chartPaths}
          onRerun={activeQuestion ? () => runQuestion(activeQuestion) : undefined}
          causalProposal={causalProposal}
          causalConfidence={causalConfidence}
          onOpenMapping={() => setMappingOpen(true)}
        />
      </section>

      <RoleMappingModal
        proposal={causalProposal}
        open={mappingOpen}
        onConfirm={confirmMapping}
        onClose={() => setMappingOpen(false)}
      />
    </div>
  );
}
