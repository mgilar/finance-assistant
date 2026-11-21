# Production backlog

Items deliberately left out of the prototype. These feed the README "What production would need" section.

## Data & correctness
- Real ECB reference rates on the invoice date (policy §5.1) instead of fixed, labelled rates.
- Vendor status history (effective-dated), so §4.1 checks use the status *on the invoice date*.
- Approver role directory and requester field, to verify §3 authority and §7 segregation of duties.
- Credit-note → original-invoice link, to support §6.1 matching and 90-day aging.

## Platform
- SQL engine (warehouse / Postgres) instead of in-memory pandas. Typed tools generate
  parameterised SQL (no free text-to-SQL); row-level security per entity / cost center;
  every query logged verbatim for the §8.2 audit trail.
- Evidence for large aggregates: return row IDs + pagination instead of full rows.

## Product
- Summary panel data-quality flags: invoices missing a PO, missing an approver, from
  non-active vendors.
