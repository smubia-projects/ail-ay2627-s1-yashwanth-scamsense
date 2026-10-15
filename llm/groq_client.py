"""Groq client over the OpenAI-compatible REST API (httpx; no vendor SDK needed).

Model choice: openai/gpt-oss-120b (strong instruction following, reliable JSON) with
llama-3.3-70b-versatile as automatic fallback. Both are Groq production models.
Llama Prompt Guard 2 is exposed through classify_injection().
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from config import Settings, get_settings
from llm.base import LLMClient, LLMError

log = logging.getLogger("scamsense.llm")


class GroqClient(LLMClient):
    name = "groq"

    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        if not self.s.llm_api_key:
            raise LLMError("GROQ_API_KEY is not set")
        self._http = httpx.AsyncClient(
            base_url=self.s.llm_base_url,
            headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
            timeout=self.s.llm_timeout_s,
        )

    async def _chat(self, model: str, messages: list[dict], *, json_mode: bool, max_tokens: int,
                    temperature: float = 0.0) -> str:
        payload: dict = {"model": model, "messages": messages, "temperature": temperature,
                         "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        for attempt in range(4):
            try:
                r = await self._http.post("/chat/completions", json=payload)
            except httpx.HTTPError as e:
                raise LLMError(f"transport:{type(e).__name__}") from e
            if r.status_code == 429:  # rate limited -> short backoff then retry
                wait = min(float(r.headers.get("retry-after", 2 * (attempt + 1))), 15)
                await asyncio.sleep(wait)
                continue
            if r.status_code >= 400:
                raise LLMError(f"http:{r.status_code}")
            try:
                return r.json()["choices"][0]["message"]["content"] or ""
            except Exception as e:  # noqa: BLE001
                raise LLMError("bad_response_shape") from e
        raise LLMError("rate_limited")

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1800) -> str:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            return await self._chat(self.s.llm_model, msgs, json_mode=True, max_tokens=max_tokens)
        except LLMError as e:
            if self.s.llm_fallback_model and self.s.llm_fallback_model != self.s.llm_model:
                log.warning("primary model failed (%s); using fallback", e)
                return await self._chat(self.s.llm_fallback_model, msgs, json_mode=True,
                                        max_tokens=max_tokens)
            raise

    async def complete_text(self, system: str, user: str, *, model: str | None = None,
                            max_tokens: int = 400) -> str:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return await self._chat(model or self.s.llm_model, msgs, json_mode=False, max_tokens=max_tokens)

    async def classify_injection(self, text: str) -> float | None:
        """Llama Prompt Guard 2 returns a single score string (probability of injection/jailbreak).

        Model context is 512 tokens, so long inputs are scored in overlapping chunks (max taken).
        """
        if not self.s.use_prompt_guard:
            return None
        chunks = [text[i : i + 1200] for i in range(0, max(len(text), 1), 1000)][:6]
        best = 0.0
        try:
            scores = await asyncio.gather(*[
                self._chat(self.s.prompt_guard_model, [{"role": "user", "content": c}],
                           json_mode=False, max_tokens=5)
                for c in chunks if c.strip()
            ])
        except LLMError:
            return None
        for s in scores:
            m = re.search(r"\d*\.?\d+", s or "")
            if m:
                best = max(best, float(m.group(0)))
        return min(best, 1.0)

    async def aclose(self) -> None:
        await self._http.aclose()
