/**
 * Client API ANALYST: REST + SSE streaming.
 *
 * /analyze memakai POST + text/event-stream → EventSource (GET-only) tak cukup,
 * jadi kita pakai fetch + ReadableStream reader dan parse frame SSE manual.
 */

import type {
  CausalRoles,
  DatasetInfo,
  EvalDashboard,
  RunRecord,
  SSEEvent,
  SSEEventType,
} from "./types";

// Base URL backend dibaca dari env (jangan hardcode). Set di Vercel:
//   NEXT_PUBLIC_API_URL=https://analyst-backend.onrender.com
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export function listDatasets(): Promise<DatasetInfo[]> {
  return getJSON<DatasetInfo[]>("/datasets");
}

export function getRun(runId: string): Promise<RunRecord> {
  return getJSON<RunRecord>(`/run/${encodeURIComponent(runId)}`);
}

export function listRuns(limit = 50): Promise<RunRecord[]> {
  return getJSON<RunRecord[]>(`/runs?limit=${limit}`);
}

export function getEvalDashboard(limit = 100): Promise<EvalDashboard> {
  return getJSON<EvalDashboard>(`/eval/dashboard?limit=${limit}`);
}

/**
 * URL gambar chart dari path absolut yang dikembalikan backend.
 * chart_paths berbentuk ".../artifacts/<subdir>/<file>.png" → ambil 2 segmen terakhir.
 */
export function artifactUrl(chartPath: string): string {
  const parts = chartPath.split(/[/\\]+/).filter(Boolean);
  const subdir = parts[parts.length - 2] ?? "";
  const file = parts[parts.length - 1] ?? "";
  return `${API_BASE}/artifacts/${encodeURIComponent(subdir)}/${encodeURIComponent(
    file,
  )}`;
}

/** Parse satu blok frame SSE ("event: x\ndata: {...}") → SSEEvent. */
function parseFrame(frame: string): SSEEvent | null {
  let type: SSEEventType | null = null;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim() as SSEEventType;
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!type) return null;
  const raw = dataLines.join("\n");
  let data: Record<string, unknown> = {};
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    data = { raw };
  }
  return { type, data };
}

/**
 * Stream analisis: panggil onEvent untuk tiap SSEEvent saat tiba.
 * Mengembalikan Promise yang resolve saat stream selesai.
 * `signal` opsional untuk membatalkan (AbortController).
 */
export async function streamAnalyze(
  body: {
    question: string;
    dataset_id: string;
    session_id?: string | null;
    causal_roles?: CausalRoles | null;
  },
  onEvent: (ev: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw new Error(`/analyze → HTTP ${res.status} ${detail}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frame SSE dipisah baris kosong ganda.
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseFrame(frame);
      if (ev) onEvent(ev);
    }
  }
  // Sisa buffer terakhir (kalau ada frame tanpa newline ganda penutup).
  const tail = parseFrame(buffer);
  if (tail) onEvent(tail);
}
