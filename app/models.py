"""Pydantic schemas for Postmortem 2.0 platform."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Result = Literal["worked", "failed", "not_tried", "blocked"]
Stance = Literal["supports", "warns"]
Risk = Literal["low", "medium", "high"]
Severity = Literal["critical", "high", "medium", "low"]
Environment = Literal["production", "staging", "development", "canary"]
Category = Literal[
    "database",
    "network",
    "infrastructure",
    "application",
    "authentication",
    "security",
    "performance",
    "deployment",
    "other",
]
MemoryStatus = Literal["used", "empty", "disabled", "unavailable"]


class IncidentInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    service: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=3, max_length=4000)
    symptoms: str = Field(min_length=3, max_length=2000)
    logs: str = Field(default="", max_length=8000)
    environment: Environment = "production"
    severity: Severity = "high"
    category: Category | None = None
    detection_time: str | None = None
    business_impact: str = Field(default="", max_length=1000)

    @field_validator(
        "title", "service", "description", "symptoms", "logs", "business_impact", mode="before"
    )
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RecalledMemory(BaseModel):
    ref: str = ""  # M1, M2...
    id: str
    text: str
    type: str | None = None
    context: str | None = None
    tags: list[str] = Field(default_factory=list)
    score: float | None = None
    outcome: Literal["worked", "failed"] | None = None
    date: str | None = None


class Evidence(BaseModel):
    ref: str
    memory_id: str
    stance: Stance
    note: str = ""
    outcome: Literal["worked", "failed"] | None = None


class PlanAction(BaseModel):
    id: str
    priority: int
    title: str
    explanation: str = ""  # detailed step description
    rationale: str = ""
    risk: Risk = "medium"
    expected_result: str = ""
    estimated_minutes: int = 15
    required_permissions: str = "Standard SRE / Read-Write"
    suggested_command: str | None = None  # Non-executed command suggestion
    evidence: list[Evidence] = Field(default_factory=list)
    warning: str | None = None
    rank_reason: str | None = None
    outcome: Result = "not_tried"
    outcome_notes: str = ""


class RootCauseAnalysis(BaseModel):
    primary_hypothesis: str
    confidence: Literal["confirmed", "possible", "unverified"]
    confidence_explanation: str
    contributing_factors: list[str] = Field(default_factory=list)
    supporting_log_evidence: list[str] = Field(default_factory=list)
    related_historical_incidents: list[str] = Field(default_factory=list)
    business_impact_assessment: str = ""
    recommended_permanent_fix: str = ""
    preventive_actions: list[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    timestamp: str
    phase: Literal[
        "detected",
        "submitted",
        "memory_recalled",
        "rca_generated",
        "plan_created",
        "troubleshooting",
        "outcome_recorded",
        "resolved",
        "retained",
    ]
    title: str
    details: str = ""


class Plan(BaseModel):
    summary: str
    incident_category: Category = "application"
    assessed_severity: Severity = "high"
    affected_services: list[str] = Field(default_factory=list)
    initial_impact: str = ""
    rca: RootCauseAnalysis | None = None
    actions: list[PlanAction]
    timeline: list[TimelineEvent] = Field(default_factory=list)
    memories: list[RecalledMemory] = Field(default_factory=list)
    memory_status: MemoryStatus
    memory_message: str = ""


class OutcomeInput(BaseModel):
    action_id: str
    result: Result
    notes: str = Field(default="", max_length=1000)

    @field_validator("notes", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OutcomeBatch(BaseModel):
    outcomes: list[OutcomeInput] = Field(min_length=1, max_length=20)


class CreateIncidentRequest(IncidentInput):
    use_memory: bool = True


class ResetRequest(BaseModel):
    confirm: str


class MemoryItem(BaseModel):
    id: str
    text: str
    fact_type: str | None = None
    context: str | None = None
    tags: list[str] = Field(default_factory=list)
    date: str | None = None


# Module G: Service Map Models
class ServiceNode(BaseModel):
    name: str
    category: str = "core"
    tier: int = 1
    dependencies: list[str] = Field(default_factory=list)
    health: Literal["healthy", "degraded", "outage"] = "healthy"
    active_incidents: list[str] = Field(default_factory=list)


# Module E: Recurring Incident Pattern
class RecurringPattern(BaseModel):
    pattern_id: str
    title: str
    affected_services: list[str]
    occurrences_count: int
    first_seen: str
    last_seen: str
    common_symptoms: list[str]
    attempted_solutions: list[str]
    most_successful_resolution: str
    underlying_pattern: str


# Module H: Analytics Dashboard Schema
class AnalyticsOverview(BaseModel):
    total_incidents: int
    open_incidents: int
    resolved_incidents: int
    critical_incidents: int
    average_resolution_minutes: float
    successful_resolutions_count: int
    failed_attempts_count: int
    recurring_patterns_count: int
    memory_assisted_count: int
    severity_distribution: dict[str, int]
    category_distribution: dict[str, int]
    service_incidents: dict[str, int]
    daily_trend: list[dict[str, Any]]
