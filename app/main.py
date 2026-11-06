"""Composition root: builds real dependencies from environment variables."""

from __future__ import annotations

from hindsight_client import Hindsight

from app.agent.llm import GroqClient
from app.api import create_app
from app.config import Settings
from app.memory.local_sqlite import LocalSqliteMemoryClient
from app.memory.service import MemoryService
from app.storage import Store


def build() -> object:
    settings = Settings.from_env()
    memory: MemoryService | None = None
    if settings.hindsight_base_url:
        client: object
        if settings.hindsight_base_url.lower() in ("local", "sqlite", "local-sqlite"):
            client = LocalSqliteMemoryClient()
        else:
            client = Hindsight(
                base_url=settings.hindsight_base_url,
                api_key=settings.hindsight_api_key,
                timeout=settings.hindsight_timeout,
            )
        memory = MemoryService(
            client, settings.hindsight_bank_id, settings.recall_max_tokens, settings.recall_budget
        )
    llm = GroqClient(settings.groq_api_key, settings.groq_model, settings.groq_base_url)
    return create_app(settings, memory, llm, Store(settings.db_path))


app = build()
