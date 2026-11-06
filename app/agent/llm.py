"""Minimal Groq (OpenAI-compatible) chat client that returns parsed JSON.

The hackathon guide warns that Groq models can fail structured output / function calling,
so we ask for a JSON object, validate it, and retry with a repair hint before giving up.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx


class LLMUnavailableError(RuntimeError):
    """LLM not configured, unreachable, rate limited, or kept returning invalid output."""


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating code fences and stray prose."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model returned JSON that is not an object")
    return value


class GroqClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._max_attempts = max_attempts

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._api_key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured.")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error = "unknown error"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._http.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                    },
                )
            except httpx.HTTPError as exc:
                last_error = f"network error: {exc}"
                time.sleep(min(2 ** (attempt - 1), 4) * 0.5)
                continue

            if response.status_code in (401, 403):
                raise LLMUnavailableError(
                    "Groq rejected the API key (401/403). Check GROQ_API_KEY."
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"Groq returned HTTP {response.status_code}"
                time.sleep(min(2 ** (attempt - 1), 4) * 0.5)
                continue
            if response.status_code >= 400:
                # Often a failed JSON-mode generation; retry with a repair hint.
                last_error = f"Groq returned HTTP {response.status_code}: {response.text[:200]}"
                messages = messages[:2] + [
                    {"role": "user", "content": "Reply with ONLY one valid JSON object."}
                ]
                continue

            try:
                content = response.json()["choices"][0]["message"]["content"]
                return extract_json(content or "")
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                last_error = f"invalid model output: {exc}"
                messages = messages[:2] + [
                    {
                        "role": "user",
                        "content": "Your last reply was not valid JSON. Reply with ONLY one "
                        "valid JSON object matching the schema.",
                    }
                ]
        raise LLMUnavailableError(f"LLM failed after {self._max_attempts} attempts: {last_error}")
