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
