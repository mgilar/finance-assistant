"""Deterministic tools the LLM can call. Python computes; the model only chooses.

Each tool returns two views of the same result:
  - `for_model`: compact JSON (rows capped) that goes back to the LLM.
  - `evidence`:  the full ToolCallEvidence shown in the UI (all contributing rows).
Failures raise ToolError; the caller sends them to the model as `is_error` tool
results and records them in the lineage. They are never turned into values.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from app.data import FX_NOTE, FX_TO_EUR, Dataset
from app.policy import Policy
from app.schemas import ToolCallEvidence

MODEL_ROW_CAP = 25
STATUS_NOTE = "Vendor status is the current vendor-master snapshot, not the status on the invoice date."

EVIDENCE_COLUMNS = [
    "invoice_number", "invoice_date", "vendor_id", "vendor_name", "vendor_country",
    "vendor_category", "vendor_status", "description", "amount", "currency",
    "amount_eur", "cost_center", "po_number", "approved_by",
]


class ToolError(Exception):
    """A tool could not produce a trustworthy result. Message is shown to the model."""


# ---------- arguments (also used to generate the JSON schemas sent to the model) ----------

class Filters(BaseModel):
    """All filters are optional and combined with AND. List values are OR-ed."""
    vendor_names: list[str] | None = Field(None, description="Exact vendor names")
    vendor_countries: list[str] | None = Field(None, description="e.g. ['Spain']")
    vendor_categories: list[str] | None = Field(None, description="Vendor-master category, e.g. ['IT Services']")
    vendor_statuses: list[Literal["ACTIVE", "INACTIVE", "ON_HOLD"]] | None = None
    currencies: list[Literal["EUR", "GBP", "USD"]] | None = None
    cost_centers: list[str] | None = None
    approvers: list[str] | None = Field(None, description="approved_by usernames")
    date_from: str | None = Field(None, description="Inclusive, YYYY-MM-DD")
    date_to: str | None = Field(None, description="Inclusive, YYYY-MM-DD")
    missing_po: bool | None = Field(None, description="True = only invoices without a PO number")
    missing_approver: bool | None = Field(None, description="True = only invoices without approved_by")
    credit_notes: bool | None = Field(None, description="True = only credit notes, False = exclude them")
    min_amount_eur: float | None = None
    max_amount_eur: float | None = None


GroupBy = Literal["vendor", "country", "category", "vendor_status", "currency",
                  "cost_center", "month", "approver"]


class AggregateSpendArgs(BaseModel):
    filters: Filters = Filters()
    group_by: GroupBy | None = Field(None, description="Omit for a single total")
    limit: int = Field(10, ge=1, le=50, description="Max groups returned, sorted by EUR spend desc")


class FindInvoicesArgs(BaseModel):
    filters: Filters = Filters()
    sort_by: Literal["amount_eur_desc", "amount_eur_asc", "date_asc", "date_desc"] = "amount_eur_desc"


class ApprovalRequirementArgs(BaseModel):
    amount: float = Field(gt=0, description="Invoice / PO value")
    currency: Literal["EUR", "GBP", "USD"] = "EUR"


# ---------- results ----------

@dataclass
class ToolOutcome:
    for_model: dict[str, Any]
    evidence: ToolCallEvidence
    policy_ids: list[str] = field(default_factory=list)  # clauses the tool itself relies on
    caveats: list[str] = field(default_factory=list)


# ---------- filtering ----------

_TEXT_FILTERS = {  # filter field -> (dataframe column, label)
    "vendor_names": ("vendor_name", "vendor"),
    "vendor_countries": ("vendor_country", "country"),
    "vendor_categories": ("vendor_category", "category"),
    "vendor_statuses": ("vendor_status", "vendor status"),
    "currencies": ("currency", "currency"),
    "cost_centers": ("cost_center", "cost center"),
    "approvers": ("approved_by", "approver"),
}


def apply_filters(df: pd.DataFrame, f: Filters) -> tuple[pd.DataFrame, str]:
    mask = pd.Series(True, index=df.index)
    applied: list[str] = []

    for name, (col, label) in _TEXT_FILTERS.items():
        values = getattr(f, name)
        if not values:
            continue
        known = {str(v).casefold(): v for v in df[col].dropna().unique()}
        unknown = [v for v in values if v.casefold() not in known]
        if unknown:
            # Never let a typo become "EUR 0 spent": fail and show the valid values.
            raise ToolError(f"Unknown {label} value(s) {unknown}. Valid values: {sorted(known.values())}")
        canonical = [known[v.casefold()] for v in values]
        mask &= df[col].isin(canonical)
        applied.append(f"{label} in {canonical}")

    if f.date_from:
        mask &= df["invoice_date"] >= _parse_date(f.date_from)
        applied.append(f"date >= {f.date_from}")
    if f.date_to:
        mask &= df["invoice_date"] <= _parse_date(f.date_to)
        applied.append(f"date <= {f.date_to}")
    for flag, col, label in (("missing_po", "po_number", "PO"), ("missing_approver", "approved_by", "approver")):
        value = getattr(f, flag)
        if value is not None:
            mask &= df[col].isna() if value else df[col].notna()
            applied.append(f"{'missing' if value else 'has'} {label}")
    if f.credit_notes is not None:
        mask &= df["is_credit_note"] == f.credit_notes
        applied.append("only credit notes" if f.credit_notes else "excluding credit notes")
    if f.min_amount_eur is not None:
        mask &= df["amount_eur"] >= f.min_amount_eur
        applied.append(f"amount_eur >= {f.min_amount_eur:,.2f}")
    if f.max_amount_eur is not None:
        mask &= df["amount_eur"] <= f.max_amount_eur
        applied.append(f"amount_eur <= {f.max_amount_eur:,.2f}")

    return df[mask], "; ".join(applied) or "none (all invoices)"


def _parse_date(value: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(value)
    except ValueError as exc:
        raise ToolError(f"Invalid date {value!r}; use YYYY-MM-DD") from exc


def _rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df[EVIDENCE_COLUMNS].copy()
    out["invoice_date"] = out["invoice_date"].dt.date.astype(str)
    out = out.astype(object).where(out.notna(), None)
    return out.to_dict(orient="records")


def _common_caveats(df: pd.DataFrame, f: Filters | None = None, group_by: str | None = None) -> list[str]:
    caveats = [FX_NOTE]
    n_credit = int(df["is_credit_note"].sum())
    if n_credit:
        caveats.append(f"Totals are net: includes {n_credit} credit note(s) (negative amounts).")
    if (f and f.vendor_statuses) or group_by == "vendor_status":
        caveats.append(STATUS_NOTE)
    return caveats


# ---------- tools ----------

_GROUP_COLUMNS = {
    "vendor": "vendor_name", "country": "vendor_country", "category": "vendor_category",
    "vendor_status": "vendor_status", "currency": "currency", "cost_center": "cost_center",
    "month": "month", "approver": "approved_by",
}


def aggregate_spend(ds: Dataset, args: AggregateSpendArgs) -> ToolOutcome:
    df, filters_text = apply_filters(ds.invoices, args.filters)
    df = df.assign(month=df["invoice_date"].dt.strftime("%Y-%m"))
    total = _group_stats(df)

    if args.group_by is None:
        result, contributing = [total], df
    else:
        col = _GROUP_COLUMNS[args.group_by]
        keyed = df.assign(_key=df[col].fillna("(none)"))
        groups = [{args.group_by: key, **_vendor_context(args.group_by, g), **_group_stats(g)}
                  for key, g in keyed.groupby("_key")]
        groups.sort(key=lambda g: g["eur_approx"], reverse=True)
        result = groups[: args.limit]
        shown = {g[args.group_by] for g in result}
        # Contributing rows = invoices behind the figures shown, not every row scanned.
        contributing = keyed[keyed["_key"].isin(shown)]

    for_model = {
        "filters_applied": filters_text,
        "rows_scanned": len(df),
        "groups_total": None if args.group_by is None else int(keyed["_key"].nunique()),
        "overall_total": total,
        "result": result,
    }
    evidence = ToolCallEvidence(
        tool="aggregate_spend", args=args.model_dump(exclude_none=True), ok=True,
        filters_applied=filters_text, rows_scanned=len(df),
        result=result, rows=_rows(contributing.sort_values("amount_eur", ascending=False)),
    )
    return ToolOutcome(for_model, evidence, caveats=_common_caveats(df, args.filters, args.group_by))


def _vendor_context(group_by: str, g: pd.DataFrame) -> dict[str, Any]:
    """Vendor groups carry status and country, so the model never needs extra calls to find
    out whether a vendor is ACTIVE (a live test showed it looping to get exactly this)."""
    if group_by != "vendor":
        return {}
    first = g.iloc[0]
    return {"vendor_status": first["vendor_status"], "vendor_country": first["vendor_country"]}


def _group_stats(g: pd.DataFrame) -> dict[str, Any]:
    return {
        "invoice_count": len(g),
        "eur_approx": round(float(g["amount_eur"].sum()), 2),
        "native_totals": {c: round(float(v), 2) for c, v in g.groupby("currency")["amount"].sum().items()},
        "credit_notes": int(g["is_credit_note"].sum()),
    }


def find_invoices(ds: Dataset, args: FindInvoicesArgs) -> ToolOutcome:
    df, filters_text = apply_filters(ds.invoices, args.filters)
    col, asc = {"amount_eur_desc": ("amount_eur", False), "amount_eur_asc": ("amount_eur", True),
                "date_asc": ("invoice_date", True), "date_desc": ("invoice_date", False)}[args.sort_by]
    df = df.sort_values(col, ascending=asc)
    rows = _rows(df)

    for_model = {
        "filters_applied": filters_text,
        "match_count": len(rows),
        "rows_shown_to_you": min(len(rows), MODEL_ROW_CAP),
        "rows": rows[:MODEL_ROW_CAP],
        "note": (f"Only the first {MODEL_ROW_CAP} rows are shown to you; the user sees all {len(rows)}."
                 if len(rows) > MODEL_ROW_CAP else None),
    }
    evidence = ToolCallEvidence(
        tool="find_invoices", args=args.model_dump(exclude_none=True), ok=True,
        filters_applied=filters_text, rows_scanned=len(ds.invoices), result=[], rows=rows,
    )
    return ToolOutcome(for_model, evidence, caveats=_common_caveats(df, args.filters))


# ---------- approval bands, read from the policy (§3 table), not hard-coded ----------

@dataclass(frozen=True)
class ApprovalBand:
    low: float          # exclusive lower bound (0 for the first band)
    high: float | None  # inclusive upper bound; None = no upper limit
    approver: str
    label: str


_NUM = r"([\d,]+(?:\.\d+)?)"


def parse_approval_bands(policy: Policy) -> list[ApprovalBand]:
    bands: list[ApprovalBand] = []
    for line in policy.units["3"].text.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2 or set(cells[0]) <= set("-"):
            continue
        label, approver = cells
        num = lambda s: float(s.replace(",", ""))  # noqa: E731
        if m := re.fullmatch(rf"Up to {_NUM}", label):
            bands.append(ApprovalBand(0.0, num(m[1]), approver, label))
        elif m := re.fullmatch(rf"{_NUM}\s*[–-]\s*{_NUM}", label):
            bands.append(ApprovalBand(num(m[1]) - 0.01, num(m[2]), approver, label))
        elif m := re.fullmatch(rf"Above {_NUM}", label):
            bands.append(ApprovalBand(num(m[1]), None, approver, label))
    if len(bands) < 2:
        raise ToolError("Could not read the approval thresholds from policy §3")
    return bands


def approval_requirement(policy: Policy, args: ApprovalRequirementArgs) -> ToolOutcome:
    amount_eur = round(args.amount * FX_TO_EUR[args.currency], 2)
    band = next(b for b in parse_approval_bands(policy)
                if amount_eur > b.low and (b.high is None or amount_eur <= b.high))
    result = {"amount": args.amount, "currency": args.currency, "amount_eur": amount_eur,
              "band": band.label, "required_approver": band.approver}
    caveats = [] if args.currency == "EUR" else [
        FX_NOTE, "Policy §3 does not state which FX rate applies to approval thresholds."]
    evidence = ToolCallEvidence(
        tool="approval_requirement", args=args.model_dump(), ok=True,
        filters_applied="policy §3 threshold table", result=[result],
    )
    return ToolOutcome(result, evidence, policy_ids=["3"], caveats=caveats)


# ---------- registry & dispatch ----------

TOOL_SPECS: dict[str, tuple[type[BaseModel], str]] = {
    "aggregate_spend": (AggregateSpendArgs,
        "Sum invoice spend (net of credit notes) with optional filters and grouping. Returns EUR "
        "approximations and exact native-currency totals per group, sorted by EUR spend. Use for "
        "totals, rankings and breakdowns."),
    "find_invoices": (FindInvoicesArgs,
        "List individual invoices matching filters (e.g. missing PO, missing approver, non-ACTIVE "
        "vendors). Use when the question is about specific invoices."),
    "approval_requirement": (ApprovalRequirementArgs,
        "Return the approver required by policy §3 for an amount, converting to EUR first. Always "
        "use this instead of reading the threshold table yourself."),
}


def tool_definitions() -> list[dict[str, Any]]:
    """Anthropic tool definitions generated from the Pydantic argument models."""
    return [{"name": name, "description": desc, "input_schema": model.model_json_schema()}
            for name, (model, desc) in TOOL_SPECS.items()]


def failed_outcome(name: str, raw_args: dict[str, Any], message: str) -> ToolOutcome:
    """A failed call stays in the lineage (§8.2 covers failures too)."""
    evidence = ToolCallEvidence(tool=name, args=raw_args, ok=False, error=message)
    return ToolOutcome({"error": message}, evidence)


def execute_tool(name: str, raw_args: dict[str, Any], ds: Dataset, policy: Policy) -> ToolOutcome:
    """Run a tool. Raises ToolError (with a model-readable message) on any failure."""
    if name not in TOOL_SPECS:
        raise ToolError(f"Unknown tool {name!r}")
    model, _ = TOOL_SPECS[name]
    try:
        args = model.model_validate(raw_args)
    except ValidationError as exc:
        raise ToolError(f"Invalid arguments: {exc.errors(include_url=False)}") from exc
    if name == "aggregate_spend":
        return aggregate_spend(ds, args)
    if name == "find_invoices":
        return find_invoices(ds, args)
    return approval_requirement(policy, args)
