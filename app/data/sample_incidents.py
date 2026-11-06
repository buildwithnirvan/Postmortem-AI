"""Copy-paste incidents for the UI dropdown and the manual test guide (synthetic)."""

from __future__ import annotations

SAMPLES: list[dict[str, str]] = [
    {
        "key": "redis-pool",
        "label": "A. payments-api: Redis timeouts + 502s (memory should change the plan)",
        "title": "payments-api 502s with Redis connection timeouts",
        "service": "payments-api",
        "description": "Since 19:40 UTC checkout requests are failing intermittently. Traffic is "
        "about 1.6x normal because of a weekend campaign. Pods look healthy.",
        "symptoms": "502 rate around 15%, p99 latency 8s, Redis client timeouts in logs.",
        "logs": "redis.exceptions.TimeoutError: Timeout reading from socket\n"
        "WARN pool wait timeout after 5000ms (max_connections=100, in_use=100)\n"
        "ERROR POST /v1/charges 502 upstream timeout",
    },
    {
        "key": "kafka-lag",
        "label": "B. ingest-pipeline: consumer lag + rebalances",
        "title": "ingest-pipeline consumer lag keeps growing",
        "service": "ingest-pipeline",
        "description": "Lag on events.raw is growing by about 1M messages per 10 minutes. "
        "Consumers keep leaving and rejoining the group.",
        "symptoms": "Lag climbing, repeated rebalances, almost no throughput between them.",
        "logs": "WARN Member consumer-3 sending LeaveGroup request: max.poll.interval.ms exceeded\n"
        "INFO Revoking previously assigned partitions",
    },
    {
        "key": "novel-dns",
        "label": "C. data-sync: DNS failures (no relevant history, generic plan expected)",
        "title": "data-sync cron failing with DNS resolution errors",
        "service": "data-sync",
        "description": "Nightly sync job to the partner SFTP host fails since this morning.",
        "symptoms": "Temporary failure in name resolution for sftp.partner.example.",
        "logs": "ERROR socket.gaierror: [Errno -3] Temporary failure in name resolution\n"
        "ERROR sync aborted after 3 retries",
    },
]
