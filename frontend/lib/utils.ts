import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Gabung className kondisional (pola shadcn). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format angka jadi ringkas dengan pemisah ribuan. */
export function fmtNum(n: number, digits = 2): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

/** Format USD kecil (biaya per run). */
export function fmtUsd(n: number): string {
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}

/** Persen 0..1 → "93%". */
export function pct(n: number, digits = 0): string {
  return `${(n * 100).toFixed(digits)}%`;
}

/** Warna teks untuk label confidence. */
export function confColorClass(label?: string | null): string {
  if (label === "HIGH") return "text-pass";
  if (label === "MEDIUM") return "text-warn";
  if (label === "LOW") return "text-fail";
  return "text-muted";
}

/**
 * Alasan terminasi run agent (aturan produksi #3).
 * Mirror dari backend/app/agent/termination.py, kalau vocabulary di sana berubah,
 * ubah di sini juga.
 */
const TERMINATION_LABEL: Record<string, string> = {
  completed: "Selesai normal",
  step_budget: "Berhenti: batas langkah",
  token_budget: "Berhenti: budget token",
  timeout: "Berhenti: batas waktu",
  tool_error: "Berhenti: tool gagal",
  cancelled: "Dibatalkan",
  crashed: "Proses mati di tengah",
};

export function terminationLabel(reason?: string | null): string {
  if (!reason) return "-";
  return TERMINATION_LABEL[reason] ?? reason;
}

/** True kalau alasan berhenti menandakan jawaban kemungkinan belum tuntas. */
export function terminationIsIncomplete(reason?: string | null): boolean {
  return Boolean(reason) && reason !== "completed";
}

export function terminationColorClass(reason?: string | null): string {
  if (!reason || reason === "completed") return "text-pass";
  if (reason === "cancelled") return "text-muted";
  if (reason === "tool_error" || reason === "crashed") return "text-fail";
  return "text-warn";
}
