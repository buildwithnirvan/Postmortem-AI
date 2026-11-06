"""SQLite store for app session state, incidents, outcomes, and reports."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from app.models import IncidentInput, OutcomeInput, Plan

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    memory_enabled INTEGER NOT NULL,
    incident TEXT NOT NULL,
    plan TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    incident_seq INTEGER NOT NULL,
    action_id TEXT NOT NULL,
    result TEXT NOT NULL,
    notes TEXT NOT NULL,
    retained INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (incident_seq, action_id)
);
CREATE TABLE IF NOT EXISTS service_configs (
    name TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    tier INTEGER NOT NULL,
    dependencies TEXT NOT NULL
);
"""

ID_OFFSET = 1000


def _seq(incident_id: str) -> int:
    try:
        return int(incident_id.removeprefix("INC-")) - ID_OFFSET
    except ValueError:
        return -1


class Store:
    def __init__(self, path: str) -> None:
        self._path = path
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_incident(self, incident: IncidentInput, memory_enabled: bool) -> str:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO incidents (created_at, memory_enabled, incident) VALUES (?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    int(memory_enabled),
                    incident.model_dump_json(),
                ),
            )
            return f"INC-{ID_OFFSET + int(cursor.lastrowid or 0)}"

    def save_plan(self, incident_id: str, plan: Plan) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE incidents SET plan = ? WHERE seq = ?",
                (plan.model_dump_json(), _seq(incident_id)),
            )

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        seq = _seq(incident_id)
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM incidents WHERE seq = ?", (seq,)).fetchone()
            if row is None:
                return None
            outcomes = conn.execute(
                "SELECT action_id, result, notes, retained FROM outcomes WHERE incident_seq = ?",
                (seq,),
            ).fetchall()
        return {
            "id": incident_id,
            "created_at": row["created_at"],
            "memory_enabled": bool(row["memory_enabled"]),
            "incident": IncidentInput.model_validate_json(row["incident"]),
            "plan": Plan.model_validate_json(row["plan"]) if row["plan"] else None,
            "outcomes": [dict(o) for o in outcomes],
        }

    def save_outcomes(
        self, incident_id: str, outcomes: list[OutcomeInput], retained: set[str]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        seq = _seq(incident_id)
        with closing(self._connect()) as conn, conn:
            for outcome in outcomes:
                conn.execute(
                    "INSERT OR REPLACE INTO outcomes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        seq,
                        outcome.action_id,
                        outcome.result,
                        outcome.notes,
                        int(outcome.action_id in retained),
                        now,
                    ),
                )

            # Also update the incident plan timeline if plan exists
            row = conn.execute("SELECT plan FROM incidents WHERE seq = ?", (seq,)).fetchone()
            if row and row["plan"]:
                try:
                    plan_data = json.loads(row["plan"])
                    for outcome in outcomes:
                        for act in plan_data.get("actions", []):
                            if act.get("id") == outcome.action_id:
                                act["outcome"] = outcome.result
                                act["outcome_notes"] = outcome.notes

                    now_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                    plan_data.setdefault("timeline", []).append(
                        {
                            "timestamp": now_time,
                            "phase": "outcome_recorded",
                            "title": "Action Outcomes Recorded",
                            "details": f"Saved {len(outcomes)} action outcomes to session & Hindsight",
                        }
                    )
                    if any(o.result == "worked" for o in outcomes):
                        plan_data["timeline"].append(
                            {
                                "timestamp": now_time,
                                "phase": "resolved",
                                "title": "Incident Resolved",
                                "details": "Confirmed working resolution established",
                            }
                        )
                    conn.execute(
                        "UPDATE incidents SET plan = ? WHERE seq = ?",
                        (json.dumps(plan_data), seq),
                    )
                except Exception:
                    pass

    def list_incidents(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT seq, created_at, memory_enabled, incident, plan FROM incidents "
                "ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
            outcomes = conn.execute(
                "SELECT incident_seq, action_id, result, notes FROM outcomes"
            ).fetchall()

        outcomes_by_seq: dict[int, list[dict[str, Any]]] = {}
        for o in outcomes:
            outcomes_by_seq.setdefault(o["incident_seq"], []).append(dict(o))

        result: list[dict[str, Any]] = []
        for r in rows:
            inc_obj = json.loads(r["incident"])
            plan_obj = json.loads(r["plan"]) if r["plan"] else {}
            seq = r["seq"]
            seq_outcomes = outcomes_by_seq.get(seq, [])

            status = "Open"
            if any(o.get("result") == "worked" for o in seq_outcomes):
                status = "Resolved"
            elif any(o.get("result") == "failed" for o in seq_outcomes):
                status = "Investigating"

            result.append(
                {
                    "id": f"INC-{ID_OFFSET + seq}",
                    "seq": seq,
                    "created_at": r["created_at"],
                    "memory_enabled": bool(r["memory_enabled"]),
                    "title": inc_obj.get("title", ""),
                    "service": inc_obj.get("service", ""),
                    "severity": inc_obj.get("severity")
                    or plan_obj.get("assessed_severity")
                    or "high",
                    "category": inc_obj.get("category")
                    or plan_obj.get("incident_category")
                    or "application",
                    "status": status,
                    "symptoms": inc_obj.get("symptoms", ""),
                    "description": inc_obj.get("description", ""),
                    "outcomes": seq_outcomes,
                }
            )
        return result

    def get_all_raw_data(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Returns all incidents and outcomes for analytics processing."""
        incidents = self.list_incidents(limit=500)
        with closing(self._connect()) as conn:
            outcomes = [dict(r) for r in conn.execute("SELECT * FROM outcomes").fetchall()]
        return incidents, outcomes
