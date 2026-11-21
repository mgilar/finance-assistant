"""POST /ask orchestration: pick the mode, run it, then post-process the same way for both.

The backend owns the evidence:
  - data evidence   = the tool calls that actually ran (failed ones included)
  - policy evidence = validated citation ids + verbatim text from the parsed policy
  - sources_used    = derived from what happened, not from what the model claims
"""

import logging

from app.answer import RawAnswer
from app.data import FX_TO_EUR, Dataset
from app.llm import llm_configured, run_claude
from app.policy import Policy
from app.schemas import AskResponse, PolicyCitation
from app.stub import run_stub
from app.verification import collect_known_numbers, unverified_figures, validate_citations

logger = logging.getLogger("finance_assistant")

DATA_TOOLS = {"aggregate_spend", "find_invoices"}


def answer_question(question: str, ds: Dataset, policy: Policy, request_id: str) -> AskResponse:
    # No silent fallback: if a key is configured and Claude fails, LLMUnavailable propagates (503).
    if llm_configured():
        mode, raw = "llm", run_claude(question, ds, policy)
    else:
        mode, raw = "stub", run_stub(question, ds, policy)
    response = postprocess(raw, mode, question, ds, policy, request_id)
    logger.info("ask [%s] mode=%s status=%s tools=%s citations=%s unverified=%s", request_id,
                mode, response.status, [e.tool for e in response.data_evidence],
                [c.id for c in response.policy_citations], response.unverified_figures)
    return response


def postprocess(raw: RawAnswer, mode: str, question: str, ds: Dataset, policy: Policy,
                request_id: str) -> AskResponse:
    status, gaps = raw.status, list(raw.gaps)

    # 1. Policy citations: keep only ids that exist; attach verbatim text. Tools that rely on
    #    a clause (approval_requirement -> §3) cite it automatically.
    tool_policy_ids = [pid for o in raw.outcomes if o.evidence.ok for pid in o.policy_ids]
    valid_ids, unknown_ids = validate_citations(raw.policy_citation_ids + tool_policy_ids, policy)
    if unknown_ids:
        gaps.append(f"The model cited policy sections that do not exist {unknown_ids}; they were removed.")
    citations = [PolicyCitation(id=u.id, title=u.title, text=u.text)
                 for u in (policy.units[i] for i in valid_ids)]

    # 2. Number check: figures in the answer must appear in the evidence or the question.
    known = collect_known_numbers(
        [o.for_model for o in raw.outcomes], [c.text for c in citations], question,
        list(FX_TO_EUR.values()),
    )
    unverified = unverified_figures(raw.answer, known)
    if unverified:
        gaps.append(f"These figures could not be matched to the evidence: {', '.join(unverified)}.")

    # The model's own status stands; the backend downgrades only on facts it verified itself.
    # (Model-listed gaps are still shown, but a context note shouldn't turn a correct answer amber.)
    if status == "answered" and (unknown_ids or unverified):
        status = "partial"

    # 3. Routing transparency from facts.
    ran = {o.evidence.tool for o in raw.outcomes if o.evidence.ok}
    sources = (["data"] if ran & DATA_TOOLS else []) + (["policy"] if citations else [])

    # 4. Caveats come from the tools that ran (FX, credit notes, status snapshot), deduplicated.
    caveats = list(dict.fromkeys(c for o in raw.outcomes if o.evidence.ok for c in o.caveats))

    return AskResponse(
        request_id=request_id,
        status=status,
        answer=raw.answer,
        sources_used=sources,
        policy_citations=citations,
        data_evidence=[o.evidence for o in raw.outcomes],
        routing_reason=raw.routing_reason,
        caveats=caveats,
        gaps=gaps,
        unverified_figures=unverified,
        mode=mode,
        model=raw.model,
        policy_version=policy.label,
        data_sources=list(ds.sources),
    )
