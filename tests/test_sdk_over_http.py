"""Runs the REAL hindsight-client SDK over HTTP against a tiny in-process STUB server.

What this proves: our calls serialise correctly through the real SDK (datetime timestamps,
tags, metadata, batch items), real SDK response models parse, and MemoryService maps them.
What it does NOT prove: Hindsight's own behaviour (fact extraction, ranking). For that use
tests/test_integration_hindsight.py against a real server.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from hindsight_client import Hindsight

from app.memory.service import MemoryService
from app.models import IncidentInput, OutcomeInput


class _Stub(BaseHTTPRequestHandler):
    store: dict[str, dict[str, Any]] = {}
    seen: list[tuple[str, str, Any]] = []

    def log_message(self, *a: Any) -> None:  # silence
        pass

    def _send(self, body: Any, status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> Any:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _route(self, method: str) -> None:
        path = self.path.split("?")[0]
        body = self._body() if method in ("POST", "PUT", "PATCH") else None
        _Stub.seen.append((method, path, body))
        if path == "/version":
            features = {
                k: False
                for k in (
                    "observations",
                    "mcp",
                    "worker",
                    "bank_config_api",
                    "bank_llm_health",
                    "file_upload_api",
                    "document_export_api",
                    "document_import_api",
                    "audit_log",
                    "llm_trace",
                    "store_document_text",
                )
            }
            return self._send({"api_version": "stub-1.0", "features": features})
        m = re.fullmatch(r"/v1/default/banks/([^/]+)", path)
        if m and method == "PUT":
            return self._send(
                {
                    "bank_id": m[1],
                    "name": m[1],
                    "mission": "",
                    "disposition": {"skepticism": 3, "literalism": 3, "empathy": 3},
                }
            )
        if m and method == "DELETE":
            _Stub.store.clear()
            return self._send({"success": True})
        if path.endswith("/memories") and method == "POST":
            for item in body["items"]:
                _Stub.store[item["document_id"]] = item
            return self._send(
                {"success": True, "bank_id": "b", "items_count": len(body["items"]), "async": False}
            )
        if path.endswith("/memories/recall") and method == "POST":
            q = set(re.findall(r"[a-z0-9\-]{4,}", body["query"].lower()))
            hits = []
            for doc_id, item in _Stub.store.items():
                if len(q & set(re.findall(r"[a-z0-9\-]{4,}", item["content"].lower()))) >= 3:
                    hits.append(
                        {
                            "id": doc_id,
                            "text": item["content"],
                            "type": "experience",
                            "tags": item.get("tags"),
                            "context": item.get("context"),
                        }
                    )
            return self._send({"results": hits})
        if path.endswith("/memories/list") and method == "GET":
            items = [
                {"id": k, "text": v["content"], "tags": v.get("tags"), "fact_type": "experience"}
                for k, v in _Stub.store.items()
            ]
            return self._send({"items": items, "total": len(items), "limit": 50, "offset": 0})
        self._send({"detail": f"stub: no route {method} {path}"}, 404)

    def do_GET(self) -> None:
        self._route("GET")  # noqa: E701

    def do_POST(self) -> None:
        self._route("POST")  # noqa: E701

    def do_PUT(self) -> None:
        self._route("PUT")  # noqa: E701

    def do_DELETE(self) -> None:
        self._route("DELETE")  # noqa: E701


@pytest.fixture()
def svc():
    _Stub.store, _Stub.seen = {}, []
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = Hindsight(base_url=f"http://127.0.0.1:{server.server_port}", api_key="k", timeout=10)
    yield MemoryService(client, "stub-bank")
    server.shutdown()


INC = IncidentInput(
    title="payments-api Redis timeouts",
    service="payments-api",
    description="Checkout failing",
    symptoms="502s and Redis timeouts",
    logs="ERROR redis timeout",
)


def test_roundtrip_through_real_sdk(svc):
    assert svc.health() == "stub-1.0"
    svc.retain_incident("INC-1001", INC)
    svc.retain_outcomes(
        "INC-1001",
        INC,
        [
            (
                OutcomeInput(action_id="a1", result="failed", notes="came back"),
                "Restart payments-api pods",
            ),
            (OutcomeInput(action_id="a2", result="not_tried"), "Check metrics"),
            (OutcomeInput(action_id="a3", result="worked"), "Raise Redis pool max_connections"),
        ],
    )
    methods = [(m, p.rsplit("/", 1)[-1]) for m, p, _ in _Stub.seen]
    assert ("PUT", "stub-bank") in methods and ("POST", "memories") in methods

    sent = [b for m, p, b in _Stub.seen if p.endswith("/memories") and m == "POST"]
    first = sent[0]["items"][0]
    assert first["document_id"] == "INC-1001:report" and "service:payments-api" in first["tags"]
    assert first["timestamp"]  # datetime serialised by the SDK
    assert len(sent[1]["items"]) == 2  # not_tried excluded on the wire

    memories = svc.recall_for_incident(INC)
    by_id = {m.id: m for m in memories}
    assert by_id["INC-1001:outcome:a1"].outcome == "failed"
    assert by_id["INC-1001:outcome:a3"].outcome == "worked"

    listing = svc.list_memories()
    assert listing["total"] == 3 and listing["items"][0].tags

    svc.reset()
    assert svc.list_memories()["total"] == 0


def test_server_error_becomes_memory_unavailable(svc):
    from app.memory.service import MemoryUnavailableError

    svc._client = Hindsight(base_url="http://127.0.0.1:9", api_key="k", timeout=2, max_attempts=1)
    with pytest.raises(MemoryUnavailableError):
        svc.health()


def test_real_sdk_works_from_many_threads(svc):
    """Regression: the SDK sync wrapper broke when called from different threads (as FastAPI
    does). MemoryService must funnel calls through one worker thread."""
    from concurrent.futures import ThreadPoolExecutor

    svc.retain_incident("INC-1", INC)
    with ThreadPoolExecutor(8) as pool:
        results = list(
            pool.map(lambda _: (svc.health(), len(svc.recall_for_incident(INC))), range(40))
        )
    assert all(version == "stub-1.0" for version, _ in results)
