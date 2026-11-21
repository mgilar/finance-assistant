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
- Policy from a versioned, approved document system: parsed when a new version is
  published (not per request or per deploy), units stored with their version, and each
  answer's audit record pointing at the version in force. The prototype already parses once
  at startup and returns `policy_version` with every answer.
- Prompt caching: the tagged policy + tool definitions are a static prefix (already sent
  with `cache_control`). Monitor `cache_read_input_tokens`, and keep anything per-request
  (timestamps, user IDs) out of the system prompt so the prefix stays byte-identical.

## Product
- Summary panel data-quality flags: invoices missing a PO, missing an approver, from
  non-active vendors.
- Provider-agnostic LLM layer: the post-processing (citations, number check, lineage) is
  already provider-neutral; only `llm.py` would need a second adapter (e.g. OpenAI).
