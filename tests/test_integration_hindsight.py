"""Opt-in test against a REAL Hindsight server. Skipped unless HINDSIGHT_INTEGRATION=1.

    HINDSIGHT_INTEGRATION=1 pytest tests/test_integration_hindsight.py -s

Uses a throwaway bank (postmortem-it-<random>) and deletes it afterwards.
Hindsight extracts facts with its own LLM, so recall is polled for a while.
"""

import os
import time
import uuid

import pytest

from app.config import Settings
from app.memory.service import MemoryService
from app.models import IncidentInput, OutcomeInput

pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("HINDSIGHT_INTEGRATION") != "1", reason="set HINDSIGHT_INTEGRATION=1")
def test_retain_then_recall_roundtrip():
    from hindsight_client import Hindsight

    settings = Settings.from_env()
    assert settings.hindsight_base_url, "HINDSIGHT_BASE_URL must be set"
    client = Hindsight(
        base_url=settings.hindsight_base_url,
        api_key=settings.hindsight_api_key,
        timeout=settings.hindsight_timeout,
    )
    svc = MemoryService(client, f"postmortem-it-{uuid.uuid4().hex[:8]}")
    incident = IncidentInput(
        title="zorbix-gateway connection pool exhausted",
        service="zorbix-gateway",
        description="Gateway returns 502 under load",
        symptoms="Pool wait timeouts to cache cluster",
        logs="ERROR pool wait timeout (max_connections=50)",
    )
    try:
        svc.retain_incident("IT-1", incident)
        svc.retain_outcomes(
            "IT-1",
            incident,
            [
                (
                    OutcomeInput(action_id="a1", result="failed", notes="restart only masked it"),
                    "Restart zorbix-gateway",
                ),
                (
                    OutcomeInput(action_id="a2", result="worked", notes="raised pool size"),
                    "Raise zorbix-gateway pool max_connections",
                ),
            ],
        )
        found = []
        for _ in range(12):
            found = svc.recall_for_incident(incident)
            if any("zorbix" in m.text.lower() for m in found):
                break
            time.sleep(5)
        assert any("zorbix" in m.text.lower() for m in found), "retained facts were not recalled"
        print("RECALLED:", [(m.text[:80], m.tags, m.outcome) for m in found])
    finally:
        client.delete_bank(bank_id=svc.bank_id)
