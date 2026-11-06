import pytest

from app.memory.service import MemoryService, MemoryUnavailableError
from app.models import IncidentInput, OutcomeInput
from tests.fakes import FakeHindsightClient

INC = IncidentInput(
    title="payments-api Redis timeouts",
    service="payments-api",
    description="Checkout failing intermittently",
    symptoms="502s and Redis timeouts",
    logs="ERROR redis timeout",
)


def make():
    client = FakeHindsightClient()
    return client, MemoryService(client, "bank-1")


def test_retain_incident_uses_bank_tags_and_document_id():
    client, svc = make()
    svc.retain_incident("INC-1001", INC)
    kind, kw = client.calls[-1]
    assert kind == "retain" and kw["bank_id"] == "bank-1"
    assert kw["document_id"] == "INC-1001:report"
    assert "service:payments-api" in kw["tags"] and "incident" in kw["tags"]
    assert any(c[0] == "create_bank" for c in client.calls)  # bank ensured first


def test_not_tried_is_never_retained():
    client, svc = make()
    outcomes = [
        (OutcomeInput(action_id="a1", result="failed", notes="came back"), "Restart pods"),
        (OutcomeInput(action_id="a2", result="not_tried"), "Check metrics"),
        (OutcomeInput(action_id="a3", result="worked"), "Raise pool"),
    ]
    assert svc.retain_outcomes("INC-1001", INC, outcomes) == 2
    ids = set(client.docs)
    assert ids == {"INC-1001:outcome:a1", "INC-1001:outcome:a3"}
    assert "result:failed" in client.docs["INC-1001:outcome:a1"]["tags"]


def test_only_not_tried_makes_no_call():
    client, svc = make()
    assert (
        svc.retain_outcomes("INC-1", INC, [(OutcomeInput(action_id="a1", result="not_tried"), "x")])
        == 0
    )
    assert not client.calls


def test_resubmitting_same_action_overwrites_not_duplicates():
    client, svc = make()
    svc.retain_outcomes("INC-1", INC, [(OutcomeInput(action_id="a1", result="failed"), "Restart")])
    svc.retain_outcomes("INC-1", INC, [(OutcomeInput(action_id="a1", result="worked"), "Restart")])
    assert len(client.docs) == 1
    assert "result:worked" in client.docs["INC-1:outcome:a1"]["tags"]


def test_recall_maps_results_and_outcome_from_tags():
    client, svc = make()
    svc.retain_outcomes(
        "INC-1", INC, [(OutcomeInput(action_id="a1", result="failed"), "Restart payments-api pods")]
    )
    memories = svc.recall_for_incident(INC)
    assert memories and memories[0].outcome == "failed"
    assert memories[0].score is not None


def test_recall_empty_bank_returns_empty_list():
    _, svc = make()
    assert svc.recall_for_incident(INC) == []


def test_hindsight_failure_is_normalised():
    client, svc = make()
    client.fail = True
    with pytest.raises(MemoryUnavailableError):
        svc.recall_for_incident(INC)
    with pytest.raises(MemoryUnavailableError):
        svc.health()


def test_list_memories_and_reset():
    client, svc = make()
    svc.retain_incident("INC-1", INC)
    assert svc.list_memories()["total"] == 1
    svc.reset()
    assert client.bank_deleted and svc.list_memories()["total"] == 0


def test_recall_falls_back_to_text_when_hindsight_drops_tags():
    from types import SimpleNamespace

    client, svc = make()
    stripped = SimpleNamespace(
        id="f1",
        text="The troubleshooting action 'Restart payments-api pods' FAILED.",
        type="experience",
        context=None,
        tags=None,
        scores=None,
        occurred_start=None,
        mentioned_at=None,
    )
    client.recall = lambda **kw: SimpleNamespace(results=[stripped])
    assert svc.recall_for_incident(INC)[0].outcome == "failed"
