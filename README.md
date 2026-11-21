# Finance Spend Assistant

A small web app where a finance analyst asks questions about 2025 vendor invoices and the
procurement policy, and every answer shows **what it is based on**: the policy clauses
(quoted verbatim) and the data rows and tool calls that produced each figure.

**Stack:** FastAPI (Python 3.13, uv) · React + TypeScript (Vite) · Claude Sonnet 5.5 via the
Anthropic API, with a clearly labelled **stub mode** when no API key is configured.

## Setup

**Backend** (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
cp .env.example .env           # add ANTHROPIC_API_KEY; leave it empty to run in STUB mode
uv run uvicorn app.main:app --port 8000 --reload
uv run pytest                  # 52 tests, no API key needed (the LLM is faked)
```

**Frontend** (tested on Node 24):

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173 (backend expected on :8000, override with VITE_API_URL)
```

**LLM path:** Anthropic API, model `claude-sonnet-5-5` (override with `ANTHROPIC_MODEL`, effort with
`ANTHROPIC_EFFORT`). Without a key, a keyword-router stub runs the *real* data tools for a few question
shapes (top N vendors, spend by country, approver for an amount) and says so in a banner and on every answer.

## How it works

```
question ─► Claude (system prompt: rules + policy tagged [§id]; 3 tools)
              │  tool loop: aggregate_spend · find_invoices · approval_requirement
              │  (pandas computes every figure; failed tools go back as is_error)
              ▼
           draft answer ─► validated against a JSON schema
              ▼
backend:   keep only policy ids that exist + attach verbatim text
           number check: every figure must appear in the evidence
           sources_used derived from the tools that actually ran
           caveats from the tools (FX, credit notes, status snapshot)
              ▼
UI:        status (answered / partial / cannot_answer) · routing reason · answer
           ▸ Policy  ▸ Data (per tool call: filters, rows scanned, result, contributing rows)
           ▸ Cannot verify  ▸ Assumptions  · request id · policy version
```

- **The LLM never does arithmetic.** It chooses tools and phrases the answer; Python computes. Even
  "who approves EUR 60k" goes through a tool, because it's a comparison against the §3 bands (read from
  the policy file, not hard-coded).
- **The backend owns the evidence** (policy §8.2 lineage): the rows shown are the rows the tools returned,
  and the model can't cite a clause that doesn't exist.
- **"Can't answer from the data" is a successful answer, not an error.** HTTP status reflects system
  health (503 if the LLM is down, with no silent fallback to the stub); the typed body says what happened.
  Every response carries a `request_id`.

Data issues found before designing anything (mixed currencies vs EUR thresholds, credit notes, vendor
status as a snapshot, usernames instead of roles) and the policy rules the data can't verify are in
[`docs/data_profile.md`](docs/data_profile.md).

## Write-up

### 1. What I built and what I left out

**Built:** `GET /summary` (total, by currency, by vendor status, lineage), `POST /ask` with grounded,
cited answers, and a UI that puts the evidence next to every answer, with explicit loading, error and retry
states. **Stretch goal: agentic routing.** The model states why it used data, policy or both; the backend
shows what was actually used.

**Priorities:** correctness and traceability over breadth. Typed tools instead of text-to-SQL (easier to
validate and test in a time box); pandas instead of a database (140 rows); fixed, labelled FX rates instead
of ECB rates; answers that state what they can't verify instead of guessing.

**Left out on purpose:** auth, deployment, persistence of chats, real FX rates, a second LLM provider, a
vector DB (the policy is ~50 lines and goes into the prompt whole), and visual polish. See
[`docs/production_backlog.md`](docs/production_backlog.md).

### 2. How I'd evaluate it, and catch hallucinations

Hallucination here means **a figure, citation or claim that the evidence doesn't support**. I'd attack it
in three layers: prevent it, detect it at runtime, and measure it offline.

**Prevent (by design).** The model never computes figures; tools do. Policy units have IDs, and only those
can be cited. The prompt lists what the data can't show (approver roles, PO dates, status on the invoice
date…), so the model reports a gap instead of filling it.

**Detect (on every answer, already built).**
- *Citation validation:* unknown clause IDs are dropped and flagged.
- *Number check:* every figure in the answer must match a tool result, the cited policy or the question
  (within 0.5%, so "EUR 1.13M" matches 1,132,677.97). A mismatch marks the figure as unverified and
  downgrades the answer to `partial`. In live runs it flagged "14": correct, but computed by the model
  (17 − 3) rather than by a tool. That's exactly the class of error it exists to catch.
- *Lineage from facts:* `sources_used` comes from the tools that ran, not from what the model says.

**Measure (offline eval set).** 20–30 questions with expected answers **computed independently from the
CSVs** (never from the app's own code), covering data questions, policy questions, mixed questions,
unanswerable-by-design questions (approver authority, PO timing) and adversarial ones (prompt injection,
off-topic). Scored per answer:

| Metric | Why |
|---|---|
| Figure accuracy vs expected values (with tolerance) | Correctness |
| Expected status (e.g. "partial" for authority questions) | Honesty about gaps |
| Required citations present, no invented ones | Grounding |
| Unverified-figure rate | Hallucination signal |
| Status consistency across 3 repeated runs | Trust: same question, same verdict |
| Tool calls, latency, cost per answer | Efficiency |

The last two metrics came out of this build: live runs showed the same question flipping between statuses,
and repeated tool calls that I traced to the structured-output setup and fixed
([`docs/live_findings.md`](docs/live_findings.md)). For the wording of the answers, I'd add an LLM-as-judge
faithfulness check ("is every claim supported by this evidence?"), calibrated against a sample reviewed by
finance. In production: track the unverified-figure and `cannot_answer` rates, collect analyst feedback, and
run a weekly sampled audit.

### 3. What production would need

- **Data:** the finance warehouse instead of CSVs. Typed tools generate *parameterised* SQL (not free
  text-to-SQL), so queries stay injection-safe, testable and loggable. Real ECB rates on the invoice
  date (§5.1); vendor status history; an approver role directory, which unlocks the §3 and §7 checks that
  are gaps today.
- **Audit trail (§8.2):** persist every request (user, question, tool calls with arguments, rows
  returned, policy version, model, answer, verification results) under its `request_id`, for the 10-year
  retention in §8.1. The response already carries everything needed; it just isn't stored.
- **Policy:** from a versioned, approved document system, parsed when a new version is published and
  stored with its version; each answer points at the version in force.
- **Access control:** SSO, plus row-level security enforced in the database (entity / cost center), so
  the assistant can only query what the analyst may see. Roles for who can ask about what.
- **Cost (200 users):** measured about **$0.006–0.008 per question** on Sonnet 5.5, with prompt caching
  of the static policy and tools. At about 20 questions per user per day, that's about **$25–35/day**. Levers:
  caching (already on), per-question model routing (Haiku for simple lookups, measured with the eval),
  rate limits per user.
- **Operations:** streaming answers (about 5 s today), monitoring the eval metrics above, alerting on
  503 rates, and a regression eval run before any prompt or model change.

## Time spent and next steps

**Time:** about 3.5 hours.

**What I'd do next, in order:**
1. Build the eval set and scoring script described above, and run it on every prompt or model change.
2. Persist the audit record per request (§8.2) and add analyst feedback on answers.
3. Real ECB rates and vendor status history, to remove the two most common caveats.
4. An approver role directory, to turn "can't verify authority" into an actual §3 / §7 check.
5. Stream responses, and try routing simple lookups to a cheaper model, judged by the eval.

## How I used AI

I built this with Claude Code as a pair programmer: I briefed it myself, made every design decision from
options it laid out (and challenged), and reviewed each step. Two moments I'd highlight: a **live API
check found two bugs** that the fake-client tests couldn't (tool-loop exhaustion and broken cross-question
caching); and when the model kept repeating tool calls, I **didn't accept the "it's double-checking"
explanation**. We measured until we found that our own structured-output setup caused it (2.67 → 1.00 calls
per question). Full record: [`ai/DECISIONS.md`](ai/DECISIONS.md) (prompts and decisions) and
[`CLAUDE.md`](CLAUDE.md) (standing instructions).

## Repository map

```
backend/app/   main.py (routes, errors) · data.py (load, join, FX) · policy.py (citable units)
               tools.py (deterministic tools) · llm.py (Claude loop, prompt) · stub.py
               ask.py (post-processing) · verification.py (citations, number check) · schemas.py (contract)
backend/tests/ 52 tests, LLM faked
frontend/src/  api.ts (typed fetch → Result) · types.ts (contract mirror) · components/
docs/          data_profile.md · live_findings.md · production_backlog.md
ai/            DECISIONS.md
data/          source CSVs + policy (unchanged)
```
