"""Tool tests. Expected values are computed independently with the csv module."""

import csv

import pytest

from app.data import DATA_DIR, FX_TO_EUR, load_dataset
from app.policy import load_policy
from app.tools import MODEL_ROW_CAP, ToolError, execute_tool, tool_definitions


@pytest.fixture(scope="module")
def ds():
    return load_dataset()


@pytest.fixture(scope="module")
def policy():
    return load_policy()


@pytest.fixture(scope="module")
def raw():
    vendors = {v["vendor_id"]: v for v in csv.DictReader(open(DATA_DIR / "vendor_master.csv"))}
    rows = list(csv.DictReader(open(DATA_DIR / "invoices_2025_clean.csv")))
    for r in rows:
        r["eur"] = round(float(r["amount"]) * FX_TO_EUR[r["currency"]], 2)
        r["country"] = vendors[r["vendor_id"]]["country"]
    return rows


def test_spain_total(ds, policy, raw):
    out = execute_tool("aggregate_spend", {"filters": {"vendor_countries": ["Spain"]}}, ds, policy)
    expected = [r for r in raw if r["country"] == "Spain"]
    assert out.for_model["result"][0]["eur_approx"] == pytest.approx(sum(r["eur"] for r in expected), abs=0.01)
    assert len(out.evidence.rows) == len(expected)


def test_country_filter_is_case_insensitive(ds, policy):
    out = execute_tool("aggregate_spend", {"filters": {"vendor_countries": ["spain"]}}, ds, policy)
    assert out.evidence.filters_applied == "country in ['Spain']"


def test_unknown_filter_value_fails_instead_of_returning_zero(ds, policy):
    with pytest.raises(ToolError, match="Valid values"):
        execute_tool("aggregate_spend", {"filters": {"vendor_countries": ["España"]}}, ds, policy)


def test_top_5_vendors_evidence_is_contributing_rows(ds, policy, raw):
    out = execute_tool("aggregate_spend", {"group_by": "vendor", "limit": 5}, ds, policy)
    top = out.for_model["result"]
    assert len(top) == 5
    assert [g["eur_approx"] for g in top] == sorted((g["eur_approx"] for g in top), reverse=True)
    shown = {g["vendor"] for g in top}
    assert {r["vendor_name"] for r in out.evidence.rows} == shown
    assert out.evidence.rows_scanned == 140
    assert len(out.evidence.rows) == sum(g["invoice_count"] for g in top)
    # Vendor groups carry status, so the model needn't query it separately.
    assert {g["vendor"]: g["vendor_status"] for g in top}["PharmaPrint Studios"] == "INACTIVE"


def test_find_invoices_caps_model_view_not_evidence(ds, policy):
    out = execute_tool("find_invoices", {"filters": {"missing_approver": True}}, ds, policy)
    assert out.for_model["match_count"] == 25
    assert len(out.evidence.rows) == 25
    out = execute_tool("find_invoices", {}, ds, policy)
    assert len(out.for_model["rows"]) == MODEL_ROW_CAP
    assert len(out.evidence.rows) == 140


@pytest.mark.parametrize("amount,currency,approver", [
    (60000, "EUR", "Finance Director"),
    (50000, "EUR", "Department Head"),        # inclusive upper bound
    (50000.01, "EUR", "Finance Director"),
    (5000, "EUR", "Cost Center Owner"),
    (45000, "GBP", "Finance Director"),       # 52,650 EUR after conversion
    (300000, "EUR", "CFO + Procurement Excellence review"),
])
def test_approval_bands_come_from_policy(ds, policy, amount, currency, approver):
    out = execute_tool("approval_requirement", {"amount": amount, "currency": currency}, ds, policy)
    assert out.for_model["required_approver"] == approver
    assert out.policy_ids == ["3"]


def test_invalid_args_raise_tool_error(ds, policy):
    with pytest.raises(ToolError, match="Invalid arguments"):
        execute_tool("approval_requirement", {"amount": -5}, ds, policy)


def test_tool_definitions_are_valid_objects():
    for t in tool_definitions():
        assert t["input_schema"]["type"] == "object"
