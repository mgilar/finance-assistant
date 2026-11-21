"""What an answering mode (Claude or stub) hands back before post-processing."""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from app.data import Dataset
from app.policy import Policy
from app.tools import ToolError, ToolOutcome, execute_tool, failed_outcome

logger = logging.getLogger("finance_assistant")

Status = Literal["answered", "partial", "cannot_answer"]


@dataclass
class RawAnswer:
    status: Status
    answer: str
    policy_citation_ids: list[str]
    gaps: list[str]
    routing_reason: str
    outcomes: list[ToolOutcome] = field(default_factory=list)  # every tool call, failed ones too
    model: str | None = None


def run_tool_safely(name: str, args: dict[str, Any], ds: Dataset, policy: Policy) -> ToolOutcome:
    """Run a tool; any failure becomes a recorded failed outcome, never a value."""
    try:
        return execute_tool(name, args, ds, policy)
    except ToolError as exc:
        return failed_outcome(name, args, str(exc))
    except Exception:  # a bug in a tool must not crash the request or invent a number
        logger.exception("Tool %s crashed", name)
        return failed_outcome(name, args, "Internal tool error; this figure could not be computed.")
