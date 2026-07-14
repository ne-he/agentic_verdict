"use client";

import { useState } from "react";
import type {
  AnalysisResult,
  CausalConfidenceBreakdown,
  CausalRouteProposal,
  ToolCall,
  VerificationResult,
} from "@/lib/types";
import { artifactUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button, SectionLabel } from "@/components/ui";
import { CausalTab } from "@/components/causal/causal-tab";

export type TabKey = "summary" | "evidence" | "code" | "charts" | "verify" | "causal";

export const TABS: { key: TabKey; label: string }[] = [
  { key: "summary", label: "Executive Summary" },
  { key: "evidence", label: "Evidence" },
  { key: "code", label: "Code" },
  { key: "charts", label: "Charts" },
  { key: "verify", label: "Verification" },
  { key: "causal", label: "Causal" },
];

/** Render markdown ringan: paragraf + **bold** (tanpa lib eksternal). */
function MarkdownLite({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const parts = block.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p
            key={i}
            className="mb-4 text-[14px] leading-[1.75] text-[#bdbdbd] last:mb-0"
          >
            {parts.map((p, j) =>
              p.startsWith("**") && p.endsWith("**") ? (
                <strong key={j} className="font-mono text-accent">
                  {p.slice(2, -2)}
                </strong>
              ) : (
                <span key={j}>{p}</span>
              ),
            )}
          </p>
        );
      })}
    </>
  );
}

function CopyButton({ text, label = "copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      onClick={() => {
        navigator.clipboard?.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
    >
      {copied ? "copied" : label}
    </Button>
  );
}

function CodeBlock({ title, code }: { title: string; code: string }) {
  return (
    <div className="border border-line">
      <div className="flex items-center justify-between border-b border-line bg-panel px-[13px] py-2">
        <span className="font-mono text-[10.5px] text-faint">{title}</span>
        <CopyButton text={code} />
      </div>
      <div className="overflow-x-auto bg-bg-soft px-[15px] py-[13px]">
        {code.split("\n").map((line, i) => (
          <div key={i} className="flex gap-[15px] font-mono text-[12px] leading-[1.7]">
            <span className="w-[22px] flex-none select-none text-right text-[#3a3a3a]">
              {i + 1}
            </span>
            <span className="whitespace-pre text-[#bdbdbd]">{line || " "}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function WorkspaceTabs({
  active,
  onTab,
  result,
  verification,
  chartPaths,
  onRerun,
  causalProposal,
  causalConfidence,
  onOpenMapping,
}: {
  active: TabKey;
  onTab: (t: TabKey) => void;
  result: AnalysisResult | null;
  verification: VerificationResult | null;
  chartPaths: string[];
  onRerun?: () => void;
  causalProposal?: CausalRouteProposal | null;
  causalConfidence?: CausalConfidenceBreakdown | null;
  onOpenMapping?: () => void;
}) {
  const causalAlive = Boolean(result?.causal || causalProposal);
  return (
    <>
      <div className="flex gap-5 border-b border-line px-[22px] pt-3">
        {TABS.map((t) => {
          const isActive = t.key === active;
          return (
            <button
              key={t.key}
              onClick={() => onTab(t.key)}
              className={cn(
                "relative pb-[10px] text-[13px] transition-colors",
                isActive ? "text-ink" : "text-faint hover:text-muted",
              )}
            >
              {t.label}
              {t.key === "causal" && causalAlive && (
                <span className="ml-[6px] font-mono text-[9px] text-accent">●</span>
              )}
              {isActive && (
                <span className="absolute inset-x-0 -bottom-px h-[2px] bg-accent" />
              )}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-[22px]">
        {active === "summary" && <SummaryTab result={result} />}
        {active === "evidence" && <EvidenceTab result={result} verification={verification} />}
        {active === "code" && <CodeTab result={result} onRerun={onRerun} />}
        {active === "charts" && <ChartsTab chartPaths={chartPaths} />}
        {active === "verify" && <VerifyTab verification={verification} />}
        {active === "causal" && (
          <CausalTab
            causal={result?.causal ?? null}
            causalConfidence={result?.causal_confidence ?? causalConfidence ?? null}
            proposal={causalProposal ?? null}
            answerGrounded={result?.answer_grounded ?? true}
            onOpenMapping={onOpenMapping}
          />
        )}
      </div>
    </>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[12.5px] text-faint">{children}</div>
  );
}

function SummaryTab({ result }: { result: AnalysisResult | null }) {
  if (!result) return <Empty>Belum ada analisis. Ajukan pertanyaan untuk mulai.</Empty>;
  const c = result.confidence;
  return (
    <div className="max-w-[820px] animate-fadein">
      {c && (
        <div className="mb-6 grid grid-cols-3 border border-line">
          {[
            { label: "Confidence", value: `${Math.round(c.final * 100)}%`, sub: c.label },
            {
              label: "Verification",
              value: result.verification ? (result.verification.passed ? "PASS" : "FAIL") : "—",
              sub: result.verification ? `agreement ${result.verification.agreement.toFixed(2)}` : "no check",
            },
            { label: "Tool calls", value: String(result.tool_calls.length), sub: `${result.tokens} tok` },
          ].map((s, i) => (
            <div key={i} className={cn("p-4", i < 2 && "border-r border-line")}>
              <div className="mb-[11px] text-[10px] uppercase tracking-[0.1em] text-faint">
                {s.label}
              </div>
              <div className="font-mono text-[26px] font-semibold leading-none text-ink">
                {s.value}
              </div>
              <div className="mt-[9px] font-mono text-[11px] text-faint">{s.sub}</div>
            </div>
          ))}
        </div>
      )}
      <h2 className="mb-3 text-[15px] font-semibold tracking-[-0.02em]">Answer</h2>
      <MarkdownLite text={result.answer_markdown} />
    </div>
  );
}

function EvidenceTab({
  result,
  verification,
}: {
  result: AnalysisResult | null;
  verification: VerificationResult | null;
}) {
  if (!result) return <Empty>Belum ada bukti.</Empty>;
  const tools = result.tool_calls.filter((t) => t.output);
  return (
    <div className="flex max-w-[840px] flex-col gap-[26px] animate-fadein">
      <p className="m-0 font-mono text-[12.5px] text-faint">
        Setiap klaim tertaut ke query yang dieksekusi dan hasil mentahnya.
      </p>
      {verification && (
        <Evidence
          tag="VERIFY"
          claim="Angka kunci diverifikasi 2 metode"
          body={`Method A — ${verification.method_a}\nMethod B — ${verification.method_b}`}
          result={`agreement ${verification.agreement.toFixed(3)} · ${verification.passed ? "consistent" : "discrepancy"}`}
        />
      )}
      {tools.map((t: ToolCall, i) => (
        <Evidence
          key={i}
          tag={t.tool}
          claim={`Tool: ${t.tool}`}
          body={String(t.output).slice(0, 600)}
          result={t.error ? `error: ${t.error}` : "ok"}
        />
      ))}
      {!verification && tools.length === 0 && <Empty>Tidak ada jejak tool.</Empty>}
    </div>
  );
}

function Evidence({
  tag,
  claim,
  body,
  result,
}: {
  tag: string;
  claim: string;
  body: string;
  result: string;
}) {
  return (
    <div>
      <div className="mb-[10px] flex items-baseline gap-[11px]">
        <span className="flex-none font-mono text-[11px] text-accent">{tag}</span>
        <span className="text-[14px] font-semibold tracking-[-0.01em]">{claim}</span>
      </div>
      <div className="border-l-2 border-accent bg-bg-soft px-[15px] py-[11px]">
        <pre className="m-0 whitespace-pre-wrap font-mono text-[11.5px] leading-[1.6] text-muted">
          {body}
        </pre>
      </div>
      <div className="mt-[9px] flex items-center gap-3 pl-[15px]">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-faint">
          result
        </span>
        <span className="font-mono text-[13px] text-accent">{result}</span>
      </div>
    </div>
  );
}

function CodeTab({
  result,
  onRerun,
}: {
  result: AnalysisResult | null;
  onRerun?: () => void;
}) {
  if (!result || !result.code) return <Empty>Belum ada kode.</Empty>;
  return (
    <div className="flex max-w-[880px] flex-col gap-5 animate-fadein">
      <div className="flex items-center justify-between">
        <p className="m-0 font-mono text-[12.5px] text-faint">
          Kode persis yang dieksekusi di sandbox — reproducible, re-run → hasil sama.
        </p>
        {onRerun && (
          <Button variant="outline" onClick={onRerun}>
            ↻ re-run
          </Button>
        )}
      </div>
      <CodeBlock title={`analysis.py · sandbox · ${result.dataset_snapshot || "snapshot"}`} code={result.code} />
    </div>
  );
}

function ChartsTab({ chartPaths }: { chartPaths: string[] }) {
  if (chartPaths.length === 0)
    return <Empty>Tidak ada chart untuk analisis ini.</Empty>;
  return (
    <div
      className="grid max-w-[900px] gap-[22px] animate-fadein"
      style={{ gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))" }}
    >
      {chartPaths.map((p, i) => (
        <figure key={i} className="m-0 border border-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={artifactUrl(p)}
            alt={`Figure ${i + 1}`}
            className="block w-full bg-bg-soft"
          />
          <figcaption className="flex items-center justify-between border-t border-line px-[14px] py-2 font-mono text-[10.5px] text-faint">
            <span>
              <span className="text-muted">Figure {i + 1}.</span>{" "}
              {p.split(/[/\\]+/).pop()}
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

function VerifyTab({ verification }: { verification: VerificationResult | null }) {
  if (!verification)
    return (
      <Empty>
        Verifikasi tidak dijalankan untuk run ini (jawaban bukan angka kunci tunggal).
      </Empty>
    );
  const v = verification;
  return (
    <div className="max-w-[880px] animate-fadein">
      <div className="mb-5 flex flex-wrap items-baseline gap-4 font-mono">
        <p className="m-0 min-w-[240px] flex-1 text-[12px] leading-[1.6] text-faint">
          Tiap angka di-derive ulang oleh metode kedua. Kesepakatan menaikkan
          confidence; selisih menurunkannya dan ditahan dari ringkasan.
        </p>
        <div className="flex gap-4 text-[11.5px]">
          <span className="text-pass">{v.passed ? "1 consistent" : "0 consistent"}</span>
          <span className="text-fail">
            {v.contradictions.length} discrepancy
          </span>
        </div>
      </div>
      <div className="border border-line">
        <div className="p-[18px]">
          <div className="mb-[13px] flex items-center justify-between gap-[14px]">
            <span className="text-[13.5px] font-semibold tracking-[-0.01em]">
              Angka kunci jawaban
            </span>
            <span
              className={cn(
                "whitespace-nowrap font-mono text-[11px] font-semibold tracking-[0.04em]",
                v.passed ? "text-pass" : "text-fail",
              )}
            >
              {v.passed ? "CONSISTENT" : "DISCREPANCY"}
            </span>
          </div>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[18px]">
            <div>
              <SectionLabel className="mb-[5px] font-mono text-[9.5px]">
                Method A · agent
              </SectionLabel>
              <div className="font-mono text-[14px] text-ink">{v.method_a}</div>
            </div>
            <div className="text-center">
              <div className={cn("font-mono text-[13px]", v.passed ? "text-pass" : "text-fail")}>
                {v.agreement.toFixed(3)}
              </div>
              <div
                className={cn(
                  "mx-auto mt-[6px] h-px w-[54px]",
                  v.passed ? "bg-pass" : "bg-fail",
                )}
              />
            </div>
            <div className="text-right">
              <SectionLabel className="mb-[5px] font-mono text-[9.5px]">
                Method B · duckdb
              </SectionLabel>
              <div className="font-mono text-[14px] text-ink">{v.method_b}</div>
            </div>
          </div>
          {v.contradictions.length > 0 && (
            <div className="mt-[13px] border-l-2 border-fail py-[7px] pl-[13px] text-[12.5px] leading-[1.6] text-[#bdbdbd]">
              {v.contradictions.map((c, i) => (
                <div key={i}>{c}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
