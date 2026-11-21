// The only place that talks HTTP. Every outcome becomes a typed Result: components never
// see a raw exception, and every failure carries a code, a message and `retryable`.
import type { ApiError, AskResponse, HealthResponse, SummaryResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TIMEOUT_MS = 90_000; // a multi-round tool loop can take ~15 s; leave generous headroom

export type Result<T> = { ok: true; data: T } | { ok: false; error: ApiError };

async function request<T>(path: string, init?: RequestInit): Promise<Result<T>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (e) {
    const timedOut = e instanceof DOMException && e.name === "TimeoutError";
    return fail("network_error", timedOut ? "The request timed out." : "Cannot reach the backend. Is it running on " + API_URL + "?", true, null);
  }

  const requestId = res.headers.get("X-Request-ID");
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return fail("bad_response", `Unexpected response from the server (HTTP ${res.status}).`, res.status >= 500, requestId);
  }

  if (res.ok) return { ok: true, data: body as T };

  // Typed error body from the backend: { request_id, error: { code, message, retryable } }
  const err = (body as { error?: Omit<ApiError, "request_id"> }).error;
  if (err) return { ok: false, error: { ...err, request_id: requestId } };
  return fail("bad_response", `HTTP ${res.status}`, res.status >= 500, requestId);
}

function fail(code: ApiError["code"], message: string, retryable: boolean, request_id: string | null): Result<never> {
  return { ok: false, error: { code, message, retryable, request_id } };
}

export const getSummary = () => request<SummaryResponse>("/summary");

export const getHealth = () => request<HealthResponse>("/health");

export const ask = (question: string) =>
  request<AskResponse>("/ask", { method: "POST", body: JSON.stringify({ question }) });
