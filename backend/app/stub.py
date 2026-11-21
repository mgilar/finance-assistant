"""STUB MODE: used only when no ANTHROPIC_API_KEY is configured.

A keyword router, not an LLM. It maps a few question shapes to the *real* tools, so
evidence, verification and the UI work end to end. Everything else is answered
honestly as cannot_answer. Every response is labelled mode="stub".
"""

import re

from app.answer import RawAnswer, run_tool_safely
from app.data import Dataset
from app.policy import Policy

_TOP_N = re.compile(r"\btop\s*(\d+)\s*vendors?\b", re.I)
_COUNTRY = re.compile(r"\b(?:in|from)\s+(?:the\s+)?([A-Z][a-zA-Z]+)")  # case-sensitive: needs a capitalised name
_APPROVE = re.compile(
    r"approv\w*.*?(EUR|GBP|USD|€|£|\$)?\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(EUR|GBP|USD)?", re.I
)
_CCY = {"€": "EUR", "£": "GBP", "$": "USD"}

SUPPORTED = ("top N vendors by spend", "total spend with vendors in <country>",
             "who can approve an invoice of <amount>")


def run_stub(question: str, ds: Dataset, policy: Policy) -> RawAnswer:
    if m := _APPROVE.search(question):
        return _approval(m, ds, policy)
    if m := _TOP_N.search(question):
        return _top_vendors(int(m.group(1)), ds, policy)
    if (m := _COUNTRY.search(question)) and re.search(r"spen[dt]", question, re.I):
        return _country_spend(m.group(1), ds, policy)
    return RawAnswer(
        status="cannot_answer",
        answer=("Stub mode (no LLM configured) only understands: " + "; ".join(SUPPORTED)
                + ". Configure ANTHROPIC_API_KEY for free-form questions."),
        policy_citation_ids=[], gaps=[], routing_reason="Stub keyword router: no pattern matched.",
    )


def _vendor_label(ds: Dataset, name: str) -> str:
    status = ds.vendors.loc[ds.vendors["vendor_name"] == name, "status"].iloc[0]
    return name if status == "ACTIVE" else f"{name} ({status})"


def _top_vendors(n: int, ds: Dataset, policy: Policy) -> RawAnswer:
    out = run_tool_safely("aggregate_spend", {"group_by": "vendor", "limit": n}, ds, policy)
    if not out.evidence.ok:
        return _failed(out)
    lines = [f"{i}. {_vendor_label(ds, g['vendor'])}: EUR {g['eur_approx']:,.2f}"
             for i, g in enumerate(out.for_model["result"], 1)]
    non_active = any("(" in line for line in lines)
    return RawAnswer(
        status="answered",
        answer=f"Top {n} vendors by 2025 spend (approx. EUR):\n" + "\n".join(lines),
        policy_citation_ids=["4.1"] if non_active else [],
        gaps=[], routing_reason="Data question: ranked vendor spend with aggregate_spend.",
        outcomes=[out],
    )


def _country_spend(country: str, ds: Dataset, policy: Policy) -> RawAnswer:
    args = {"filters": {"vendor_countries": [country]}, "group_by": "vendor"}
    out = run_tool_safely("aggregate_spend", args, ds, policy)
    if not out.evidence.ok:
        return _failed(out)
    total = out.for_model["overall_total"]
    vendors = ", ".join(f"{_vendor_label(ds, g['vendor'])} EUR {g['eur_approx']:,.2f}"
                        for g in out.for_model["result"])
    return RawAnswer(
        status="answered",
        answer=(f"Total 2025 spend with vendors based in {country.title()}: approx. "
                f"EUR {total['eur_approx']:,.2f} across {total['invoice_count']} invoices "
                f"({vendors})."),
        policy_citation_ids=["4.1"] if "(" in vendors else [],
        gaps=[], routing_reason="Data question: filtered spend by vendor country.",
        outcomes=[out],
    )


def _approval(m: re.Match, ds: Dataset, policy: Policy) -> RawAnswer:
    ccy = (m.group(1) or m.group(4) or "EUR").upper()
    ccy = _CCY.get(ccy, ccy)
    amount = float(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
    out = run_tool_safely("approval_requirement", {"amount": amount, "currency": ccy}, ds, policy)
    if not out.evidence.ok:
        return _failed(out)
    r = out.for_model
    eur = "" if ccy == "EUR" else f" (approx. EUR {r['amount_eur']:,.2f})"
    return RawAnswer(
        status="answered",
        answer=(f"An invoice of {ccy} {amount:,.2f}{eur} falls in the {r['band']} band, so it "
                f"must be approved by: {r['required_approver']}."),
        policy_citation_ids=["3"], gaps=[],
        routing_reason="Policy question with an amount: §3 band computed by approval_requirement.",
        outcomes=[out],
    )


def _failed(out) -> RawAnswer:
    return RawAnswer(
        status="cannot_answer",
        answer=f"The figure could not be computed: {out.evidence.error}",
        policy_citation_ids=[], gaps=[], routing_reason="Tool call failed.", outcomes=[out],
    )
