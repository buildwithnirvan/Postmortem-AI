"""HTTP layer for Postmortem 2.0: Orchestrates recall, triage, rca, retain, analytics & reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.agent.llm import LLMUnavailableError
from app.agent.planner import JsonLLM, PlanGenerationError, generate_plan
from app.config import Settings
from app.data.sample_incidents import SAMPLES
from app.data.seed_incidents import SEED_INCIDENTS, build_seed_items
from app.intelligence import IntelligenceEngine
from app.memory.service import MemoryService, MemoryUnavailableError
from app.models import (
    CreateIncidentRequest,
    IncidentInput,
    OutcomeBatch,
    Plan,
    ResetRequest,
)
from app.storage import Store

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Settings, memory: MemoryService | None, llm: JsonLLM, store: Store
) -> FastAPI:
    app = FastAPI(title="Postmortem 2.0", version="2.0.0")
    intel = IntelligenceEngine()

    def require_memory() -> MemoryService:
        if memory is None:
            raise HTTPException(
                503, "Hindsight is not configured. Set HINDSIGHT_BASE_URL (and HINDSIGHT_API_KEY)."
            )
        return memory

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        hindsight: dict[str, Any] = {"configured": memory is not None}
        if memory is not None:
            try:
                hindsight.update(ok=True, version=memory.health(), bank=memory.bank_id)
            except MemoryUnavailableError as exc:
                hindsight.update(ok=False, error=str(exc), bank=memory.bank_id)
        return {
            "hindsight": hindsight,
            "llm": {"configured": bool(settings.groq_api_key), "model": settings.groq_model},
            "missing_env": settings.missing(),
        }

    @app.get("/api/samples")
    def samples() -> list[dict[str, str]]:
        return SAMPLES

    @app.post("/api/incidents")
    def create_incident(request: CreateIncidentRequest) -> dict[str, Any]:
        incident = IncidentInput(**request.model_dump(exclude={"use_memory"}))
        warnings: list[str] = []

        # 1) RECALL first, so the new incident cannot recall itself
        memories, status, message = [], "disabled", "Memory switched off for this run."
        if request.use_memory:
            try:
                memories = require_memory().recall_for_incident(incident)
                status = "used" if memories else "empty"
                message = (
                    f"Recalled {len(memories)} memories from Hindsight."
                    if memories
                    else "Hindsight returned no relevant memories (cold start)."
                )
            except (MemoryUnavailableError, HTTPException) as exc:
                status = "unavailable"
                message = str(exc.detail if isinstance(exc, HTTPException) else exc)
                warnings.append(f"Planning without memory: {message}")

        # 2) PLAN & RCA.
        try:
            plan: Plan = generate_plan(incident, memories, llm, status, message)
        except LLMUnavailableError as exc:
            raise HTTPException(502, f"LLM unavailable: {exc}") from exc
        except PlanGenerationError as exc:
            raise HTTPException(502, str(exc)) from exc

        incident_id = store.create_incident(incident, memory_enabled=request.use_memory)
        store.save_plan(incident_id, plan)

        # 3) RETAIN the incident report into Hindsight
        retained = False
        if request.use_memory and status != "unavailable":
            try:
                require_memory().retain_incident(incident_id, incident)
                retained = True
            except (MemoryUnavailableError, HTTPException) as exc:
                warnings.append(f"Incident was not saved to memory: {exc}")

        return {
            "incident_id": incident_id,
            "plan": plan,
            "incident_retained": retained,
            "warnings": warnings,
        }

    @app.get("/api/incidents")
    def list_incidents(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
        return store.list_incidents(limit=limit)

    @app.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict[str, Any]:
        record = store.get_incident(incident_id)
        if record is None:
            raise HTTPException(404, f"Incident {incident_id} not found.")
        return record

    @app.post("/api/incidents/{incident_id}/outcomes")
    def record_outcomes(incident_id: str, batch: OutcomeBatch) -> dict[str, Any]:
        record = store.get_incident(incident_id)
        if record is None:
            raise HTTPException(404, f"Incident {incident_id} not found.")
        plan: Plan | None = record["plan"]
        if plan is None:
            raise HTTPException(409, "This incident has no plan yet.")

        titles = {a.id: a.title for a in plan.actions}
        unknown = [o.action_id for o in batch.outcomes if o.action_id not in titles]
        if unknown:
            raise HTTPException(422, f"Unknown action ids: {', '.join(unknown)}")

        warnings: list[str] = []
        retained_ids: set[str] = set()
        if record["memory_enabled"]:
            try:
                pairs = [(o, titles[o.action_id]) for o in batch.outcomes]
                require_memory().retain_outcomes(incident_id, record["incident"], pairs)
                retained_ids = {
                    o.action_id for o in batch.outcomes if o.result in ("worked", "failed")
                }
            except (MemoryUnavailableError, HTTPException) as exc:
                warnings.append(f"Outcomes saved locally but NOT retained in Hindsight: {exc}")
        else:
            warnings.append(
                "This was a memory-off run, so outcomes were not retained in Hindsight."
            )

        store.save_outcomes(incident_id, batch.outcomes, retained_ids)
        return {
            "saved": len(batch.outcomes),
            "retained_in_hindsight": len(retained_ids),
            "skipped_not_tried": sum(o.result == "not_tried" for o in batch.outcomes),
            "warnings": warnings,
        }

    # Module E: Recurring Patterns Endpoint
    @app.get("/api/patterns")
    def get_recurring_patterns() -> list[dict[str, Any]]:
        incidents, outcomes = store.get_all_raw_data()
        patterns = intel.detect_recurring_patterns(incidents, outcomes)
        return [p.model_dump() for p in patterns]

    # Module G: Service Graph & Blast Radius
    @app.get("/api/services")
    def get_services() -> dict[str, Any]:
        incidents, _ = store.get_all_raw_data()
        active = [i for i in incidents if i.get("status") != "Resolved"]
        graph = intel.get_service_graph(active)
        return {"services": [n.model_dump() for n in graph]}

    @app.get("/api/services/{service_name}/blast-radius")
    def get_blast_radius(service_name: str) -> dict[str, Any]:
        radius = intel.calculate_blast_radius(service_name)
        return {"service": service_name, "impacted_dependents": radius, "risk_count": len(radius)}

    # Module H: Analytics Dashboard Endpoint
    @app.get("/api/analytics")
    def get_analytics() -> dict[str, Any]:
        incidents, outcomes = store.get_all_raw_data()
        analytics = intel.compute_analytics(incidents, outcomes)
        return analytics.model_dump()

    # Module I: Postmortem Report Export (Markdown, Printable View, and Native PDF)
    @app.get("/api/incidents/{incident_id}/report")
    def get_incident_report(
        incident_id: str, format: str = Query("markdown", pattern="^(markdown|html|pdf)$")
    ) -> Response:
        record = store.get_incident(incident_id)
        if record is None or not record.get("plan"):
            raise HTTPException(404, f"Incident {incident_id} or plan not found.")

        if format == "pdf":
            from app.pdf_generator import generate_pdf_report

            pdf_bytes = generate_pdf_report(
                incident_id, record["incident"], record["plan"], record.get("outcomes", [])
            )
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{incident_id}-postmortem.pdf"'
                },
            )

        md = intel.generate_markdown_report(
            incident_id, record["incident"], record["plan"], record.get("outcomes", [])
        )
        if format == "markdown":
            return PlainTextResponse(
                md,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="{incident_id}-postmortem.md"'
                },
            )

        html_content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Postmortem Report - {incident_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 40px auto; padding: 20px; color: #1e293b; }}
    h1 {{ border-bottom: 2px solid #0284c7; padding-bottom: 8px; color: #0f172a; }}
    h2 {{ color: #0369a1; margin-top: 24px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
    pre {{ background: #0f172a; color: #f8fafc; padding: 14px; border-radius: 6px; overflow-x: auto; }}
    @media print {{ body {{ margin: 0; padding: 15px; max-width: 100%; }} }}
  </style>
</head>
<body>
  <div style="float: right;">
    <button onclick="window.print()" style="padding: 8px 16px; background: #0284c7; color: white; border: none; border-radius: 4px; cursor: pointer;">Print / Save as PDF</button>
  </div>
  <pre style="white-space: pre-wrap; font-family: inherit; background: transparent; color: inherit; padding: 0;">{md}</pre>
</body>
</html>"""
        return Response(content=html_content, media_type="text/html")

    # Module B: Memory Intelligence
    @app.get("/api/memories")
    def memories(
        q: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        try:
            return require_memory().list_memories(q, limit, offset)
        except MemoryUnavailableError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/memory/seed")
    def seed_memory() -> dict[str, Any]:
        try:
            count = require_memory().retain_batch(build_seed_items())
        except MemoryUnavailableError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"retained_items": count, "incidents": len(SEED_INCIDENTS)}

    @app.post("/api/memory/reset")
    def reset_memory(request: ResetRequest) -> dict[str, str]:
        if request.confirm != "RESET":
            raise HTTPException(422, 'Send {"confirm": "RESET"} to delete all memory.')
        try:
            require_memory().reset()
        except MemoryUnavailableError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"status": "memory bank deleted and recreated empty"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
