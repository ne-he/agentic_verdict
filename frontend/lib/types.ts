/**
 * Tipe ini MIRROR dari backend/app/core/schemas.py (sumber kebenaran tunggal).
 * Kalau schema backend berubah → regenerate backend/.../export_schemas → samakan di sini.
 * JSON schema mentah ada di lib/schemas.json.
 */

export type StepStatus = "pending" | "running" | "done" | "error";
export type ConfidenceLabel = "HIGH" | "MEDIUM" | "LOW";
export type Intent = "descriptive" | "causal";
export type SSEEventType =
  | "plan"
  | "intent"
  | "step"
  | "tool"
  | "chart"
  | "verify"
  | "causal"
  | "confidence"
  | "final"
  | "error";

export interface AnalyzeRequest {
  question: string;
  dataset_id: string;
  session_id?: string | null;
  /** Mapping kolom kausal yang SUDAH dikonfirmasi user (D3). */
  causal_roles?: CausalRoles | null;
}

// ── Jalur kausal (mirror app/causal/schemas.py) ─────────────────────────────
export interface CausalRoles {
  unit_id?: string | null;
  treatment?: string | null;
  outcome: string;
  covariates?: string[];
  timestamp?: string | null;
  intervention_date?: string | null;
}

export type CausalMethod = "ab_test" | "observational" | "timeseries" | "descriptive";
export type AssumptionStatus = "pass" | "warn" | "fail";
export type RiskLevel = "low" | "medium" | "high";
export type CausalDecision =
  | "deploy"
  | "deploy_with_caution"
  | "do_not_ship"
  | "inconclusive";

export interface RouterDecision {
  method: CausalMethod;
  confidence: number;
  reasons: string[];
  assumptions_required: string[];
  diagnostics: Record<string, unknown>;
  allow_override: boolean;
}

export interface EffectEstimate {
  point: number;
  ci_low: number;
  ci_high: number;
  ci_level: number;
  relative_lift: number | null;
  p_value: number | null;
  is_significant: boolean | null;
}

export interface PowerAnalysis {
  observed_n_per_arm: number;
  mde_absolute: number | null;
  required_n_per_arm: number | null;
  days_needed: number | null;
  power: number;
}

export interface AssumptionCheck {
  name: string;
  status: AssumptionStatus;
  value: number | null;
  business_explanation: string;
  risk: RiskLevel;
}

export interface CausalVerdict {
  decision: CausalDecision;
  rationale: string;
  required_n: number | null;
}

export interface CausalResult {
  dataset_id: string;
  roles: CausalRoles;
  router_decision: RouterDecision;
  effect: EffectEstimate | null;
  power: PowerAnalysis | null;
  method_specific: Record<string, unknown>;
  refutations: unknown[];
  assumptions: AssumptionCheck[];
  verdict: CausalVerdict | null;
}

export interface CausalRouteProposal {
  roles: CausalRoles;
  needs_confirmation: boolean;
  router_decision: RouterDecision;
  instruction?: string;
}

export interface CausalConfidenceBreakdown {
  router_confidence: number;
  assumption_health: number;
  verification_agreement: number;
  tool_execution_success: number;
  final: number;
  label: ConfidenceLabel;
}

export interface IntentDecision {
  intent: Intent;
  signals: string[];
  note: string;
}

export interface PlanStep {
  id: number;
  description: string;
  tool: string;
  status: StepStatus;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: string | null;
  error: string | null;
  duration_ms: number;
}

export interface VerificationResult {
  method_a: string;
  method_b: string;
  agreement: number;
  contradictions: string[];
  passed: boolean;
}

export interface ConfidenceBreakdown {
  answer_consistency: number;
  verification_agreement: number;
  tool_execution_success: number;
  data_coverage: number;
  final: number;
  label: ConfidenceLabel;
}

export interface AnalysisResult {
  run_id: string;
  answer_markdown: string;
  code: string;
  dataset_id: string;
  dataset_snapshot: string;
  chart_paths: string[];
  verification: VerificationResult | null;
  confidence: ConfidenceBreakdown | null;
  tool_calls: ToolCall[];
  tokens: number;
  cost_usd: number;
  duration_ms: number;
  intent: Intent;
  causal: CausalResult | null;
  causal_confidence: CausalConfidenceBreakdown | null;
  answer_grounded: boolean;
}

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

export interface Scorecard {
  run_id: string;
  question_id: string;
  correctness: number;
  cost_usd: number;
  tool_calls: number;
  time_to_insight: number;
  hallucination_flag: boolean;
  verification_accuracy: number;
}

export interface BatchSummary {
  total: number;
  avg_correctness: number;
  total_cost_usd: number;
  hallucination_rate: number;
  avg_tool_calls: number;
  avg_time_to_insight: number;
  run_ids: string[];
}

export interface RunRecord {
  run_id: string;
  dataset_id: string;
  dataset_snapshot: string;
  question: string;
  answer_markdown: string;
  code: string;
  tokens: number;
  cost_usd: number;
  duration_ms: number;
  chart_paths: string[];
  created_at: string | null;
}

export interface DatasetInfo {
  dataset_id: string;
  file: string;
  encoding: string;
}

export interface EvalDashboard {
  summary: BatchSummary;
  recent: Scorecard[];
}
