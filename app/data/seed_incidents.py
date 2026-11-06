"""Synthetic incident history used to demonstrate memory. All data is invented.

The Redis pool-exhaustion pattern appears twice on purpose: in both, restarting the service
FAILED (it only masked the leak) and raising the pool limit WORKED. A later, similar incident
should therefore not lead with "restart".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.memory.formatting import (
    format_incident_memory,
    format_outcome_memory,
    tags_for_incident,
    tags_for_outcome,
)
from app.models import IncidentInput


@dataclass(frozen=True)
class SeedAction:
    title: str
    result: str  # "worked" | "failed"
    notes: str


@dataclass(frozen=True)
class SeedIncident:
    id: str
    days_ago: int
    incident: IncidentInput
    actions: list[SeedAction] = field(default_factory=list)


def _inc(title: str, service: str, description: str, symptoms: str, logs: str) -> IncidentInput:
    return IncidentInput(
        title=title, service=service, description=description, symptoms=symptoms, logs=logs
    )


SEED_INCIDENTS: list[SeedIncident] = [
    SeedIncident(
        "SEED-01",
        140,
        _inc(
            "payments-api returning 502s, Redis connection errors",
            "payments-api",
            "Checkout failures spiked during evening traffic. Gateway shows 502 from payments-api.",
            "502 rate 18%, p99 latency 9s, errors correlate with Redis client timeouts.",
            "redis.exceptions.ConnectionError: Too many connections\n"
            "WARN pool wait timeout after 5000ms (max_connections=50, in_use=50)\n"
            "ERROR POST /v1/charges 502 upstream timeout",
        ),
        [
            SeedAction(
                "Restart payments-api pods",
                "failed",
                "Errors stopped for about 12 minutes then returned. Only masked a connection leak.",
            ),
            SeedAction(
                "Scale payments-api replicas from 4 to 8",
                "failed",
                "Made it worse: more clients competing for the same Redis maxclients.",
            ),
            SeedAction(
                "Raise Redis client max_connections from 50 to 200 and set socket_timeout",
                "worked",
                "502s cleared within 5 minutes. Pool size was the immediate bottleneck.",
            ),
            SeedAction(
                "Fix connection leak in the retry path (release in finally block)",
                "worked",
                "Root cause. Deployed next day; pool usage stayed flat.",
            ),
        ],
    ),
    SeedIncident(
        "SEED-02",
        120,
        _inc(
            "checkout-service p99 latency spike after deploy",
            "checkout-service",
            "Latency tripled right after release v2.41.0 went out.",
            "p99 from 400ms to 1.4s, DB CPU at 85%, no error-rate increase.",
            "INFO deploy v2.41.0 complete\nWARN slow query count=4812/min on carts.items\n",
        ),
        [
            SeedAction(
                "Roll back checkout-service to v2.40.2",
                "worked",
                "Latency recovered in 5 minutes. N+1 query was in the new cart endpoint.",
            ),
            SeedAction(
                "Add a DB read replica",
                "failed",
                "No effect: query volume, not capacity, was the problem.",
            ),
            SeedAction("Purge CDN cache", "failed", "Unrelated to the slow path."),
        ],
    ),
    SeedIncident(
        "SEED-03",
        75,
        _inc(
            "payments-api Redis connection timeouts during promo traffic",
            "payments-api",
            "Flash-sale traffic surge. Intermittent payment failures and timeouts to Redis.",
            "Timeouts to Redis, checkout 502s climbing, pods healthy.",
            "redis.exceptions.TimeoutError: Timeout reading from socket\n"
            "WARN pool wait timeout after 5000ms (max_connections=100, in_use=100)\n"
            "ERROR charge failed: upstream timeout",
        ),
        [
            SeedAction(
                "Restart the payments worker",
                "failed",
                "Same story as before: recovered briefly, then pool saturated again within 15 minutes.",
            ),
            SeedAction(
                "Increase pool max_connections and add a pool-wait alert",
                "worked",
                "Stable through the rest of the promo. Alert now fires at 80% pool use.",
            ),
        ],
    ),
    SeedIncident(
        "SEED-04",
        95,
        _inc(
            "ingest-pipeline Kafka consumer lag climbing",
            "ingest-pipeline",
            "Consumer group lag on topic events.raw grew from 2k to 4M messages in an hour.",
            "Lag growing, frequent rebalances, throughput near zero between rebalances.",
            "WARN Member consumer-7 sending LeaveGroup request: max.poll.interval.ms exceeded\n"
            "INFO Revoking previously assigned partitions\n",
        ),
        [
            SeedAction(
                "Add partitions to events.raw",
                "failed",
                "Triggered another rebalance; lag unchanged.",
            ),
            SeedAction(
                "Restart consumers", "failed", "Rebalance loop resumed after a few minutes."
            ),
            SeedAction(
                "Raise max.poll.interval.ms and cut max.poll.records from 500 to 100",
                "worked",
                "Batches were taking longer than the poll interval. Lag drained in 40 minutes.",
            ),
        ],
    ),
    SeedIncident(
        "SEED-05",
        60,
        _inc(
            "auth-service gateway serving expired TLS certificate",
            "auth-service",
            "Clients failing TLS handshakes to the internal gateway.",
            "x509: certificate has expired; login flows failing for internal tools.",
            "ERROR tls: failed to verify certificate: x509: certificate has expired or is not yet valid\n",
        ),
        [
            SeedAction(
                "Restart the gateway", "failed", "Still served the old certificate from the secret."
            ),
            SeedAction(
                "Renew the certificate via cert-manager and trigger a gateway reload",
                "worked",
                "Handshakes recovered immediately. Added expiry alert at 21 days.",
            ),
        ],
    ),
    SeedIncident(
        "SEED-06",
        45,
        _inc(
            "orders-db disk usage at 95%",
            "orders-db",
            "Primary Postgres volume nearly full; writes at risk.",
            "Disk 95%, WAL archive directory growing, replica lag normal.",
            "WARN could not write to file: No space left on device (imminent)\n"
            "INFO archive_command succeeded for 000000010000003A000000F2\n",
        ),
        [
            SeedAction(
                "Run VACUUM FULL on the orders table",
                "failed",
                "Needs extra disk and takes exclusive locks. Made the incident worse.",
            ),
            SeedAction(
                "Purge archived WAL older than 3 days after confirming replica is caught up",
                "worked",
                "Freed 40% of the volume in minutes.",
            ),
            SeedAction("Expand the volume by 200 GB", "worked", "Gave headroom for the weekend."),
        ],
    ),
    SeedIncident(
        "SEED-07",
        30,
        _inc(
            "search-api Elasticsearch heap pressure and slow queries",
            "search-api",
            "Search latency doubled; data nodes at 92% heap.",
            "Circuit breaker trips, GC pauses over 4s, queries timing out.",
            "WARN [gc][old] overhead, spent [4.2s] collecting\n"
            "ERROR CircuitBreakingException: [fielddata] Data too large\n",
        ),
        [
            SeedAction(
                "Restart the data nodes", "failed", "Heap climbed back to 90% within the hour."
            ),
            SeedAction(
                "Cap fielddata cache size and move sorting to doc_values",
                "worked",
                "Heap stabilised near 60%.",
            ),
        ],
    ),
    SeedIncident(
        "SEED-08",
        14,
        _inc(
            "notifications-worker OOMKilled repeatedly",
            "notifications-worker",
            "Pods restarting every ~25 minutes with exit code 137 since release v1.9.3.",
            "OOMKilled, memory climbing linearly, queue depth rising.",
            "State: Terminated Reason: OOMKilled Exit Code: 137\nWARN retry queue size=981223\n",
        ),
        [
            SeedAction(
                "Raise the memory limit from 512Mi to 1Gi",
                "failed",
                "Only delayed the OOM kill. Memory kept climbing.",
            ),
            SeedAction("Roll back to v1.9.2", "worked", "Memory flat again."),
            SeedAction(
                "Cap the in-memory retry queue and spill to disk",
                "worked",
                "Heap dump showed an unbounded retry queue. Fixed in v1.9.4.",
            ),
        ],
    ),
]


def build_seed_items(now: datetime | None = None) -> list[dict[str, Any]]:
    """retain_batch items: one incident report + one memory per recorded outcome."""
    now = now or datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for seed in SEED_INCIDENTS:
        when = now - timedelta(days=seed.days_ago)
        svc = seed.incident.service
        items.append(
            {
                "content": format_incident_memory(seed.id, seed.incident),
                "context": "Incident report",
                "document_id": f"{seed.id}:report",
                "tags": tags_for_incident(svc),
                "timestamp": when,
                "metadata": {"incident_id": seed.id, "kind": "incident", "synthetic": "true"},
            }
        )
        for index, action in enumerate(seed.actions, start=1):
            items.append(
                {
                    "content": format_outcome_memory(
                        seed.id, seed.incident, action.title, action.result, action.notes
                    ),
                    "context": "Confirmed troubleshooting outcome",
                    "document_id": f"{seed.id}:outcome:a{index}",
                    "tags": tags_for_outcome(svc, action.result),
                    "timestamp": when + timedelta(hours=1),
                    "metadata": {
                        "incident_id": seed.id,
                        "kind": "outcome",
                        "result": action.result,
                        "synthetic": "true",
                    },
                }
            )
    return items
