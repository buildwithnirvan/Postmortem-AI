"""The ONLY module that talks to Hindsight.

Memory lifecycle (see README for the diagram):
  RETAIN  1. incident opened       -> incident report (tags: incident, service:<x>)
          2. outcome confirmed     -> one memory per worked/failed action
                                      (tags: outcome, service:<x>, result:<worked|failed>)
  RECALL  3. new incident arrives  -> semantic recall BEFORE planning (and before the new
                                      incident is retained, so it can't recall itself)
  INSPECT 4. list_memories()       -> memory inspector page
  RESET   5. reset()               -> deletes the bank (explicit user action only)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from app.memory.formatting import (
    build_recall_query,
    format_incident_memory,
    format_outcome_memory,
    outcome_from_tags,
    outcome_from_text,
    tags_for_incident,
    tags_for_outcome,
)
from app.models import IncidentInput, MemoryItem, OutcomeInput, RecalledMemory

RETAIN_MISSION = (
    "This bank stores production incident history for an on-call assistant. Extract: the "
    "affected service, symptoms, error signatures, root cause when stated, each "
    "troubleshooting action verbatim, and whether that action WORKED or FAILED (including "
    "when it only masked the symptom temporarily). Ignore chit-chat."
)


class MemoryUnavailableError(RuntimeError):
    """Hindsight is not configured, unreachable, or returned an error."""


class MemoryService:
    def __init__(
        self, client: Any, bank_id: str, recall_max_tokens: int = 3000, recall_budget: str = "mid"
    ) -> None:
        self._client = client
        self._bank = bank_id
        self._max_tokens = recall_max_tokens
        self._budget = recall_budget
        self._bank_ready = False
        # The SDK's sync wrapper binds its HTTP session to the calling thread's event loop and
        # breaks when called from different threads (FastAPI runs sync routes in a pool).
        # One dedicated worker thread keeps a single loop for the app's lifetime.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hindsight")

    @property
    def bank_id(self) -> str:
        return self._bank

    def _call(self, operation: str, fn: Any, **kwargs: Any) -> Any:
        try:
            return self._executor.submit(lambda: fn(**kwargs)).result()
        except Exception as exc:  # SDK raises many exception types; normalise them here
            raise MemoryUnavailableError(f"Hindsight {operation} failed: {exc}") from exc

    def ensure_bank(self) -> None:
        if self._bank_ready:
            return
        self._call(
            "create_bank",
            self._client.create_bank,
            bank_id=self._bank,
            retain_mission=RETAIN_MISSION,
        )
        self._bank_ready = True

    def health(self) -> str:
        """Returns the Hindsight API version string; raises MemoryUnavailableError."""
        version = self._call("get_version", self._client.get_version)
        return str(getattr(version, "api_version", "unknown"))

    # ---- retain -------------------------------------------------------------------------
    def retain_incident(
        self, incident_id: str, incident: IncidentInput, when: datetime | None = None
    ) -> None:
        self.ensure_bank()
        self._call(
            "retain",
            self._client.retain,
            bank_id=self._bank,
            content=format_incident_memory(incident_id, incident),
            context="Incident report",
            document_id=f"{incident_id}:report",
            tags=tags_for_incident(incident.service),
            timestamp=when or datetime.now(timezone.utc),
            metadata={"incident_id": incident_id, "kind": "incident"},
        )

    def retain_outcomes(
        self,
        incident_id: str,
        incident: IncidentInput,
        outcomes: list[tuple[OutcomeInput, str]],
    ) -> int:
        """Retain confirmed outcomes. `outcomes` pairs each input with its action title.

        'not_tried' entries are skipped on purpose: they carry no evidence about what works.
        Re-submitting an action overwrites it (same document_id) rather than duplicating.
        Returns the number of memories retained.
        """
        items = [
            {
                "content": format_outcome_memory(
                    incident_id, incident, title, outcome.result, outcome.notes
                ),
                "context": "Confirmed troubleshooting outcome",
                "document_id": f"{incident_id}:outcome:{outcome.action_id}",
                "tags": tags_for_outcome(incident.service, outcome.result),
                "timestamp": datetime.now(timezone.utc),
                "metadata": {
                    "incident_id": incident_id,
                    "kind": "outcome",
                    "result": outcome.result,
                },
            }
            for outcome, title in outcomes
            if outcome.result in ("worked", "failed")
        ]
        if not items:
            return 0
        self.ensure_bank()
        self._call("retain_batch", self._client.retain_batch, bank_id=self._bank, items=items)
        return len(items)

    def retain_batch(self, items: list[dict[str, Any]]) -> int:
        """Used by the seeder to load synthetic history in one request."""
        self.ensure_bank()
        self._call("retain_batch", self._client.retain_batch, bank_id=self._bank, items=items)
        return len(items)

    # ---- recall -------------------------------------------------------------------------
    def recall_for_incident(self, incident: IncidentInput) -> list[RecalledMemory]:
        self.ensure_bank()
        response = self._call(
            "recall",
            self._client.recall,
            bank_id=self._bank,
            query=build_recall_query(incident),
            max_tokens=self._max_tokens,
            budget=self._budget,
        )
        memories: list[RecalledMemory] = []
        for result in getattr(response, "results", None) or []:
            tags = list(getattr(result, "tags", None) or [])
            scores = getattr(result, "scores", None)
            memories.append(
                RecalledMemory(
                    id=result.id,
                    text=result.text,
                    type=getattr(result, "type", None),
                    context=getattr(result, "context", None),
                    tags=tags,
                    score=getattr(scores, "final", None) if scores else None,
                    outcome=outcome_from_tags(tags)  # exact: written by us at retain time
                    or outcome_from_text(result.text, tags),  # type: ignore[arg-type]
                    date=getattr(result, "occurred_start", None)
                    or getattr(result, "mentioned_at", None),
                )
            )
        return memories

    # ---- inspect / reset ------------------------------------------------------------------
    def list_memories(self, query: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        self.ensure_bank()
        response = self._call(
            "list_memories",
            self._client.list_memories,
            bank_id=self._bank,
            search_query=query or None,
            limit=limit,
            offset=offset,
        )
        items = [
            MemoryItem(
                id=item.id,
                text=item.text or "",
                fact_type=getattr(item, "fact_type", None),
                context=getattr(item, "context", None),
                tags=list(getattr(item, "tags", None) or []),
                date=getattr(item, "mentioned_at", None) or getattr(item, "var_date", None),
            )
            for item in getattr(response, "items", [])
        ]
        return {"items": items, "total": getattr(response, "total", len(items))}

    def reset(self) -> None:
        """Delete the whole bank, then recreate it empty. Irreversible."""
        try:
            self._executor.submit(lambda: self._client.delete_bank(bank_id=self._bank)).result()
        except Exception as exc:
            if "not found" not in str(exc).lower() and "404" not in str(exc):
                raise MemoryUnavailableError(f"Hindsight delete_bank failed: {exc}") from exc
        self._bank_ready = False
        self.ensure_bank()
