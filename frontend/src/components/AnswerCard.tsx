import type { AskResponse } from "../types";
import { DataEvidence, PolicyEvidence } from "./Evidence";

const STATUS_LABEL = { answered: "Answered", partial: "Partial — see gaps", cannot_answer: "Cannot answer from the data" };

// The answer and everything it is based on, kept together.
export function AnswerCard({ r }: { r: AskResponse }) {
  const toolCalls = r.data_evidence.length;
  return (
    <article className={`bubble bot answer status-${r.status}`}>
      <header className="answer-head">
        <span className={`badge status-${r.status}`}>{STATUS_LABEL[r.status]}</span>
        {r.sources_used.length > 0
          ? r.sources_used.map((s) => <span key={s} className="badge source">{s === "data" ? "Invoice data" : "Policy"}</span>)
          : <span className="badge source none">No sources used</span>}
        <span className="muted">{r.mode === "stub" ? "stub" : r.model}</span>
      </header>

      <p className="routing"><strong>Routing:</strong> {r.routing_reason}</p>
      <p className="answer-text">{r.answer}</p>

      {r.unverified_figures.length > 0 && (
        <p className="unverified">
          ⚠ Figures not found in the evidence: <strong>{r.unverified_figures.join(", ")}</strong>. Check them against the data below.
        </p>
      )}

      {r.policy_citations.length > 0 && (
        <details>
          <summary>Policy ({r.policy_citations.map((c) => `§${c.id}`).join(" ")})</summary>
          <PolicyEvidence citations={r.policy_citations} version={r.policy_version} />
        </details>
      )}
      {toolCalls > 0 && (
        <details>
          <summary>Data ({toolCalls} tool call{toolCalls > 1 ? "s" : ""}{r.data_evidence.some((e) => !e.ok) ? ", some failed" : ""})</summary>
          {r.data_evidence.map((e, i) => <DataEvidence key={i} e={e} />)}
          <p className="muted">Sources: {r.data_sources.join(", ")}</p>
        </details>
      )}
      {r.gaps.length > 0 && (
        <details open={r.status !== "answered"}>
          <summary>Cannot verify ({r.gaps.length})</summary>
          <ul>{r.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </details>
      )}
      {r.caveats.length > 0 && (
        <details>
          <summary>Assumptions ({r.caveats.length})</summary>
          <ul>{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </details>
      )}

      <footer className="muted">request {r.request_id.slice(0, 8)} · {r.policy_version}</footer>
    </article>
  );
}
