"use client";

import { useEffect, useState } from "react";
import type { EvalDashboard, Scorecard } from "@/lib/types";
import { getEvalDashboard } from "@/lib/api";
import { cn, fmtUsd, pct } from "@/lib/utils";

/** Kategorikan satu scorecard jadi bucket failure dashboard. */
function bucketOf(s: Scorecard): "correct" | "flagged_low" | "verif_fail" | "halluc" {
  if (s.hallucination_flag) return "halluc";
  if (s.correctness >= 0.5) return "correct";
  // salah & tidak di-flag halusinasi → kalau verification menangkap (accuracy tinggi) = verif_fail bucket
  if (s.verification_accuracy >= 0.5) return "verif_fail";
  return "flagged_low";
}

const BUCKETS = [
  { key: "correct", label: "Correct", color: "bg-pass", text: "text-pass" },
  { key: "flagged_low", label: "Incorrect (flagged low)", color: "bg-warn", text: "text-warn" },
  { key: "verif_fail", label: "Verification caught", color: "bg-[#d2734e]", text: "text-[#d2734e]" },
  { key: "halluc", label: "Hallucination (uncaught)", color: "bg-fail", text: "text-fail" },
] as const;

export function EvalView() {
  const [data, setData] = useState<EvalDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalDashboard(100)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error)
    return (
      <div className="p-9 font-mono text-[12.5px] text-fail">
        Gagal memuat dashboard — {error}
        <div className="mt-2 text-faint">Pastikan backend jalan di :8000.</div>
      </div>
    );
  if (!data) return <div className="p-9 font-mono text-[12.5px] text-faint">memuat…</div>;

  const s = data.summary;
  const counts = { correct: 0, flagged_low: 0, verif_fail: 0, halluc: 0 };
  for (const card of data.recent) counts[bucketOf(card)] += 1;
  const total = data.recent.length || 1;
  const verifyCatch =
    data.recent.length > 0
      ? data.recent.reduce((a, c) => a + c.verification_accuracy, 0) / data.recent.length
      : 0;

  const stats = [
    { value: pct(s.avg_correctness), label: "Correctness", sub: `${data.recent.length} run dinilai`, color: "text-pass" },
    { value: pct(s.hallucination_rate), label: "Hallucination rate", sub: `${counts.halluc} uncaught`, color: counts.halluc > 0 ? "text-fail" : "text-pass" },
    { value: pct(verifyCatch), label: "Verify catch rate", sub: "wrong answers flagged", color: "text-[#6b9bd2]" },
    { value: fmtUsd(s.total_cost_usd / total), label: "Avg cost / run", sub: `total ${fmtUsd(s.total_cost_usd)}`, color: "text-ink" },
  ];

  return (
    <div className="flex-1 overflow-y-auto px-9 py-[30px]">
      <div className="mx-auto max-w-[1100px]">
        <h1 className="mb-[6px] text-[19px] font-semibold tracking-[-0.02em]">
          Reliability dashboard
        </h1>
        <p className="mb-6 text-[13px] leading-[1.6] text-faint">
          Dinilai terhadap golden set. Tujuannya bukan 100% benar — tapi tahu
          persis kapan agent salah.
        </p>

        <div className="mb-[22px] grid grid-cols-2 border border-line md:grid-cols-4">
          {stats.map((st, i) => (
            <div
              key={i}
              className={cn(
                "p-[18px]",
                i < stats.length - 1 && "md:border-r",
                "border-line",
              )}
            >
              <div className={cn("font-mono text-[28px] font-semibold leading-none", st.color)}>
                {st.value}
              </div>
              <div className="mt-[10px] text-[11px] text-muted">{st.label}</div>
              <div className="mt-1 font-mono text-[10.5px] text-faint">{st.sub}</div>
            </div>
          ))}
        </div>

        <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
          <div className="border border-line p-[18px]">
            <div className="mb-4 text-[12.5px] font-semibold tracking-[-0.01em]">
              Last {data.recent.length} runs
            </div>
            <div className="mb-[18px] flex h-2">
              {BUCKETS.map((b) => {
                const w = (counts[b.key] / total) * 100;
                return w > 0 ? (
                  <div key={b.key} className={cn(b.color)} style={{ width: `${w}%` }} />
                ) : null;
              })}
            </div>
            <div className="flex flex-col gap-[10px]">
              {BUCKETS.map((b) => (
                <div key={b.key} className="flex items-center justify-between">
                  <span className="flex items-center gap-[10px] text-[12.5px] text-[#bdbdbd]">
                    <span className={cn("h-[10px] w-[10px]", b.color)} />
                    {b.label}
                  </span>
                  <span className="font-mono text-[12.5px] text-ink">{counts[b.key]}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-line p-[18px]">
            <div className="mb-[18px] text-[12.5px] font-semibold tracking-[-0.01em]">
              Run terbaru
            </div>
            {data.recent.length === 0 && (
              <div className="font-mono text-[12px] text-faint">
                Belum ada scorecard. Jalankan batch eval:
                <br />
                <span className="text-muted">python -m app.eval.run_batch</span>
              </div>
            )}
            <div className="flex flex-col gap-3">
              {data.recent.slice(0, 8).map((c) => (
                <div key={c.run_id} className="flex items-center justify-between gap-3">
                  <span className="truncate font-mono text-[11px] text-accent">
                    {c.question_id || c.run_id}
                  </span>
                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className={cn(c.correctness >= 0.5 ? "text-pass" : "text-fail")}>
                      {pct(c.correctness)}
                    </span>
                    {c.hallucination_flag && <span className="text-fail">halluc</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
