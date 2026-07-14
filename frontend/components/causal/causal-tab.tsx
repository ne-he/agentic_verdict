"use client";

/**
 * Tab Causal — render CausalResult dari backend (BLUEPRINT M2).
 * SEMUA angka di sini berasal dari engine deterministik (P1); komponen ini
 * murni presentasi. Styling fungsional konsisten tema — polish design menyusul.
 */

import type {
  AssumptionCheck,
  CausalConfidenceBreakdown,
  CausalResult,
  CausalRouteProposal,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const statusColor: Record<AssumptionCheck["status"], string> = {
  pass: "text-pass",
  warn: "text-warn",
  fail: "text-fail",
};

const decisionMeta: Record<string, { label: string; cls: string }> = {
  deploy: { label: "DEPLOY", cls: "text-pass border-pass" },
  deploy_with_caution: { label: "DEPLOY WITH CAUTION", cls: "text-warn border-warn" },
  do_not_ship: { label: "DO NOT SHIP", cls: "text-fail border-fail" },
  inconclusive: { label: "INCONCLUSIVE", cls: "text-faint border-line2" },
};

const fmt = (x: number | null | undefined, digits = 4): string =>
  x === null || x === undefined ? "—" : Number(x).toPrecision(digits);

export function RouterDecisionCard({
  decision,
  needsConfirmation,
  onOpenMapping,
}: {
  decision: CausalResult["router_decision"];
  needsConfirmation?: boolean;
  onOpenMapping?: () => void;
}) {
  return (
    <div className="border border-line">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-panel px-4 py-[10px]">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
            Method router
          </span>
          <span className="font-mono text-[15px] font-semibold text-accent">
            {decision.method}
          </span>
          <span className="font-mono text-[11px] text-faint">
            confidence {decision.confidence.toFixed(2)}
          </span>
        </div>
        {needsConfirmation && onOpenMapping && (
          <button
            onClick={onOpenMapping}
            className="border border-accent px-3 py-[6px] font-mono text-[11px] text-accent hover:bg-accent hover:text-bg"
          >
            konfirmasi mapping →
          </button>
        )}
      </div>
      <div className="grid gap-0 sm:grid-cols-2">
        <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
          <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-faint">
            Kenapa metode ini
          </div>
          {decision.reasons.map((r, i) => (
            <div key={i} className="mb-[6px] text-[12.5px] leading-[1.6] text-[#bdbdbd]">
              · {r}
            </div>
          ))}
        </div>
        <div className="p-4">
          <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-faint">
            Asumsi yang ditanggung
          </div>
          {decision.assumptions_required.map((a, i) => (
            <div key={i} className="mb-[6px] text-[12.5px] leading-[1.6] text-[#bdbdbd]">
              · {a}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function EffectSummary({ result }: { result: CausalResult }) {
  const e = result.effect;
  const p = result.power;
  const v = result.verdict;
  const ms = result.method_specific ?? {};
  if (!e)
    return (
      <div className="border border-line p-4 font-mono text-[12px] text-faint">
        Tidak ada estimasi efek (metode: {result.router_decision.method}).
      </div>
    );
  const dm = v ? decisionMeta[v.decision] ?? decisionMeta.inconclusive : null;
  return (
    <div className="border border-line">
      <div className="grid sm:grid-cols-3">
        <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
          <div className="mb-[9px] text-[10px] uppercase tracking-[0.12em] text-faint">
            Efek (absolut)
          </div>
          <div className="font-mono text-[26px] font-semibold leading-none text-ink">
            {e.point >= 0 ? "+" : ""}
            {fmt(e.point)}
          </div>
          <div className="mt-[8px] font-mono text-[11px] text-faint">
            CI {Math.round(e.ci_level * 100)}%: [{fmt(e.ci_low)}, {fmt(e.ci_high)}]
          </div>
        </div>
        <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
          <div className="mb-[9px] text-[10px] uppercase tracking-[0.12em] text-faint">
            Signifikansi
          </div>
          <div
            className={cn(
              "font-mono text-[26px] font-semibold leading-none",
              e.is_significant ? "text-pass" : "text-warn",
            )}
          >
            {e.is_significant === null ? "—" : e.is_significant ? "SIG" : "NOT SIG"}
          </div>
          <div className="mt-[8px] font-mono text-[11px] text-faint">
            p = {e.p_value === null ? "—" : e.p_value.toExponential(2)}
            {e.relative_lift !== null && ` · lift ${(e.relative_lift * 100).toFixed(2)}%`}
          </div>
        </div>
        <div className="p-4">
          <div className="mb-[9px] text-[10px] uppercase tracking-[0.12em] text-faint">
            Power
          </div>
          <div className="font-mono text-[26px] font-semibold leading-none text-ink">
            {p ? p.observed_n_per_arm.toLocaleString() : "—"}
          </div>
          <div className="mt-[8px] font-mono text-[11px] text-faint">
            n/arm · MDE {p ? fmt(p.mde_absolute, 3) : "—"}
            {typeof ms["cuped_variance_reduction"] === "number" &&
              ` · CUPED −${((ms["cuped_variance_reduction"] as number) * 100).toFixed(1)}% var`}
          </div>
        </div>
      </div>
      {v && dm && (
        <div className={cn("flex flex-wrap items-baseline gap-3 border-t px-4 py-3", dm.cls, "border-t-line")}>
          <span className={cn("border px-2 py-[3px] font-mono text-[11px] font-semibold tracking-[0.06em]", dm.cls)}>
            {dm.label}
          </span>
          <span className="min-w-0 flex-1 text-[12.5px] leading-[1.6] text-[#bdbdbd]">
            {v.rationale}
          </span>
        </div>
      )}
    </div>
  );
}

export function AssumptionBadges({ checks }: { checks: AssumptionCheck[] }) {
  if (!checks.length)
    return (
      <div className="font-mono text-[12px] text-faint">
        Belum ada assumption check untuk metode ini.
      </div>
    );
  return (
    <div className="flex flex-col gap-[10px]">
      {checks.map((a, i) => (
        <div key={i} className="border border-line">
          <div className="flex items-center justify-between border-b border-line bg-panel px-[13px] py-[7px]">
            <span className="font-mono text-[11px] text-muted">{a.name}</span>
            <span className={cn("font-mono text-[11px] font-semibold uppercase tracking-[0.08em]", statusColor[a.status])}>
              {a.status} · risk {a.risk}
            </span>
          </div>
          <div className="px-[13px] py-[10px] text-[12.5px] leading-[1.65] text-[#bdbdbd]">
            {a.business_explanation}
          </div>
        </div>
      ))}
    </div>
  );
}

export function CausalConfidenceCard({ c }: { c: CausalConfidenceBreakdown }) {
  const rows: { label: string; weight: string; value: number }[] = [
    { label: "Router confidence", weight: "0.30", value: c.router_confidence },
    { label: "Assumption health", weight: "0.30", value: c.assumption_health },
    { label: "Verification agreement", weight: "0.25", value: c.verification_agreement },
    { label: "Tool execution success", weight: "0.15", value: c.tool_execution_success },
  ];
  return (
    <div className="border border-line">
      <div className="flex items-baseline justify-between border-b border-line bg-panel px-4 py-[10px]">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
          Causal confidence (computed)
        </span>
        <span
          className={cn(
            "font-mono text-[13px] font-semibold",
            c.label === "HIGH" ? "text-pass" : c.label === "MEDIUM" ? "text-warn" : "text-fail",
          )}
        >
          {c.label} · {Math.round(c.final * 100)}%
        </span>
      </div>
      <div className="p-4">
        {rows.map((r, i) => (
          <div key={i} className="mb-[9px] last:mb-0">
            <div className="mb-[4px] flex items-baseline justify-between font-mono text-[11px]">
              <span className="text-muted">
                {r.label} <span className="text-[#4a4a4a]">× {r.weight}</span>
              </span>
              <span className="text-ink">{r.value.toFixed(2)}</span>
            </div>
            <div className="h-[3px] bg-line">
              <div className="h-full bg-accent" style={{ width: `${r.value * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CausalTab({
  causal,
  causalConfidence,
  proposal,
  answerGrounded,
  onOpenMapping,
}: {
  causal: CausalResult | null;
  causalConfidence: CausalConfidenceBreakdown | null;
  proposal: CausalRouteProposal | null;
  answerGrounded: boolean;
  onOpenMapping?: () => void;
}) {
  if (!causal && !proposal)
    return (
      <div className="font-mono text-[12.5px] text-faint">
        Belum ada analisis kausal. Ajukan pertanyaan sebab-akibat (mis. “apakah
        kampanye ini menaikkan konversi?”).
      </div>
    );

  return (
    <div className="flex max-w-[880px] flex-col gap-5 animate-fadein">
      {!causal && proposal && (
        <div className="border border-warn/50 bg-warn/5 px-4 py-3 text-[12.5px] leading-[1.6] text-[#bdbdbd]">
          Router sudah mengusulkan mapping kolom — analisis menunggu{" "}
          <span className="text-warn">konfirmasi mapping</span> darimu (guardrail:
          analisis kausal tidak pernah jalan tanpa konfirmasi manusia).
        </div>
      )}
      {!answerGrounded && (
        <div className="border border-fail/50 bg-fail/5 px-4 py-3 font-mono text-[12px] text-fail">
          narasi LLM gagal number-grounding → jawaban diganti template deterministik
        </div>
      )}
      <RouterDecisionCard
        decision={(causal ?? proposal)!.router_decision}
        needsConfirmation={!causal && proposal?.needs_confirmation}
        onOpenMapping={onOpenMapping}
      />
      {causal && <EffectSummary result={causal} />}
      {causal && (
        <div className="grid items-start gap-5 lg:grid-cols-2">
          <div>
            <div className="mb-[10px] text-[10px] uppercase tracking-[0.14em] text-faint">
              Assumption checks
            </div>
            <AssumptionBadges checks={causal.assumptions} />
          </div>
          {causalConfidence && <CausalConfidenceCard c={causalConfidence} />}
        </div>
      )}
    </div>
  );
}
