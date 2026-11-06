"""Environment-driven configuration. No secrets are hardcoded anywhere in the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_PLACEHOLDER_MARKERS = ("REPLACE_WITH", "your-", "<your")


def _clean(value: str | None) -> str | None:
    """Treat empty strings and .env.example placeholders as 'not set'."""
    if value is None:
        return None
    value = value.strip()
    if not value or any(marker in value for marker in _PLACEHOLDER_MARKERS):
        return None
    return value


@dataclass(frozen=True)
class Settings:
    hindsight_base_url: str | None
    hindsight_api_key: str | None
    hindsight_bank_id: str
    hindsight_timeout: float
    groq_api_key: str | None
    groq_model: str
    groq_base_url: str
    db_path: str
    recall_max_tokens: int
    recall_budget: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        env = os.environ
        return cls(
            hindsight_base_url=_clean(env.get("HINDSIGHT_BASE_URL")),
            hindsight_api_key=_clean(env.get("HINDSIGHT_API_KEY")),
            hindsight_bank_id=env.get("HINDSIGHT_BANK_ID", "postmortem-demo").strip(),
            hindsight_timeout=float(env.get("HINDSIGHT_TIMEOUT_SECONDS", "120")),
            groq_api_key=_clean(env.get("GROQ_API_KEY")),
            groq_model=env.get("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
            groq_base_url=env.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip(),
            db_path=env.get("POSTMORTEM_DB_PATH", "postmortem.db"),
            recall_max_tokens=int(env.get("RECALL_MAX_TOKENS", "3000")),
            recall_budget=env.get("RECALL_BUDGET", "mid").strip(),
        )

    def missing(self) -> list[str]:
        """Names of required variables that are not configured."""
        missing = []
        if not self.hindsight_base_url:
            missing.append("HINDSIGHT_BASE_URL")
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        return missing
