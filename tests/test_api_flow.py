"""End-to-end flow through the real FastAPI app with test doubles for Hindsight and the LLM."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.memory.service import MemoryService
from app.storage import Store
from tests.fakes import FakeHindsightClient, ScriptedLLM

BODY = {
    "title": "payments-api 502s with Redis connection timeouts",
    "service": "payments-api",
    "description": "Checkout failing intermittently under load",
    "symptoms": "502s and Redis timeouts",
    "logs": "ERROR redis timeout",
}


@pytest.fixture()
def env(tmp_path):
    hs = FakeHindsightClient()
    settings = Settings(None, None, "bank", 5, "k", "m", "u", str(tmp_path / "t.db"), 1000, "mid")
    app = create_app(settings, MemoryService(hs, "bank"), ScriptedLLM(), Store(settings.db_path))
    return TestClient(app), hs


def test_cold_start_then_learning_changes_plan(env):
    client, hs = env
    first = client.post("/api/incidents", json=BODY).json()
    assert first["plan"]["memory_status"] == "empty"
    assert first["plan"]["actions"][0]["title"] == "Restart payments-api pods"  # generic order
    assert first["incident_retained"] is True and "INC-1001:report" in hs.docs

    outcomes = [
        {"action_id": "a1", "result": "failed", "notes": "Errors returned after 12 min"},
        {"action_id": "a2", "result": "not_tried"},
        {"action_id": "a3", "result": "worked", "notes": "Cleared in 5 min"},
    ]
    saved = client.post(
        f"/api/incidents/{first['incident_id']}/outcomes", json={"outcomes": outcomes}
    ).json()
    assert saved["retained_in_hindsight"] == 2 and saved["skipped_not_tried"] == 1

    second = client.post("/api/incidents", json=BODY).json()["plan"]
    assert second["memory_status"] == "used"
    assert second["actions"][0]["title"] == "Raise Redis client max_connections"
    assert second["actions"][-1]["title"] == "Restart payments-api pods"
    assert second["actions"][-1]["warning"]
    assert second["memories"], "recalled memories must be exposed for the inspector"


def test_memory_off_run_is_baseline_and_retains_nothing(env):
    client, hs = env
    res = client.post("/api/incidents", json={**BODY, "use_memory": False}).json()
    assert res["plan"]["memory_status"] == "disabled" and not hs.docs
    out = client.post(
        f"/api/incidents/{res['incident_id']}/outcomes",
        json={"outcomes": [{"action_id": "a1", "result": "failed"}]},
    ).json()
    assert out["retained_in_hindsight"] == 0 and out["warnings"]


def test_hindsight_down_degrades_gracefully(env):
    client, hs = env
    hs.fail = True
    res = client.post("/api/incidents", json=BODY)
    assert res.status_code == 200
    body = res.json()
    assert body["plan"]["memory_status"] == "unavailable" and body["warnings"]
    assert body["incident_retained"] is False
    assert client.get("/api/health").json()["hindsight"]["ok"] is False
    assert client.get("/api/memories").status_code == 502


def test_validation_errors(env):
    client, _ = env
    assert client.post("/api/incidents", json={**BODY, "title": "x"}).status_code == 422
    assert client.post("/api/incidents", json={**BODY, "service": "   "}).status_code == 422
    assert client.get("/api/incidents/INC-9999").status_code == 404
    res = client.post("/api/incidents", json=BODY).json()
    bad = client.post(
        f"/api/incidents/{res['incident_id']}/outcomes",
        json={"outcomes": [{"action_id": "zzz", "result": "worked"}]},
    )
    assert bad.status_code == 422
    assert (
        client.post(
            f"/api/incidents/{res['incident_id']}/outcomes", json={"outcomes": []}
        ).status_code
        == 422
    )


def test_reset_requires_confirmation_and_seed_loads(env):
    client, hs = env
    assert client.post("/api/memory/reset", json={"confirm": "yes"}).status_code == 422
    seeded = client.post("/api/memory/seed").json()
    assert seeded["incidents"] == 8 and len(hs.docs) == seeded["retained_items"] > 8
    assert client.post("/api/memory/reset", json={"confirm": "RESET"}).status_code == 200
    assert not hs.docs


def test_llm_failure_returns_502_not_a_fake_plan(tmp_path):
    from app.agent.llm import GroqClient

    settings = Settings(None, None, "bank", 5, None, "m", "u", str(tmp_path / "t.db"), 1000, "mid")
    app = create_app(
        settings,
        MemoryService(FakeHindsightClient(), "bank"),
        GroqClient(None, "m", "http://x"),
        Store(settings.db_path),
    )
    res = TestClient(app).post("/api/incidents", json=BODY)
    assert res.status_code == 502 and "LLM unavailable" in res.json()["detail"]


def test_no_hindsight_configured(tmp_path):
    settings = Settings(None, None, "bank", 5, "k", "m", "u", str(tmp_path / "t.db"), 1000, "mid")
    client = TestClient(create_app(settings, None, ScriptedLLM(), Store(settings.db_path)))
    res = client.post("/api/incidents", json=BODY).json()
    assert res["plan"]["memory_status"] == "unavailable"
    assert client.get("/api/health").json()["hindsight"]["configured"] is False
    assert client.get("/").status_code == 200
