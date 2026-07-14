"use client";

import type { StepStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SectionLabel } from "@/components/ui";

export interface TraceNode {
  label: string;
  tool: string;
  status: StepStatus;
}

const TOOL_LABEL: Record<string, string> = {
  planner: "Planner",
  inspect_schema: "Inspect Schema",
  write_and_execute: "Compute",
  make_chart: "Chart",
  verify: "Self-Verify",
  answer: "Answer",
};

export function toolLabel(tool: string): string {
  return TOOL_LABEL[tool] ?? tool;
}

function statusWord(s: StepStatus): { word: string; color: string } {
  switch (s) {
    case "running":
      return { word: "running", color: "text-accent" };
    case "done":
      return { word: "ok", color: "text-pass" };
    case "error":
      return { word: "error", color: "text-fail" };
    default:
      return { word: "pending", color: "text-faint" };
  }
}

export function ExecutionTrace({ nodes }: { nodes: TraceNode[] }) {
  if (nodes.length === 0) return null;
  return (
    <div className="border-b border-line px-[22px] pb-0 pt-[13px]">
      <SectionLabel className="mb-[10px]">Execution trace</SectionLabel>
      <div className="flex items-stretch overflow-x-auto pb-3">
        {nodes.map((node, i) => {
          const st = statusWord(node.status);
          return (
            <div key={i} className="flex flex-none items-center">
              <div
                className={cn(
                  "min-w-[140px] border px-[14px] py-[11px]",
                  node.status === "running"
                    ? "border-accent"
                    : "border-line",
                )}
              >
                <div className="whitespace-nowrap text-[12.5px] font-medium tracking-[-0.01em] text-ink">
                  {node.label}
                </div>
                <div className="mt-[5px] flex items-center gap-[9px] font-mono text-[10px]">
                  <span className={st.color}>{st.word}</span>
                  <span className="text-[#3a3a3a]">{node.tool}</span>
                </div>
              </div>
              {i < nodes.length - 1 && (
                <div className="h-px w-[18px] flex-none bg-line" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
