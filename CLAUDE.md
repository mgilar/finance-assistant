# Finance spend intelligence assistant — AI harness

Instructions for the AI coding assistant (Claude Code) used to build this prototype.
The developer makes every design decision; the assistant proposes options with
trade-offs, implements in small reviewable steps, and explains each step.

## Stack
- Backend: Python 3.13, FastAPI, uv (`backend/`). Run: `uv run uvicorn app.main:app --reload`
- Frontend: Vite + React + TypeScript (`frontend/`). Run: `npm run dev`
- LLM: Anthropic API with tool calling when `ANTHROPIC_API_KEY` is set; otherwise a
  deterministic stub, clearly labelled as such in the API response and the UI.

## Design rules
1. **The LLM never does arithmetic or reads raw rows.** It chooses deterministic
   tools; Python computes; the LLM writes the answer from tool results.
2. **The backend owns the evidence.** Rows and aggregates shown to the user are the
   ones the tools actually returned. Policy citations from the model are validated
   against real section IDs; unknown IDs are dropped and flagged.
3. **Traceable lineage (policy §8.2).** Every answer carries which sources were used
   (data / policy / both), the tool calls with arguments, and any caveats.
4. **Currency:** per-currency totals are the source of truth. EUR conversion uses a
   fixed, labelled rate table and always adds a caveat. Policy approval bands (§3)
   are evaluated on the EUR-converted amount.
5. **Credit notes:** negative amounts are included in totals (net spend), and answers
   state how many credit notes are included.
6. **Never guess past the data.** Answer what the data supports, and state explicitly
   what can't be verified (approver roles, PO timing, vendor status on the invoice
   date, etc.; see `docs/data_profile.md` §B).
7. **Category** means `vendor_master.category`, never the free-text invoice description.
8. **Data engine:** pandas for the prototype; no SQL engine.
9. **Evidence shape:** policy citations at clause level (§3.1 …; the §3 table is its own
   unit), validated against parsed IDs, with verbatim text attached by the backend. Data
   evidence = tool name + args + result table + contributing invoice rows + scanned-row count.
10. **Summary:** total (approx. EUR), by currency (native + EUR), by vendor status, and a
    lineage footer (sources, row count, credit notes, FX rates). Nothing more.
11. Out-of-scope ideas go to `docs/production_backlog.md`, not into the code.

## Conventions
- Keep `main.py` thin (routes only); logic lives in `data.py`, `tools.py`, `policy.py`, `llm.py`.
- Pydantic models in `schemas.py` are the API contract; mirror them in `frontend/src/types.ts`.
- Prototype-level code: readable over clever, no auth/deployment/CI.
- Use public registries only (PyPI, npmjs) so lockfiles are reproducible for reviewers.
