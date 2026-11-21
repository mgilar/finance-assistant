"""/ask tests: stub mode end to end, and LLM mode with a scripted fake Claude client."""

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import app.llm as llm
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def ask(client, q):
    return client.post("/ask", json={"question": q})


# ---------- stub mode ----------

def test_stub_top_vendors(client):
    r = ask(client, "What are our top 5 vendors by total spend in 2025?")
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "stub" and body["model"] is None
    assert body["status"] == "answered"
    assert body["sources_used"] == ["data", "policy"]          # §4.1 cited: an INACTIVE vendor is in the top 5
    assert "PharmaPrint Studios (INACTIVE)" in body["answer"]
    assert body["data_evidence"][0]["rows_scanned"] == 140
    assert body["unverified_figures"] == []
    assert any("approximate fixed rates" in c for c in body["caveats"])


def test_stub_spain(client):
    body = ask(client, "What is our total spend with vendors based in Spain?").json()
    assert body["status"] == "answered"
    assert body["data_evidence"][0]["filters_applied"] == "country in ['Spain']"
    assert body["unverified_figures"] == []


def test_stub_approval_cites_policy_table(client):
    body = ask(client, "Who is allowed to approve an invoice of EUR 60,000?").json()
    assert "Finance Director" in body["answer"]
    assert [c["id"] for c in body["policy_citations"]] == ["3"]
    assert body["sources_used"] == ["policy"]
    assert body["policy_version"].startswith("FIN-POL-014 v3.2")


def test_stub_unknown_question_is_cannot_answer_not_error(client):
    r = ask(client, "What's the weather in Madrid?")
    assert r.status_code == 200
    assert r.json()["status"] == "cannot_answer"


def test_empty_question_is_typed_422(client):
    r = ask(client, "")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert r.json()["request_id"] == r.headers["X-Request-ID"]


# ---------- LLM mode with a fake client ----------

def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def final(**answer):
    base = {"status": "answered", "policy_citation_ids": [], "gaps": [], "routing_reason": "r"}
    text = json.dumps({**base, **answer})
    return SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5",
                           content=[SimpleNamespace(type="text", text=text)])


def tool_turn(*blocks):
    return SimpleNamespace(stop_reason="tool_use", model="claude-sonnet-5-5", content=list(blocks))


@pytest.fixture
def fake_claude(monkeypatch):
    """Install a scripted Claude: pass a list of responses (or exceptions)."""
    calls = []

    def install(script):
        responses = iter(script)

        def create(**kwargs):
            calls.append(kwargs)
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

        fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        monkeypatch.setattr(llm.anthropic, "Anthropic", lambda: fake)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        return calls

    with TestClient(app) as c:
        yield c, install


def test_llm_happy_path_with_validated_citation(fake_claude):
    client, install = fake_claude
    install([
        tool_turn(tool_use("t1", "approval_requirement", {"amount": 60000, "currency": "EUR"})),
        final(answer="A EUR 60,000 invoice needs the Finance Director.", policy_citation_ids=["3"]),
    ])
    body = ask(client, "Who approves EUR 60,000?").json()
    assert body["mode"] == "llm" and body["model"] == "claude-sonnet-5-5"
    assert body["status"] == "answered"
    assert [c["id"] for c in body["policy_citations"]] == ["3"]
    assert "Finance Director" in body["policy_citations"][0]["text"]


def test_llm_failed_tool_goes_back_as_is_error_and_stays_in_lineage(fake_claude):
    client, install = fake_claude
    calls = install([
        tool_turn(tool_use("t1", "aggregate_spend", {"filters": {"vendor_countries": ["España"]}})),
        tool_turn(tool_use("t2", "aggregate_spend", {"filters": {"vendor_countries": ["Spain"]}})),
        final(answer="Spain spend is approx. EUR 2,639,451."),
    ])
    body = ask(client, "Spend in Spain?").json()
    # messages = [question, assistant turn 1, tool results 1, ...]; the list keeps growing,
    # so index the first tool-result message explicitly.
    sent_result = calls[1]["messages"][2]["content"][0]
    assert sent_result["is_error"] is True and "Valid values" in sent_result["content"]
    assert [e["ok"] for e in body["data_evidence"]] == [False, True]
    assert body["status"] == "answered" and body["unverified_figures"] == []


def test_llm_invented_figure_and_fake_citation_downgrade_to_partial(fake_claude):
    client, install = fake_claude
    install([
        tool_turn(tool_use("t1", "aggregate_spend", {"filters": {"vendor_countries": ["Spain"]}})),
        final(answer="Spain spend is EUR 3,100,000.", policy_citation_ids=["4.1", "12.9"]),
    ])
    body = ask(client, "Spend in Spain?").json()
    assert body["status"] == "partial"
    assert body["unverified_figures"] == ["3,100,000"]
    assert [c["id"] for c in body["policy_citations"]] == ["4.1"]
    assert any("12.9" in g for g in body["gaps"])


def test_model_gap_note_does_not_downgrade_a_verified_answer(fake_claude):
    client, install = fake_claude
    install([
        tool_turn(tool_use("t1", "approval_requirement", {"amount": 60000, "currency": "EUR"})),
        final(answer="The Finance Director.", policy_citation_ids=["3"],
              gaps=["No approver roles in the data."]),
    ])
    body = ask(client, "Who approves EUR 60,000?").json()
    assert body["status"] == "answered"                # model's status stands
    assert body["gaps"] == ["No approver roles in the data."]  # but the note is still shown


def test_llm_failure_is_503_without_stub_fallback(fake_claude):
    client, install = fake_claude
    install([anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))])
    r = ask(client, "What are our top 5 vendors?")
    assert r.status_code == 503
    assert r.json()["error"] == {"code": "llm_unavailable", "message": "Could not reach the LLM API.",
                                 "retryable": True}


def test_llm_tool_loop_ends_with_forced_answer_from_gathered_evidence(fake_claude):
    client, install = fake_claude
    loop = tool_turn(tool_use("t", "approval_requirement", {"amount": 60000, "currency": "EUR"}))
    calls = install([loop] * llm.MAX_TOOL_ROUNDS
                    + [final(answer="Finance Director.", policy_citation_ids=["3"])])
    body = ask(client, "loop forever").json()
    assert calls[-1]["tool_choice"] == {"type": "none"}          # last round: tools disabled
    assert all(c["tool_choice"] == {"type": "auto"} for c in calls[:-1])
    assert body["status"] == "partial"                            # downgraded, not discarded
    assert any("Tool-call limit" in g for g in body["gaps"])
    assert len(body["data_evidence"]) == llm.MAX_TOOL_ROUNDS


def test_tool_loop_is_unconstrained_and_valid_json_draft_is_used_directly(fake_claude):
    client, install = fake_claude
    calls = install([
        tool_turn(tool_use("t1", "approval_requirement", {"amount": 60000, "currency": "EUR"})),
        final(answer="Finance Director.", policy_citation_ids=["3"]),
    ])
    body = ask(client, "Who approves EUR 60,000?").json()
    assert len(calls) == 2                                        # no extra structuring call
    assert all("format" not in c["output_config"] for c in calls)  # format never constrains the loop
    assert body["status"] == "answered"


def test_prose_draft_triggers_one_structuring_call(fake_claude):
    client, install = fake_claude
    prose = SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5",
                            content=[SimpleNamespace(type="text", text="The Finance Director approves it.")])
    calls = install([
        tool_turn(tool_use("t1", "approval_requirement", {"amount": 60000, "currency": "EUR"})),
        prose,
        final(answer="The Finance Director approves it.", policy_citation_ids=["3"]),
    ])
    body = ask(client, "Who approves EUR 60,000?").json()
    assert len(calls) == 3
    assert calls[-1]["output_config"]["format"]["type"] == "json_schema"
    assert calls[-1]["tool_choice"] == {"type": "none"}
    assert body["answer"] == "The Finance Director approves it." and body["status"] == "answered"


def test_json_inside_prose_draft_is_used_without_structuring_call(fake_claude):
    client, install = fake_claude
    payload = json.dumps({"status": "answered", "answer": "Finance Director.", "policy_citation_ids": ["3"],
                          "gaps": [], "routing_reason": "r"})
    draft = SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(
        type="text", text=f"Here is the ranking {{see §3}}.\n\n```json\n{payload}\n```")])
    calls = install([tool_turn(tool_use("t1", "approval_requirement", {"amount": 60000})), draft])
    body = ask(client, "Who approves EUR 60,000?").json()
    assert len(calls) == 2 and body["answer"] == "Finance Director."


def test_invalid_final_after_structuring_is_503(fake_claude):
    client, install = fake_claude
    bad = SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(type="text", text="not json")])
    install([bad, bad])
    r = ask(client, "anything")
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"


def test_system_prompt_has_explicit_cache_breakpoint(fake_claude):
    client, install = fake_claude
    calls = install([final(answer="ok", status="cannot_answer")])
    ask(client, "hello")
    assert calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
