import { useEffect, useState } from "react";
import { getSummary } from "../api";
import { money, moneyCompact } from "../format";
import type { ApiError, SummaryResponse } from "../types";
import { ErrorBox } from "./ErrorBox";

type State =
  | { kind: "loading" }
  | { kind: "error"; error: ApiError }
  | { kind: "ready"; data: SummaryResponse };

export function SummaryPanel() {
  const [state, setState] = useState<State>({ kind: "loading" }); // starts loading: no setState needed on mount
  const [attempt, setAttempt] = useState(0);

  // Fetch on startup (so there's something on screen before any question) and on each retry.
  useEffect(() => {
    let cancelled = false; // StrictMode runs effects twice in dev: ignore the stale response
    getSummary().then((res) => {
      if (!cancelled) setState(res.ok ? { kind: "ready", data: res.data } : { kind: "error", error: res.error });
    });
    return () => { cancelled = true; };
  }, [attempt]);

  const load = () => { setState({ kind: "loading" }); setAttempt((n) => n + 1); };

  return (
    <aside className="summary">
      <h2>Invoice overview</h2>
      {state.kind === "loading" && <div className="skeleton" aria-busy="true">Loading summary…</div>}
      {state.kind === "error" && <ErrorBox error={state.error} onRetry={load} />}
      {state.kind === "ready" && <SummaryBody s={state.data} />}
    </aside>
  );
}

function SummaryBody({ s }: { s: SummaryResponse }) {
  return (
    <>
      <div className="kpi">
        <span className="kpi-label">Total spend (approx.)</span>
        <span className="kpi-value" title={money(s.total_eur_approx)}>{moneyCompact(s.total_eur_approx)}</span>
        <span className="muted">{s.invoice_count} invoices · {s.period_start} → {s.period_end}</span>
      </div>

      <h3>By currency</h3>
      <table className="mini">
        <thead><tr><th>Ccy</th><th>#</th><th>Native (exact)</th><th>≈ EUR</th></tr></thead>
        <tbody>
          {s.by_currency.map((r) => (
            <tr key={r.currency}>
              <td>{r.currency}</td><td>{r.invoice_count}</td>
              <td>{moneyCompact(r.total_native, r.currency)}</td><td>{moneyCompact(r.eur_approx)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>By vendor status</h3>
      <table className="mini">
        <thead><tr><th>Status</th><th>Vendors</th><th>#</th><th>≈ EUR</th></tr></thead>
        <tbody>
          {s.by_vendor_status.map((r) => (
            <tr key={r.vendor_status} className={r.vendor_status === "ACTIVE" ? "" : "warn-row"}>
              <td>{r.vendor_status}</td><td>{r.vendor_count}</td><td>{r.invoice_count}</td><td>{moneyCompact(r.eur_approx)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <details className="lineage">
        <summary>Lineage &amp; assumptions</summary>
        <p>Sources: {s.lineage.sources.join(", ")} ({s.lineage.rows_used} rows)</p>
        <ul>{s.lineage.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        <p className="muted">request {s.request_id.slice(0, 8)}</p>
      </details>
    </>
  );
}
