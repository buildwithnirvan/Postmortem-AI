"""Turns an incident + recalled memories into an advanced RCA, timeline and evidence-cited plan."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.memory.formatting import redact
from app.models import (
    Category,
    Evidence,
    IncidentInput,
    MemoryStatus,
    Plan,
    PlanAction,
    RecalledMemory,
    Risk,
    RootCauseAnalysis,
    Severity,
    Stance,
    TimelineEvent,
)


class PlanGenerationError(RuntimeError):
    """The LLM answered, but not with a usable plan."""


class JsonLLM(Protocol):
    def chat_json(self, system: str, user: str) -> dict[str, Any]: ...


SYSTEM_PROMPT = """You are Postmortem 2.0, an enterprise AI Incident Intelligence and SRE Resolution engine.
You help on-call engineers triage technical incidents, analyze root causes, and prioritize safe troubleshooting steps based on historical memories.
You never execute anything automatically on infrastructure. Commands are suggestions only.

Return ONE JSON object with exact fields:
{
  "summary": str,
  "incident_category": "database"|"network"|"infrastructure"|"application"|"authentication"|"security"|"performance"|"deployment"|"other",
  "assessed_severity": "critical"|"high"|"medium"|"low",
  "affected_services": [str],
  "initial_impact": str,
  "rca": {
    "primary_hypothesis": str,
    "confidence": "confirmed"|"possible"|"unverified",
    "confidence_explanation": str,
    "contributing_factors": [str],
    "supporting_log_evidence": [str],
    "related_historical_incidents": [str],
    "business_impact_assessment": str,
    "recommended_permanent_fix": str,
    "preventive_actions": [str]
  },
  "actions": [
    {
      "title": str,
      "explanation": str,
      "rationale": str,
      "risk": "low"|"medium"|"high",
      "expected_result": str,
      "estimated_minutes": int,
      "required_permissions": str,
      "suggested_command": str or null,
      "evidence": [{"ref": "M1", "stance": "supports"|"warns", "note": str}]
    }
  ]
}

Rules:
1. Distinguish observed facts from unverified hypotheses. In RCA confidence, mark 'confirmed' only if supported by clear historical memory or explicit logs.
2. Provide 3 to 6 prioritized troubleshooting actions (rank 1 = first to try).
3. Memories are numbered excerpts (M1, M2...). Cite them in "evidence" by ref. Never invent a ref.
4. If a memory indicates an action FAILED or caused harm previously on a similar incident:
   do not recommend it as a primary step; place it last with stance "warns", explain why.
5. If a memory shows an action WORKED for a similar incident:
   rank it high, cite stance "supports", and explain the proven outcome.
6. If no memories exist, state that in summary, deliver standard industry best practices, and leave evidence empty.
7. Suggestions with commands should be non-destructive diagnostic queries whenever possible.
"""


class _RawEvidence(BaseModel):
    ref: str
    stance: Stance = "supports"
    note: str = ""


class _RawAction(BaseModel):
    title: str = Field(min_length=1)
    explanation: str = ""
    rationale: str = ""
    risk: Risk = "medium"
    expected_result: str = ""
    estimated_minutes: int = 15
    required_permissions: str = "Standard SRE"
    suggested_command: str | None = None
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _RawPlan(BaseModel):
    summary: str = ""
    incident_category: Category = "application"
    assessed_severity: Severity = "high"
    affected_services: list[str] = Field(default_factory=list)
    initial_impact: str = ""
    rca: RootCauseAnalysis | None = None
    actions: list[_RawAction] = Field(min_length=1, max_length=8)


def assign_refs(memories: list[RecalledMemory]) -> list[RecalledMemory]:
    for index, memory in enumerate(memories, start=1):
        memory.ref = f"M{index}"
    return memories


def build_user_prompt(incident: IncidentInput, memories: list[RecalledMemory]) -> str:
    if memories:
        lines = []
        for m in memories:
            outcome = f" [recorded outcome: {m.outcome.upper()}]" if m.outcome else ""
            lines.append(f"{m.ref}{outcome}: {m.text}")
        memory_block = "\n".join(lines)
    else:
        memory_block = "(no relevant memories were recalled)"

    env_str = f"Environment: {incident.environment}\nSeverity: {incident.severity}\n"
    if incident.business_impact:
        env_str += f"Business Impact: {incident.business_impact}\n"
    if incident.category:
        env_str += f"User specified category: {incident.category}\n"

    return redact(
        f"INCIDENT DETAILS\nTitle: {incident.title}\nService: {incident.service}\n"
        f"{env_str}"
        f"Description: {incident.description}\nSymptoms: {incident.symptoms}\n"
        f"Logs:\n{incident.logs or '(none provided)'}\n\n"
        f"MEMORIES FROM PAST INCIDENTS\n{memory_block}"
    )


def apply_outcome_guard(raw: _RawPlan, memories: list[RecalledMemory]) -> list[PlanAction]:
    by_ref = {m.ref: m for m in memories}
    staged: list[tuple[int, int, PlanAction]] = []

    for index, raw_action in enumerate(raw.actions):
        evidence: list[Evidence] = []
        corrected = False
        for item in raw_action.evidence:
            memory = by_ref.get(item.ref)
            if memory is None:
                continue
            stance: Stance = item.stance
            if memory.outcome == "failed" and stance == "supports":
                stance, corrected = "warns", True
            evidence.append(
                Evidence(
                    ref=item.ref,
                    memory_id=memory.id,
                    stance=stance,
                    note=item.note,
                    outcome=memory.outcome,
                )
            )

        worked_support = any(e.stance == "supports" and e.outcome == "worked" for e in evidence)
        failed_warning = any(e.stance == "warns" and e.outcome == "failed" for e in evidence)
        warns = [e for e in evidence if e.stance == "warns"]

        if worked_support:
            group, reason = (
                0,
                "Ranked up: Prior WORKED outcome recorded in Hindsight on similar incident.",
            )
        elif failed_warning:
            group, reason = (
                2,
                "Ranked down: Prior FAILED outcome recorded in Hindsight on similar incident.",
            )
        else:
            group, reason = 1, None
        if corrected:
            reason = (reason or "") + " (Citation corrected from 'supports' to 'warns'.)"

        action = PlanAction(
            id="",
            priority=0,
            title=raw_action.title,
            explanation=raw_action.explanation or raw_action.rationale,
            rationale=raw_action.rationale,
            risk=raw_action.risk,
            expected_result=raw_action.expected_result,
            estimated_minutes=raw_action.estimated_minutes or 15,
            required_permissions=raw_action.required_permissions or "Standard SRE",
            suggested_command=raw_action.suggested_command,
            evidence=evidence,
            warning=(warns[0].note or "Past evidence warns against this step.") if warns else None,
            rank_reason=reason.strip() if reason else None,
        )
        staged.append((group, index, action))

    staged.sort(key=lambda row: (row[0], row[1]))
    actions = [row[2] for row in staged]
    for position, action in enumerate(actions, start=1):
        action.id, action.priority = f"a{position}", position
    return actions


def generate_plan(
    incident: IncidentInput,
    memories: list[RecalledMemory],
    llm: JsonLLM,
    memory_status: MemoryStatus,
    memory_message: str = "",
) -> Plan:
    now_iso = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    timeline: list[TimelineEvent] = [
        TimelineEvent(
            timestamp=incident.detection_time or now_iso,
            phase="detected",
            title="Incident Detected",
            details=f"Service {incident.service} reported {incident.symptoms}",
        ),
        TimelineEvent(
            timestamp=now_iso,
            phase="submitted",
            title="Investigation Initialized",
            details="Incident details & logs submitted for AI triage",
        ),
    ]

    assign_refs(memories)
    if memory_status == "used" and memories:
        timeline.append(
            TimelineEvent(
                timestamp=now_iso,
                phase="memory_recalled",
                title="Historical Memory Retrieved",
                details=f"Retrieved {len(memories)} matching episodic memories from Hindsight",
            )
        )

    payload = llm.chat_json(SYSTEM_PROMPT, build_user_prompt(incident, memories))
    try:
        raw = _RawPlan.model_validate(payload)
    except ValidationError as exc:
        raise PlanGenerationError(
            "The model returned a plan in an unexpected shape: "
            + json.dumps(exc.errors()[:2], default=str)
        ) from exc

    timeline.append(
        TimelineEvent(
            timestamp=now_iso,
            phase="rca_generated",
            title="Root Cause Hypothesis Generated",
            details=f"Primary hypothesis identified with {raw.rca.confidence if raw.rca else 'unverified'} confidence",
        )
    )
    timeline.append(
        TimelineEvent(
            timestamp=now_iso,
            phase="plan_created",
            title="Troubleshooting Roadmap Built",
            details=f"Generated {len(raw.actions)} prioritized actions with deterministic outcome guard applied",
        )
    )

    affected = raw.affected_services or [incident.service]
    if incident.service not in affected:
        affected.insert(0, incident.service)

    return Plan(
        summary=raw.summary or "Investigation completed.",
        incident_category=raw.incident_category or incident.category or "application",
        assessed_severity=raw.assessed_severity or incident.severity or "high",
        affected_services=affected,
        initial_impact=raw.initial_impact
        or incident.business_impact
        or "Degraded performance observed",
        rca=raw.rca,
        actions=apply_outcome_guard(raw, memories),
        timeline=timeline,
        memories=memories,
        memory_status=memory_status,
        memory_message=memory_message,
    )
