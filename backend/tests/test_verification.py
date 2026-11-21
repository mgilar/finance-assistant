from app.policy import load_policy
from app.verification import (
    collect_known_numbers, extract_figures, unverified_figures, validate_citations,
)


def test_ids_dates_and_policy_refs_are_not_figures():
    text = "INV-20029 on 2025-11-13 under §3.1 in 2025 via PO-78935 for CC-IT-550"
    assert extract_figures(text) == []


def test_abbreviations_are_scaled():
    assert extract_figures("EUR 1.13M and 52.6k") == [("1.13M", 1_130_000.0), ("52.6k", 52_600.0)]


def test_rounded_figures_match_within_tolerance():
    known = collect_known_numbers({"eur_approx": 1132677.97})
    assert unverified_figures("about EUR 1.13M, or 1,132,678", known) == []
    assert unverified_figures("about EUR 1.25M", known) == ["1.25M"]


def test_credit_notes_match_by_absolute_value():
    known = collect_known_numbers({"amount": -52749.39})
    assert unverified_figures("a credit note of 52,749.39", known) == []


def test_citation_validation():
    valid, unknown = validate_citations(["§3", "3.1", "3", "12.9"], load_policy())
    assert valid == ["3", "3.1"] and unknown == ["12.9"]
