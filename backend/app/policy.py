"""Policy layer: parse procurement_policy.md into citable units.

The whole policy (about 50 lines) goes into the LLM context, so there's no retrieval step.
Parsing it into units with stable IDs lets the model cite "§3.1", and lets the
backend validate that citation and attach the verbatim text itself.

Unit IDs:
  - numbered clauses -> "2.1", "3.1", ...
  - text directly under a section heading (e.g. the §1 paragraph, the §3
    threshold table) -> the section number, "1", "3"
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.data import DATA_DIR

POLICY_FILE = "procurement_policy.md"

_SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+)$")
_CLAUSE_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")
_META_RE = re.compile(
    r"\*\*Document ID:\*\*\s*(?P<doc_id>[\w-]+).*\*\*Version:\*\*\s*(?P<version>[\d.]+)"
    r".*\*\*Effective:\*\*\s*(?P<effective>[\w-]+)"
)


@dataclass(frozen=True)
class PolicyUnit:
    id: str
    title: str  # section title, e.g. "Approval Thresholds"
    text: str


@dataclass(frozen=True)
class Policy:
    doc_id: str
    version: str
    effective: str
    units: dict[str, PolicyUnit]  # id -> unit, in document order
    source: str

    @property
    def label(self) -> str:
        return f"{self.doc_id} v{self.version} (effective {self.effective})"

    def render_for_prompt(self) -> str:
        """Policy text with an explicit [§id] tag per unit: the only IDs the model may cite."""
        lines = [f"Policy {self.label}"]
        for u in self.units.values():
            lines.append(f"[§{u.id}] ({u.title}) {u.text}")
        return "\n".join(lines)


class PolicyParseError(Exception):
    pass


def load_policy(data_dir: Path = DATA_DIR) -> Policy:
    raw = (data_dir / POLICY_FILE).read_text(encoding="utf-8")

    meta = _META_RE.search(raw)
    if not meta:
        raise PolicyParseError("Policy header (Document ID / Version / Effective) not found")

    units: dict[str, PolicyUnit] = {}
    section_id, section_title = None, None
    section_body: list[str] = []

    def flush_section_body() -> None:
        if section_id and section_body:
            units[section_id] = PolicyUnit(section_id, section_title, "\n".join(section_body))

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("# ") or line.startswith("**Document ID"):
            continue
        if m := _SECTION_RE.match(line):
            flush_section_body()
            section_id, section_title, section_body = m.group(1), m.group(2), []
        elif m := _CLAUSE_RE.match(line):
            units[m.group(1)] = PolicyUnit(m.group(1), section_title, m.group(2))
        elif section_id:
            section_body.append(line)  # section intro text or table rows
    flush_section_body()

    if not units:
        raise PolicyParseError("No policy units parsed")

    # Keep document order: sort ids numerically ("3" before "3.1" before "4").
    ordered = dict(sorted(units.items(), key=lambda kv: [int(p) for p in kv[0].split(".")]))
    return Policy(meta["doc_id"], meta["version"], meta["effective"], ordered,
                  source=f"data/{POLICY_FILE}")
