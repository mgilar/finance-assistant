import { cell } from "../format";
import type { PolicyCitation, Row, ToolCallEvidence } from "../types";

export function PolicyEvidence({ citations, version }: { citations: PolicyCitation[]; version: string }) {
  return (
    <div className="policy">
      {citations.map((c) => (
        <blockquote key={c.id}>
          <strong>§{c.id} {c.title}</strong>
          <pre>{c.text}</pre>
        </blockquote>
      ))}
      <p className="muted">Quoted verbatim from {version}.</p>
    </div>
  );
}

// Columns shown for invoice rows; the full row is in the API response.
const ROW_COLUMNS = ["invoice_number", "invoice_date", "vendor_name", "vendor_status", "amount",
                     "currency", "amount_eur", "po_number", "approved_by"];

export function DataEvidence({ e }: { e: ToolCallEvidence }) {
  if (!e.ok) {
    return (
      <div className="tool failed">
        <code>{e.tool}</code> ✗ failed: {e.error}
        <div className="muted">args: <code>{JSON.stringify(e.args)}</code></div>
      </div>
    );
  }
  return (
    <div className="tool">
      <div>
        <code>{e.tool}</code> ✓ <span className="muted">filters: {e.filters_applied}
        {e.rows_scanned > 0 && ` · ${e.rows_scanned} rows scanned`}</span>
      </div>
      {e.result.length > 0 && <Table rows={e.result} />}
      <MissingSummary rows={e.rows} />
      {e.rows.length > 0 && (
        <details>
          <summary>{e.rows.length} contributing invoice row{e.rows.length > 1 ? "s" : ""}</summary>
          <Table rows={e.rows} columns={ROW_COLUMNS} scroll />
        </details>
      )}
    </div>
  );
}

// Policy-relevant gaps, visible without expanding the rows: no PO (§2.2) or no approver (§3.1).
const POLICY_FIELDS = ["po_number", "approved_by"];

function MissingSummary({ rows }: { rows: Row[] }) {
  const noPo = rows.filter((r) => r.po_number === null).length;
  const noApprover = rows.filter((r) => r.approved_by === null).length;
  if (noPo === 0 && noApprover === 0) return null;
  return (
    <p className="missing-summary">
      Of {rows.length} invoice rows: <strong>{noPo} without a PO</strong> (§2.2) ·{" "}
      <strong>{noApprover} without an approver</strong> (§3.1)
    </p>
  );
}

function Table({ rows, columns, scroll }: { rows: Row[]; columns?: string[]; scroll?: boolean }) {
  const cols = columns ?? Object.keys(rows[0]);
  return (
    <div className={scroll ? "table-wrap scroll" : "table-wrap"}>
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map((c) => (
              <td key={c}>
                {r[c] === null && POLICY_FIELDS.includes(c) ? <span className="missing-badge">MISSING</span> : cell(r[c])}
              </td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
