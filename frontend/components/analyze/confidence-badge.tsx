"use client";

import { useState } from "react";
import type { ConfidenceBreakdown } from "@/lib/types";
import { cn } from "@/lib/utils";

const WEIGHTS: Record<keyof Omit<ConfidenceBreakdown, "final" | "label">, number> = {
  answer_consistency: 0.4,
  verification_agreement: 0.3,
  tool_execution_success: 0.2,
  data_coverage: 0.1,
};

const ROW_LABELS: Record<string, string> = {
  answer_consistency: "Answer consistency",
  verification_agreement: "Verification agreement",
  tool_execution_success: "Tool execution success",
  data_coverage: "Data coverage",
};

function colorFor(label?: string) {
  if (label === "HIGH") return "text-pass";
  if (label === "MEDIUM") return "text-warn";
  return "text-fail";
}

export function ConfidenceBadge({ c }: { c: ConfidenceBreakdown | null }) {
  const [open, setOpen] = useState(true);
  if (!c) {
    return (
      <div className="w-[296px] border border-line bg-bg-soft px-[15px] py-[11px]">
        <span className="font-mono text-[11px] text-faint">
          confidence — menunggu hasil
        </span>
      </div>
    );
  }
  const color = colorFor(c.label);
  const rows = (Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).map((k) => ({
    label: ROW_LABELS[k],
    raw: c[k] as number,
    weight: WEIGHTS[k],
    contrib: (c[k] as number) * WEIGHTS[k],
  }));

  return (
    <div className="relative w-[296px] flex-none">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between border border-line2 bg-bg-soft px-[15px] py-[11px] text-left hover:border-accent"
      >
        <div className="flex items-center gap-[10px]">
          <span className="text-[10px] uppercase tracking-[0.12em] text-faint">
            Confidence
          </span>
          <span className={cn("font-mono text-[12px] font-semibold tracking-[0.08em]", color)}>
            {c.label}
          </span>
        </div>
        <span className={cn("font-mono text-[18px] font-semibold", color)}>
          {Math.round(c.final * 100)}%
        </span>
      </button>
      {open && (
        <div className="absolute inset-x-0 top-[46px] z-20 border border-line2 bg-panel px-[15px] py-[13px]">
          <div className="mb-[11px] font-mono text-[10px] tracking-[0.02em] text-faint">
            COMPUTED — weighted signal model
          </div>
          <table className="w-full border-collapse font-mono text-[11.5px]">
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className="py-[3px] text-muted">{r.label}</td>
                  <td className="py-[3px] text-right text-faint">
                    {r.raw.toFixed(2)}×{r.weight}
                  </td>
                  <td className="py-[3px] pl-[14px] text-right text-ink">
                    {r.contrib.toFixed(3)}
                  </td>
                </tr>
              ))}
              <tr>
                <td colSpan={3} className="border-t border-line2 pt-[2px]" />
              </tr>
              <tr>
                <td className={cn("pt-[5px] font-semibold tracking-[0.04em]", "text-accent")}>
                  FINAL CONFIDENCE
                </td>
                <td />
                <td className="pt-[5px] text-right font-semibold text-accent">
                  {Math.round(c.final * 100)}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
