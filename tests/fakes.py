"""TEST DOUBLES. These stand in for the Hindsight SDK client and the LLM so the app's own
logic can be tested offline. They are NOT Hindsight and prove nothing about Hindsight itself;
see tests/test_integration_hindsight.py for the opt-in test against a real server."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any


class FakeHindsightClient:
    """Mimics the SDK call surface used by MemoryService (keyword arguments, same names)."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = False
        self.bank_deleted = False

    def _maybe_fail(self) -> None:
        if self.fail:
            raise ConnectionError("hindsight down")

    def create_bank(self, **kw: Any) -> None:
        self._maybe_fail()
        self.calls.append(("create_bank", kw))

    def get_version(self) -> Any:
        self._maybe_fail()
        return SimpleNamespace(api_version="test")

    def retain(self, **kw: Any) -> None:
        self._maybe_fail()
        self.calls.append(("retain", kw))
        self.docs[kw["document_id"]] = kw

    def retain_batch(self, **kw: Any) -> None:
        self._maybe_fail()
        self.calls.append(("retain_batch", kw))
        for item in kw["items"]:
            self.docs[item["document_id"]] = item

    def recall(self, **kw: Any) -> Any:
        self._maybe_fail()
        self.calls.append(("recall", kw))
        words = set(re.findall(r"[a-z0-9\-]{4,}", kw["query"].lower()))
        results = []
        for doc_id, doc in self.docs.items():
            overlap = words & set(re.findall(r"[a-z0-9\-]{4,}", doc["content"].lower()))
            if len(overlap) >= 3:
                results.append(
                    SimpleNamespace(
                        id=doc_id,
                        text=doc["content"],
                        type="experience",
                        context=doc.get("context"),
                        tags=doc.get("tags"),
                        scores=SimpleNamespace(final=len(overlap) / 10),
                        occurred_start=None,
                        mentioned_at=None,
                    )
                )
        return SimpleNamespace(results=results)

    def list_memories(self, **kw: Any) -> Any:
        self._maybe_fail()
        items = [
            SimpleNamespace(
                id=k,
                text=v["content"],
                fact_type="experience",
                context=v.get("context"),
                tags=v.get("tags"),
                mentioned_at=None,
                var_date=None,
            )
            for k, v in self.docs.items()
        ]
        return SimpleNamespace(items=items, total=len(items))

    def delete_bank(self, **kw: Any) -> None:
        self._maybe_fail()
        self.bank_deleted = True
        self.docs.clear()


class ScriptedLLM:
    """Returns a canned plan. Records the prompts it was given."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        self.prompts.append(user)
        if self.payload is not None:
            return self.payload
        # Behaves like a model that obeys the prompt: if memory marks "restart" as FAILED,
        # it still lists it first (worst case) so the guard has to demote it.
        failed_ref = next(
            (
                m.split(" ")[0].rstrip(":")
                for m in user.splitlines()
                if "recorded outcome: FAILED" in m
            ),
            None,
        )
        worked_ref = next(
            (
                m.split(" ")[0].rstrip(":")
                for m in user.splitlines()
                if "recorded outcome: WORKED" in m
            ),
            None,
        )
        restart_ev = (
            [{"ref": failed_ref, "stance": "supports", "note": "Restart masked it before."}]
            if failed_ref
            else []
        )
        pool_ev = (
            [{"ref": worked_ref, "stance": "supports", "note": "Pool limit fixed it before."}]
            if worked_ref
            else []
        )
        return {
            "summary": "Likely Redis pool saturation.",
            "actions": [
                {
                    "title": "Restart payments-api pods",
                    "rationale": "Quick relief.",
                    "risk": "low",
                    "evidence": restart_ev,
                },
                {
                    "title": "Check Redis pool metrics",
                    "rationale": "Confirm saturation.",
                    "risk": "low",
                    "evidence": [],
                },
                {
                    "title": "Raise Redis client max_connections",
                    "rationale": "Pool is full.",
                    "risk": "medium",
                    "evidence": pool_ev,
                },
            ],
        }
