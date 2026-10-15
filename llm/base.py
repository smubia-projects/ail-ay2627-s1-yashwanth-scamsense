"""Thin, swappable LLM interface. Pipeline code depends only on this."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Transport / timeout / rate-limit failure."""


class LLMOutputError(LLMError):
    """Model replied but the output was not valid JSON for the schema."""


class LLMClient(ABC):
    name: str = "base"

    @abstractmethod
    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1800) -> str:
        """Return the raw text of a JSON-object completion."""

    async def classify_injection(self, text: str) -> float | None:
        """Optional: prompt-injection score in [0,1]; None when unsupported."""
        return None

    async def structured(self, schema: type[T], system: str, user: str, *, retries: int = 1,
                         max_tokens: int = 1800) -> T:
        """Call -> parse -> validate; one retry on transport error OR invalid output."""
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                raw = await self.complete_json(system, user, max_tokens=max_tokens)
                return parse_model(schema, raw)
            except (LLMError, ValidationError, json.JSONDecodeError) as e:  # noqa: PERF203
                last = e
        raise LLMOutputError(f"{type(last).__name__}") from last


def _extract_json_blob(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    if raw.startswith("{"):
        return raw
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw


def parse_model(schema: type[T], raw: str) -> T:
    return schema.model_validate(json.loads(_extract_json_blob(raw)))
