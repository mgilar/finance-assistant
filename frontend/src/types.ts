// Mirror of backend/app/schemas.py — the API contract. Keep the two in sync.

export interface Lineage {
  sources: string[];
  rows_used: number;
  credit_notes_included: number;
  fx_rates_to_eur: Record<string, number>;
  notes: string[];
}

export interface CurrencyBreakdown {
  currency: string;
  invoice_count: number;
  total_native: number;
  eur_approx: number;
}

export interface StatusBreakdown {
  vendor_status: string;
  vendor_count: number;
  invoice_count: number;
  eur_approx: number;
}

export interface SummaryResponse {
  request_id: string;
  invoice_count: number;
  period_start: string;
  period_end: string;
  total_eur_approx: number;
  by_currency: CurrencyBreakdown[];
  by_vendor_status: StatusBreakdown[];
  lineage: Lineage;
}

export interface PolicyCitation {
  id: string;
  title: string;
  text: string;
}

export type Row = Record<string, string | number | boolean | null | Record<string, number>>;

export interface ToolCallEvidence {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  error: string | null;
  filters_applied: string;
  rows_scanned: number;
  result: Row[];
  rows: Row[];
}

export type AnswerStatus = "answered" | "partial" | "cannot_answer";
export type Source = "data" | "policy";

export interface AskResponse {
  request_id: string;
  status: AnswerStatus;
  answer: string;
  sources_used: Source[];
  policy_citations: PolicyCitation[];
  data_evidence: ToolCallEvidence[];
  routing_reason: string;
  caveats: string[];
  gaps: string[];
  unverified_figures: string[];
  mode: "llm" | "stub";
  model: string | null;
  policy_version: string;
  data_sources: string[];
}

export interface HealthResponse {
  request_id: string;
  status: "ok";
  mode: "llm" | "stub";
  model: string | null;
}

// Server error codes, plus two the client produces itself.
export type ErrorCode =
  | "invalid_request" | "not_found" | "llm_unavailable" | "internal_error"
  | "network_error" | "bad_response";

export interface ApiError {
  code: ErrorCode;
  message: string;
  retryable: boolean;
  request_id: string | null;
}
