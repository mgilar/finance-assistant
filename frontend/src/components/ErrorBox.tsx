import type { ApiError } from "../types";

// System failures only (red). "Can't answer from the data" is NOT an error and never lands here.
export function ErrorBox({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <strong>{TITLES[error.code]}</strong>
      <p>{error.message}</p>
      <div className="error-meta">
        {error.request_id && <span className="muted">request {error.request_id.slice(0, 8)}</span>}
        {error.retryable && onRetry && <button onClick={onRetry}>Retry</button>}
      </div>
    </div>
  );
}

const TITLES: Record<ApiError["code"], string> = {
  invalid_request: "Invalid request",
  not_found: "Not found",
  llm_unavailable: "The AI service is unavailable",
  internal_error: "Server error",
  network_error: "Connection problem",
  bad_response: "Unexpected server response",
};
