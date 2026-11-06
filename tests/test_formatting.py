from app.memory.formatting import (
    build_recall_query,
    format_incident_memory,
    format_outcome_memory,
    log_signature,
    outcome_from_tags,
    redact,
    service_slug,
    tags_for_outcome,
)
from app.models import IncidentInput

INC = IncidentInput(
    title="payments-api 502s",
    service="Payments API",
    description="Checkout failing",
    symptoms="502s and Redis timeouts",
    logs="INFO started\nERROR redis timeout\nINFO ok\nWARN pool wait timeout",
)


def test_redacts_secrets_and_emails():
    text = "password=hunter2 key AKIAABCDEFGHIJKLMNOP mail bob@corp.com Authorization: Bearer abcdefghijklmnop12345"
    out = redact(text)
    assert "hunter2" not in out and "AKIA" not in out and "bob@corp.com" not in out
    assert "abcdefghijklmnop12345" not in out


def test_service_slug_and_tags():
    assert service_slug("Payments API") == "payments-api"
    assert tags_for_outcome("Payments API", "failed") == [
        "outcome",
        "service:payments-api",
        "result:failed",
    ]


def test_outcome_from_tags_roundtrip():
    assert outcome_from_tags(tags_for_outcome("x", "worked")) == "worked"
    assert outcome_from_tags(tags_for_outcome("x", "failed")) == "failed"
    assert outcome_from_tags(["incident"]) is None
    assert outcome_from_tags(None) is None


def test_log_signature_prefers_error_lines():
    sig = log_signature(INC.logs)
    assert "ERROR redis timeout" in sig and "INFO started" not in sig


def test_incident_memory_contains_identifying_details():
    text = format_incident_memory("INC-1001", INC)
    assert "INC-1001" in text and "Payments API" in text and "Redis timeouts" in text


def test_outcome_memory_states_verdict_and_notes_and_redacts():
    text = format_outcome_memory(
        "INC-1001", INC, "Restart pods", "failed", "token=abc123 came back"
    )
    assert "FAILED" in text and "Restart pods" in text and "abc123" not in text


def test_recall_query_mentions_service_and_symptoms():
    q = build_recall_query(INC)
    assert "Payments API" in q and "Redis timeouts" in q


def test_text_fallback_only_when_tags_missing_and_unambiguous():
    from app.memory.formatting import outcome_from_text

    failed = "The troubleshooting action 'Restart pods' failed for payments-api."
    worked = "The action 'Raise pool size' worked and cleared the 502s."
    assert outcome_from_text(failed, []) == "failed"
    assert outcome_from_text(worked, None) == "worked"
    assert outcome_from_text(failed, ["outcome", "result:failed"]) is None  # tags are authoritative
    assert outcome_from_text(failed, ["incident"]) is None  # never infer on reports
    assert outcome_from_text("Restart failed but pool resize worked, action taken.", []) is None
    assert outcome_from_text("Checkout failed with 502s.", []) is None  # no action/outcome word
