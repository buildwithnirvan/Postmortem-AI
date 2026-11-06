"""Repeatable before/after demo, using the same pipeline as the app.

    python -m scripts.demo --reset      # wipes the configured bank first

Steps: (1) plan with NO memory  (2) load synthetic history into Hindsight
       (3) plan the SAME incident WITH recalled memory  (4) print the difference.
Requires real HINDSIGHT_* and GROQ_API_KEY values in .env. Nothing here is mocked.
"""

from __future__ import annotations

import argparse
import sys
import time

from hindsight_client import Hindsight

from app.agent.llm import GroqClient
from app.agent.planner import generate_plan
from app.config import Settings
from app.data.sample_incidents import SAMPLES
from app.data.seed_incidents import build_seed_items
from app.memory.service import MemoryService
from app.models import IncidentInput, Plan


def show(title: str, plan: Plan) -> None:
    print(f"\n=== {title} ({plan.memory_status}) ===\n{plan.summary}")
    for a in plan.actions:
        print(f"  {a.priority}. {a.title}  [{a.risk} risk]")
        if a.rank_reason:
            print(f"     -> {a.rank_reason}")
        if a.warning:
            print(f"     !! {a.warning}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete the bank before starting")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.missing():
        print(f"Missing configuration: {', '.join(settings.missing())}. See .env.example.")
        return 2
    client = Hindsight(
        base_url=settings.hindsight_base_url or "",
        api_key=settings.hindsight_api_key,
        timeout=settings.hindsight_timeout,
    )
    memory = MemoryService(client, settings.hindsight_bank_id, settings.recall_max_tokens)
    llm = GroqClient(settings.groq_api_key, settings.groq_model, settings.groq_base_url)
    sample = next(s for s in SAMPLES if s["key"] == "redis-pool")
    fields = ("title", "service", "description", "symptoms", "logs")
    incident = IncidentInput(**{k: sample[k] for k in fields})

    if args.reset:
        memory.reset()
    before = generate_plan(incident, [], llm, "disabled", "Baseline without memory.")
    show("BEFORE: no memory", before)

    print("\nLoading synthetic incident history into Hindsight...")
    memory.retain_batch(build_seed_items())
    time.sleep(2)

    memories = memory.recall_for_incident(incident)
    print(f"Recalled {len(memories)} memories.")
    after = generate_plan(incident, memories, llm, "used" if memories else "empty")
    show("AFTER: with Hindsight memory", after)

    print("\nBefore order:", [a.title for a in before.actions])
    print("After  order:", [a.title for a in after.actions])
    return 0


if __name__ == "__main__":
    sys.exit(main())
