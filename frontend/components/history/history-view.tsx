"use client";

import { useEffect, useMemo, useState } from "react";
import type { RunRecord } from "@/lib/types";
import { listRuns } from "@/lib/api";
import { cn, fmtUsd, terminationColorClass, terminationLabel } from "@/lib/utils";

export function HistoryView() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns(100)
      .then(setRuns)
      .catch((e) => setError(String(e)));
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return runs;
    return runs.filter(
      (r) =>
        r.question.toLowerCase().includes(q) ||
        r.dataset_id.toLowerCase().includes(q) ||
        r.run_id.toLowerCase().includes(q),
    );
  }, [runs, filter]);

  return (
    <div className="flex-1 overflow-y-auto px-9 py-[30px]">
      <div className="mx-auto max-w-[1060px]">
        <div className="mb-[6px] flex flex-wrap items-end justify-between gap-3">
          <h1 className="m-0 text-[19px] font-semibold tracking-[-0.02em]">Case docket</h1>
          <div className="flex items-stretch border border-line2 bg-bg-soft">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter runs…"
              className="w-[200px] bg-transparent px-[11px] py-[7px] font-mono text-[12px] text-ink outline-none"
            />
            <span className="flex items-center border-l border-line2 bg-panel px-[11px] font-mono text-muted">
              ⌕
            </span>
          </div>
        </div>
        <p className="mb-[22px] text-[13px] leading-[1.6] text-faint">
          Tiap analisis tersimpan dengan dataset, computed confidence, kode-nya, dan alasan
          run itu berhenti. Run terbaru muncul paling atas.
        </p>

        {error && (
          <div className="mb-4 font-mono text-[12.5px] text-fail">
            Gagal memuat — {error}. Pastikan backend jalan di :8000.
          </div>
        )}

        <div className="border border-line">
          <div className="grid grid-cols-[110px_1fr_110px_90px_150px_130px] gap-2 border-b border-line bg-panel px-[18px] py-[9px] font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
            <span>Run</span>
            <span>Question</span>
            <span>Dataset</span>
            <span>Cost</span>
            <span>Terminasi</span>
            <span className="text-right">Date</span>
          </div>
          {filtered.length === 0 && (
            <div className="px-[18px] py-6 font-mono text-[12px] text-faint">
              {runs.length === 0
                ? "Belum ada run tersimpan. Jalankan analisis di tab Analyze."
                : "Tidak ada yang cocok dengan filter."}
            </div>
          )}
          {filtered.map((r) => (
            <div
              key={r.run_id}
              className="grid grid-cols-[110px_1fr_110px_90px_150px_130px] items-center gap-2 border-b border-line/60 px-[18px] py-[11px] last:border-b-0 hover:bg-panel/40"
            >
              <span className="truncate font-mono text-[11px] text-accent">
                {r.run_id.replace("run_", "")}
              </span>
              <span className="truncate pr-4 text-[13px] text-ink">{r.question}</span>
              <span className="text-[12px] text-muted">{r.dataset_id}</span>
              <span className="font-mono text-[11.5px] text-muted">{fmtUsd(r.cost_usd)}</span>
              <span
                className={cn(
                  "truncate font-mono text-[11px]",
                  terminationColorClass(r.termination_reason),
                )}
              >
                {terminationLabel(r.termination_reason)}
              </span>
              <span className={cn("text-right font-mono text-[11px] text-faint")}>
                {r.created_at ? new Date(r.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
