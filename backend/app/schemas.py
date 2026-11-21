"""API contract. Mirrored in frontend/src/types.ts.

Rule: the HTTP status says whether the *system* worked; the typed body says what
happened. Every body, success or error, carries a request_id.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- shared ----------

class Lineage(BaseModel):
    """Where a figure came from and which assumptions were applied (policy §8.2)."""
    sources: list[str]
    rows_used: int
    credit_notes_included: int
    fx_rates_to_eur: dict[str, float]
    notes: list[str]


# ---------- GET /summary ----------

class CurrencyBreakdown(BaseModel):
    currency: str
    invoice_count: int
    total_native: float          # exact, in this currency
    eur_approx: float            # converted at fixed rates


class StatusBreakdown(BaseModel):
    vendor_status: str           # current snapshot from the vendor master
    vendor_count: int
    invoice_count: int
    eur_approx: float            # mixed currencies, so no native total


class SummaryResponse(BaseModel):
    request_id: str
    invoice_count: int
    period_start: str
    period_end: str
    total_eur_approx: float
    by_currency: list[CurrencyBreakdown]
    by_vendor_status: list[StatusBreakdown]
    lineage: Lineage


# ---------- POST /ask ----------

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class PolicyCitation(BaseModel):
    id: str                      # clause id, e.g. "3.1" or "3" for the threshold table
    title: str
    text: str                    # verbatim from procurement_policy.md, attached by the backend


class ToolCallEvidence(BaseModel):
    tool: str
    args: dict[str, Any]
    ok: bool                     # failed calls stay in the lineage too
    error: str | None = None
    filters_applied: str = ""
    rows_scanned: int = 0
    result: list[dict[str, Any]] = []   # aggregate table / answer rows
    rows: list[dict[str, Any]] = []     # contributing invoice rows


class AskResponse(BaseModel):
    request_id: str
    # "can't answer from the data" is a successful outcome (HTTP 200), not an error.
    status: Literal["answered", "partial", "cannot_answer"]
    answer: str
    sources_used: list[Literal["data", "policy"]]
    policy_citations: list[PolicyCitation]
    data_evidence: list[ToolCallEvidence]
    routing_reason: str          # why data / policy / both were used (agentic routing)
    caveats: list[str]           # assumptions applied (FX, net of credit notes, status snapshot)
    gaps: list[str]              # what the data cannot verify
    unverified_figures: list[str]  # numbers in the answer not found in any evidence
    mode: Literal["llm", "stub"]
    model: str | None = None     # the model that actually answered (None in stub mode)
    policy_version: str
    data_sources: list[str]


# ---------- errors ----------

ErrorCode = Literal["invalid_request", "not_found", "llm_unavailable", "internal_error"]


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail
