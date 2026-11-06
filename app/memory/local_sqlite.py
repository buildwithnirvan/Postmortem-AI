"""Local SQLite-backed memory client for offline or standalone testing when Hindsight Cloud is unavailable."""

from __future__ import annotations

import json
import re
import sqlite3
from types import SimpleNamespace
from typing import Any


class LocalSqliteMemoryClient:
    """Drop-in substitute for the Hindsight client using local SQLite."""

    def __init__(self, db_path: str = "postmortem_memory.db") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_docs (
                id TEXT PRIMARY KEY,
                bank_id TEXT,
                content TEXT,
                context TEXT,
                tags TEXT,
                metadata TEXT,
                timestamp TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def get_version(self) -> Any:
        return SimpleNamespace(api_version="local-memory-sqlite-1.0")

    def create_bank(self, bank_id: str, retain_mission: str | None = None) -> None:
        pass

    def retain(
        self,
        bank_id: str,
        document_id: str,
        content: str,
        context: str | None = None,
        tags: list[str] | None = None,
        timestamp: Any = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tags_json = json.dumps(tags or [])
        metadata_json = json.dumps(metadata or {})
        ts_str = str(timestamp) if timestamp is not None else None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memory_docs (id, bank_id, content, context, tags, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, bank_id, content, context, tags_json, metadata_json, ts_str),
        )
        self._conn.commit()

    def retain_batch(self, bank_id: str, items: list[dict[str, Any]], **kwargs: Any) -> None:
        for it in items:
            self.retain(
                bank_id=bank_id,
                document_id=it["document_id"],
                content=it["content"],
                context=it.get("context"),
                tags=it.get("tags"),
                timestamp=it.get("timestamp"),
                metadata=it.get("metadata"),
            )

    def recall(
        self, bank_id: str, query: str, max_tokens: int = 3000, budget: str = "mid", **kwargs: Any
    ) -> Any:
        query_words = set(re.findall(r"[a-z0-9\-]{3,}", query.lower()))
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id, content, context, tags FROM memory_docs WHERE bank_id = ?",
            (bank_id,),
        )
        results = []
        for doc_id, content, context, tags_json in cur.fetchall():
            tags = json.loads(tags_json or "[]")
            content_words = set(re.findall(r"[a-z0-9\-]{3,}", content.lower()))
            overlap = query_words & content_words
            if overlap:
                score = len(overlap) / max(len(query_words), 1)
                results.append(
                    SimpleNamespace(
                        id=doc_id,
                        text=content,
                        type="experience",
                        context=context,
                        tags=tags,
                        scores=SimpleNamespace(final=score),
                        occurred_start=None,
                        mentioned_at=None,
                    )
                )
        results.sort(key=lambda x: x.scores.final, reverse=True)
        return SimpleNamespace(results=results[:15])

    def list_memories(
        self,
        bank_id: str,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> Any:
        cur = self._conn.cursor()
        if search_query:
            pattern = f"%{search_query.strip()}%"
            cur.execute(
                """
                SELECT id, content, context, tags FROM memory_docs 
                WHERE bank_id = ? AND (content LIKE ? OR tags LIKE ?)
                ORDER BY rowid DESC LIMIT ? OFFSET ?
                """,
                (bank_id, pattern, pattern, limit, offset),
            )
        else:
            cur.execute(
                "SELECT id, content, context, tags FROM memory_docs WHERE bank_id = ? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (bank_id, limit, offset),
            )
        items = [
            SimpleNamespace(
                id=r[0],
                text=r[1],
                fact_type="experience",
                context=r[2],
                tags=json.loads(r[3] or "[]"),
                mentioned_at=None,
                var_date=None,
            )
            for r in cur.fetchall()
        ]
        if search_query:
            pattern = f"%{search_query.strip()}%"
            cur.execute(
                "SELECT COUNT(*) FROM memory_docs WHERE bank_id = ? AND (content LIKE ? OR tags LIKE ?)",
                (bank_id, pattern, pattern),
            )
        else:
            cur.execute("SELECT COUNT(*) FROM memory_docs WHERE bank_id = ?", (bank_id,))
        total = cur.fetchone()[0]
        return SimpleNamespace(items=items, total=total)

    def delete_bank(self, bank_id: str, **kwargs: Any) -> None:
        self._conn.execute("DELETE FROM memory_docs WHERE bank_id = ?", (bank_id,))
        self._conn.commit()
