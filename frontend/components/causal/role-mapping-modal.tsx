"use client";

/**
 * RoleMappingModal (BLUEPRINT D3) — gate manusia sebelum analisis kausal.
 * Agent MENGUSULKAN mapping; user koreksi & konfirmasi; analisis di-re-run
 * dengan causal_roles terkonfirmasi. Fungsional dulu — polish design menyusul.
 */

import { useEffect, useState } from "react";
import type { CausalRoles, CausalRouteProposal } from "@/lib/types";

function Field({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <div className="mb-[5px] flex items-baseline justify-between">
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted">
          {label}
        </span>
        <span className="font-mono text-[10px] text-faint">{hint}</span>
      </div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-line2 bg-bg-soft px-[10px] py-[8px] font-mono text-[13px] text-ink outline-none focus:border-accent"
      />
    </label>
  );
}

export function RoleMappingModal({
  proposal,
  open,
  onConfirm,
  onClose,
}: {
  proposal: CausalRouteProposal | null;
  open: boolean;
  onConfirm: (roles: CausalRoles) => void;
  onClose: () => void;
}) {
  const [treatment, setTreatment] = useState("");
  const [outcome, setOutcome] = useState("");
  const [covariates, setCovariates] = useState("");

  useEffect(() => {
    if (proposal) {
      setTreatment(proposal.roles.treatment ?? "");
      setOutcome(proposal.roles.outcome ?? "");
      setCovariates((proposal.roles.covariates ?? []).join(", "));
    }
  }, [proposal]);

  if (!open || !proposal) return null;

  const submit = () => {
    if (!outcome.trim()) return;
    onConfirm({
      treatment: treatment.trim() || null,
      outcome: outcome.trim(),
      covariates: covariates
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-[520px] border border-line2 bg-bg">
        <div className="flex items-center justify-between border-b border-line bg-panel px-4 py-3">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent">
            Konfirmasi mapping kolom
          </span>
          <button
            onClick={onClose}
            className="font-mono text-[13px] text-faint hover:text-ink"
            title="tutup"
          >
            ✕
          </button>
        </div>

        <div className="flex flex-col gap-4 p-4">
          <p className="m-0 text-[12.5px] leading-[1.65] text-[#bdbdbd]">
            Agent mengusulkan mapping di bawah (metode:{" "}
            <span className="font-mono text-accent">
              {proposal.router_decision.method}
            </span>
            ). Analisis kausal <span className="text-warn">tidak akan jalan</span>{" "}
            sebelum kamu konfirmasi — koreksi kalau usulannya salah.
          </p>
          <Field
            label="Treatment"
            hint="kolom grup/perlakuan · 2 arm"
            value={treatment}
            onChange={setTreatment}
          />
          <Field
            label="Outcome"
            hint="metrik hasil (wajib)"
            value={outcome}
            onChange={setOutcome}
          />
          <Field
            label="Covariates"
            hint="pisahkan dengan koma"
            value={covariates}
            onChange={setCovariates}
          />
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-line px-4 py-3">
          <button
            onClick={onClose}
            className="border border-line2 px-4 py-[8px] font-mono text-[12px] text-muted hover:text-ink"
          >
            batal
          </button>
          <button
            onClick={submit}
            disabled={!outcome.trim()}
            className="border border-accent bg-accent px-4 py-[8px] font-mono text-[12px] font-semibold text-bg disabled:opacity-40"
          >
            konfirmasi & jalankan analisis →
          </button>
        </div>
      </div>
    </div>
  );
}
