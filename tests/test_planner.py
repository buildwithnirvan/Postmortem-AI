import json

import httpx
import pytest

from app.agent.llm import GroqClient, LLMUnavailableError, extract_json
from app.agent.planner import PlanGenerationError, generate_plan
from app.models import IncidentInput, RecalledMemory
from tests.fakes import ScriptedLLM

INC = IncidentInput(
    title="payments-api Redis timeouts",
    service="payments-api",
    description="Checkout failing",
    symptoms="502s and Redis timeouts",
)


def mem(id_, text, outcome=None):
    return RecalledMemory(id=id_, text=text, outcome=outcome)


def titles(plan):
    return [a.title for a in plan.actions]


def test_failed_memory_demotes_action_and_corrects_stance():
    memories = [
        mem("m-fail", "Restart FAILED", "failed"),
        mem("m-ok", "Raise pool WORKED", "worked"),
    ]
    plan = generate_plan(INC, memories, ScriptedLLM(), "used")
    assert titles(plan)[0] == "Raise Redis client max_connections"  # worked-backed first
    assert titles(plan)[-1] == "Restart payments-api pods"  # failed-warned last
    restart = plan.actions[-1]
    assert restart.evidence[0].stance == "warns"  # model said supports; corrected
    assert "FAILED" in (restart.rank_reason or "") and restart.warning
    assert [a.id for a in plan.actions] == ["a1", "a2", "a3"]


def test_without_memory_order_is_unchanged():
    plan = generate_plan(INC, [], ScriptedLLM(), "empty")
    assert titles(plan)[0] == "Restart payments-api pods"
    assert all(a.rank_reason is None for a in plan.actions)


def test_hallucinated_refs_are_dropped():
    payload = {
        "summary": "s",
        "actions": [
            {"title": "A", "rationale": "r", "evidence": [{"ref": "M99", "stance": "supports"}]}
        ],
    }
    plan = generate_plan(INC, [mem("x", "t")], ScriptedLLM(payload), "used")
    assert plan.actions[0].evidence == []


def test_memories_are_labelled_in_prompt_and_untrusted_text_is_redacted():
    llm = ScriptedLLM()
    generate_plan(INC, [mem("x", "Restart FAILED password=abc", "failed")], llm, "used")
    assert "M1 [recorded outcome: FAILED]" in llm.prompts[0]
    assert "abc" not in llm.prompts[0]


def test_bad_plan_shape_raises():
    with pytest.raises(PlanGenerationError):
        generate_plan(INC, [], ScriptedLLM({"summary": "x", "actions": []}), "empty")


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("no json here")


def _client(handler, attempts=3):
    return GroqClient(
        "key", "m", "http://x/v1", transport=httpx.MockTransport(handler), max_attempts=attempts
    )


def _ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_llm_retries_invalid_json_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    replies = iter([_ok("not json"), _ok(json.dumps({"ok": True}))])
    assert _client(lambda req: next(replies)).chat_json("s", "u") == {"ok": True}


def test_llm_gives_up_with_clear_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(LLMUnavailableError, match="after 2 attempts"):
        _client(lambda req: httpx.Response(429), attempts=2).chat_json("s", "u")


def test_llm_bad_key_fails_fast():
    with pytest.raises(LLMUnavailableError, match="rejected"):
        _client(lambda req: httpx.Response(401)).chat_json("s", "u")


def test_llm_missing_key():
    with pytest.raises(LLMUnavailableError, match="not configured"):
        GroqClient(None, "m", "http://x").chat_json("s", "u")
