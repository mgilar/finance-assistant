# How I used AI on this project

I built this with Claude Code as a pair programmer. `CLAUDE.md` holds the standing
instructions I gave it. Below are the key prompts and decision points: what I asked,
what it proposed, and what I decided. The AI wrote most of the code; the design
decisions and their reasons are mine, and I reviewed every step.

---

## 1. Kickoff prompt

Instead of handing over the assignment PDF, I briefed the assistant myself:

> **Goal:** Our Finance team spends a lot of time cross-referencing vendor invoices with our procurement policy — checking approvals, vendor status, spend thresholds. I want to build a simple AI assistant to help with that. The goal is to build a small web app where a finance analyst can ask questions about the invoice that and the policy.
>
> Example questions: "What are our top 5 vendors by total spend in 2025?" "What is our total spend with vendors based in Spain?" "Who is allowed to approve an invoice of EUR 60,000?"
>
> **Hard constraints:**
> - use python + fastAPI backend and React frontend
> - BE: two minimum endpoints: POST /ask takes a question, returns an answer and the evidence behind it, GET /summary returns a quick overview of the invoice data
> - FE: chat pannel where the analyst types questions and sees answers with supporting evidence, summary panel that loads on startup using GET /summary
> - AI: prepare to root both via an API key and a clearly labelled stub, load directly the policy in the context without using a vector DB
>
> This is just a prototype, don't prepare auth, deployment, cicd or visual polish.
>
> **Let's focus on:**
> - grounding answers on policy and data, routing on what part was used to provide the response.
> - failure handling
> - add evidences in the UI
> - data traceability
>
> Before proposing anything, start by profiling the data and list anything that could answers go wrong. Review the policy document as well to identify potential errors that are not part of the current dataset and list those as separate items.
>
> Available data in @data:
> - invoices_2025_clean.csv: 140 invoices with consistent dates and no duplicates, examples of real data.
> - vendor_master.csv: 10 vendors with their country, category and status
> - procurement_policy.md: a short excerpt of the Global procurement and spend policy.
>
> Let's build it with small steps, give me options with trade-offs and a recommendation, and challenge my choices. Keep a record of the key prompts and decisions for the repo.

**AI output:** a data profile and a list of policy gaps, saved as [`docs/data_profile.md`](../docs/data_profile.md).
Key findings: every vendor invoices in three currencies while the policy thresholds are in EUR;
2 credit notes; vendor status is a current snapshot; `approved_by` is a username, not a role;
and a dozen policy rules the data can't verify (PO timing, segregation of duties, emergency exceptions).
It also challenged my wording: the descriptions don't match the vendor categories, so the data is
realistic *sample* data, not real data.

## 2. Follow-up prompt: tightening the contract

After reading the profile, I added two requirements before any development:

> before starting development, also consider:
> - evidence needs to be depicted as which policy section and which data rows were used to answer the question
> - the summary should briedly specify the total spend and a breackdown by currency and by vendor status

**AI challenged:** for aggregates, "which rows" is ambiguous. Ranking the top 5 vendors
reads all 140 rows, but only the top-5 vendors' invoices produce the figures shown. And a
single "total spend" figure needs FX, which is approximate.

**I decided:**
- **Aggregate evidence** = the result table + the invoice rows behind the displayed figures
  + a note of how many rows were scanned and which filters applied.
- **Policy citations at clause level** (§3.1, §4.1 …, with the §3 threshold table as its own
  unit). The LLM cites IDs; the backend validates them and attaches the verbatim text.
- **Summary** = total (approx. EUR, rates shown), by currency (native + EUR), by vendor
  status, plus a lineage footer. I left out data-quality flag counts to keep scope tight, and
  listed them as a production item instead.

## 3. Decisions after the profile

**Data-handling rules:**
- **Currency:** per-currency totals are the truth, plus an approximate EUR figure at fixed,
  labelled rates. Approval bands are checked on the converted amount. Real ECB rates are a production item.
- **Credit notes:** totals are net, and answers say how many credit notes are included.
- **Data gaps:** answer what the data supports and explicitly state what can't be verified,
  rather than refusing outright or guessing.
- **Category** means the vendor-master category (curated master data), not free-text descriptions.

**Architecture.** The AI proposed three options: (a) put the CSV in the prompt; (b) LLM plus
typed deterministic tools; (c) text-to-SQL. I chose **(b) typed tools.** With (a) the LLM does
arithmetic and hallucinates sums. With (c) the system is more flexible, but harder to validate and
evaluate in a time box. With tools, Python computes, the LLM only chooses tools and phrases the
answer, and the tool outputs *are* the evidence. That gives the traceable lineage policy §8.2 requires.

**Other choices:**
- **Anthropic API with a labelled stub fallback**, so reviewers can run the app without a key.
- **TypeScript frontend**, so the `/ask` contract is typed on both sides.
- **Stretch goal: agentic routing.** It comes almost for free with tool calling, and every answer reports
  whether it used data, policy or both.
- **Layout:** thin routes plus `data` / `tools` / `policy` / `llm` / `schemas` modules, one per concern.
  uv + `pyproject.toml` with a lockfile, pinned to public package registries.

**Data engine.** The AI proposed pandas or DuckDB. I chose **pandas for the prototype.** It's 140
rows, the tools are plain Python functions, and the evidence is already the tool name, its arguments
and the returned rows. **For production I'd move to SQL** (warehouse or Postgres): the data won't
arrive as CSVs, the database can enforce row-level access control per entity or cost center, and
every parameterised query can be logged verbatim for the §8.2 audit trail. I'd still keep typed tools
that generate parameterised SQL rather than free text-to-SQL, because they are injection-safe,
testable and auditable.

## 4. Data layer

**AI proposed:** two ways to handle FX: illustrative fixed rates in code, or a configurable rate file. It also proposed a
small pytest suite.

**I decided:**
- **Illustrative 2025 averages as code constants** (1 GBP = 1.17 EUR, 1 USD = 0.89 EUR), with a
  note attached to every converted figure saying they are not ECB rates. In production we'd
  use real ECB rates on the invoice date, as policy §5.1 requires.
- **Load once, validate, fail fast.** Unknown currencies, orphan vendor IDs, duplicate invoice
  numbers or missing columns stop the app at startup, rather than producing a wrong answer later.
- **Add data-layer tests** whose expected values come from the independent profiling, not from
  the code under test. They are also the seed of the evaluation set.
