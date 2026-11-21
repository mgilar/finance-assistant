"""Post-answer checks, independent of which mode (LLM or stub) produced the answer.

1. Citation validation: the model may only cite policy unit ids that exist.
2. Number check: every figure in the answer must appear in the evidence (tool
   results, cited policy text, FX rates) or in the question. A mismatch doesn't
   block the answer; it's flagged and the status is downgraded to "partial".
"""

import json
import re
from typing import Any

from app.policy import Policy

# Identifiers and dates contain digits but aren't figures: remove them before scanning.
_NOT_FIGURES = re.compile(
    r"§\s?\d+(?:\.\d+)?"                 # policy references (§3.1)
    r"|\b[A-Z]{1,4}-[A-Z]*-?\d+\b"       # INV-20029, PO-78935, V-1006, CC-IT-550
    r"|\b\d{4}-\d{2}(?:-\d{2})?\b"       # dates, months
    r"|\b(?:19|20)\d{2}\b"               # years
)
_FIGURE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*([kKmM])?(?![\w])")
_SCALE = {"k": 1e3, "m": 1e6}
_REL_TOLERANCE = 0.005  # 0.5%: allows "EUR 1.13M" for 1,132,677.97


def validate_citations(cited_ids: list[str], policy: Policy) -> tuple[list[str], list[str]]:
    """Return (valid ids in order, unknown ids). Accepts '3.1' or '§3.1'."""
    valid, unknown = [], []
    for raw in cited_ids:
        uid = raw.strip().lstrip("§").strip()
        if uid in policy.units:
            if uid not in valid:
                valid.append(uid)
        else:
            unknown.append(raw)
    return valid, unknown


def extract_figures(text: str) -> list[tuple[str, float]]:
    cleaned = _NOT_FIGURES.sub(" ", text)
    figures = []
    for m in _FIGURE.finditer(cleaned):
        value = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        if m.group(3):
            value *= _SCALE[m.group(3).lower()]
        figures.append((m.group(0).strip(), value))
    return figures


def collect_known_numbers(*sources: Any) -> set[float]:
    """Every number found in tool results, policy text, the question, etc."""
    known: set[float] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, (int, float)):
            known.add(abs(float(obj)))
        elif isinstance(obj, str):
            known.update(abs(v) for _, v in extract_figures(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, (list, tuple, set)):
            for v in obj:
                walk(v)
        else:
            walk(json.loads(json.dumps(obj, default=str)))

    for s in sources:
        walk(s)
    return known


def unverified_figures(answer: str, known: set[float]) -> list[str]:
    missing = []
    for label, value in extract_figures(answer):
        value = abs(value)
        if value < 10 and float(value).is_integer():
            continue  # small counts/ordinals ("top 5", "3 vendors") are too ambiguous to check
        if not any(abs(value - k) <= max(_REL_TOLERANCE * k, 0.01) for k in known):
            missing.append(label)
    return missing
