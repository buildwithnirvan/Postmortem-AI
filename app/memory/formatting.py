"""Pure functions that decide WHAT is written to / asked of Hindsight with enhanced categorisation.

Keeping this separate from the SDK calls makes the memory lifecycle easy to read and test:
  * retain  -> format_incident_memory(), format_outcome_memory(), tags_for_*()
  * recall  -> build_recall_query()
  * safety  -> redact() runs on every free-text field before it leaves the app
"""

from __future__ import annotations

import re

from app.models import IncidentInput

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)bearer\s+[a-z0-9._\-]{16,}"), "Bearer [REDACTED]"),
    (
        re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b(\s*[=:]\s*)\S+"),
        r"\1\2[REDACTED]",
    ),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
]

_SIGNAL = re.compile(r"(?i)error|exception|fatal|timeout|timed out|refused|oom|panic|warn|fail")


def redact(text: str) -> str:
    """Mask obvious secrets and emails. Best-effort guard, not a DLP product."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def service_slug(service: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", service.lower()).strip("-") or "unknown"


def tags_for_incident(
    service: str, category: str | None = None, env: str = "production"
) -> list[str]:
    tags = ["incident", f"service:{service_slug(service)}", f"env:{env}"]
    if category:
        tags.append(f"category:{category.lower()}")
    return tags


def tags_for_outcome(service: str, result: str, category: str | None = None) -> list[str]:
    tags = ["outcome", f"service:{service_slug(service)}", f"result:{result}"]
    if category:
        tags.append(f"category:{category.lower()}")
    return tags


def tags_for_root_cause(service: str, confidence: str) -> list[str]:
    return ["root_cause", f"service:{service_slug(service)}", f"confidence:{confidence}"]


def outcome_from_tags(tags: list[str] | None) -> str | None:
    """Read the worked/failed signal back from tags written at retain time."""
    for tag in tags or []:
        if tag in ("result:worked", "result:failed"):
            return tag.split(":", 1)[1]
    return None


_FAILED_WORDS = re.compile(r"(?i)\b(failed|did not work|didn't work|masked|made it worse)\b")
_WORKED_WORDS = re.compile(r"(?i)\b(worked|resolved|fixed|cleared)\b")


def outcome_from_text(text: str, tags: list[str] | None) -> str | None:
    """HEURISTIC fallback for when Hindsight did not keep our result:* tags on a fact."""
    if any(t in ("outcome", "incident") for t in tags or []):
        return None
    if not re.search(r"(?i)\b(action|outcome)\b", text):
        return None
    failed, worked = bool(_FAILED_WORDS.search(text)), bool(_WORKED_WORDS.search(text))
    if failed == worked:
        return None
    return "failed" if failed else "worked"


def log_signature(logs: str, max_lines: int = 4, max_chars: int = 400) -> str:
    """The few log lines that best identify the failure (errors first, else the head)."""
    lines = [ln.strip() for ln in logs.splitlines() if ln.strip()]
    chosen = [ln for ln in lines if _SIGNAL.search(ln)][:max_lines] or lines[:max_lines]
    return " | ".join(chosen)[:max_chars]


def format_incident_memory(incident_id: str, incident: IncidentInput) -> str:
    """Text retained when an incident is opened. Hindsight extracts facts from it."""
    parts = [
        f"Incident {incident_id} on service {incident.service} (Environment: {incident.environment}, Severity: {incident.severity}): {incident.title}.",
        f"Category: {incident.category or 'application'}",
        f"Description: {incident.description}",
        f"Symptoms: {incident.symptoms}",
    ]
    if incident.business_impact:
        parts.append(f"Business Impact: {incident.business_impact}")
    signature = log_signature(incident.logs)
    if signature:
        parts.append(f"Key log lines: {signature}")
    return redact("\n".join(parts))


def format_outcome_memory(
    incident_id: str,
    incident: IncidentInput,
    action_title: str,
    result: str,
    notes: str,
) -> str:
    """Text retained for a CONFIRMED outcome. 'not_tried' and 'blocked' are skipped from core resolution facts."""
    verdict = {"worked": "WORKED", "failed": "FAILED", "blocked": "BLOCKED"}.get(
        result, result.upper()
    )
    text = (
        f"Outcome for incident {incident_id} on service {incident.service} "
        f"('{incident.title}'): the troubleshooting action '{action_title}' {verdict}."
    )
    if notes:
        text += f" Engineer notes: {notes}"
    return redact(text)


def format_root_cause_memory(
    incident_id: str, service: str, hypothesis: str, confidence: str
) -> str:
    return redact(
        f"Root Cause Analysis for incident {incident_id} on service {service}: {hypothesis} (Confidence: {confidence.upper()})."
    )


def build_recall_query(incident: IncidentInput) -> str:
    """Natural-language query describing the new incident, used for semantic recall."""
    cat_str = f" Category: {incident.category}." if incident.category else ""
    query = (
        f"{incident.service} incident: {incident.title}.{cat_str} Symptoms: {incident.symptoms}."
    )
    signature = log_signature(incident.logs)
    if signature:
        query += f" Log evidence: {signature}"
    query += " Which troubleshooting actions worked or failed for similar incidents?"
    return redact(query)
