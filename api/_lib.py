"""Shared helpers for the Vercel serverless functions. Stateless: the browser sends the conversation each time.

Vercel treats files starting with "_" as non-routes, so this is a library, not an endpoint.
Nothing here logs or stores player text.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MAX_BODY = 64_000
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class Limiter:
    """Best-effort per-IP sliding window. Serverless instances do not share memory, so this only slows down a single warm
    instance; the real spending cap must be set in the LLM provider's console (see README)."""

    def __init__(self, max_events: int, window_s: int) -> None:
        self.max, self.window, self._ev = max_events, window_s, defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, q = time.monotonic(), self._ev[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True


@asynccontextmanager
async def llm_client():
    """Yield (llm, demo). A fresh client per request: no state is shared between invocations."""
    from config import get_settings
    from llm.mock import HeuristicMockLLM

    s = get_settings()
    if s.llm_api_key:
        from llm.groq_client import GroqClient
        c = GroqClient(s)
        try:
            yield c, False
        finally:
            await c.aclose()
    else:
        yield HeuristicMockLLM(), True


def client_ip(h: BaseHTTPRequestHandler) -> str:
    fwd = h.headers.get("x-forwarded-for") or h.headers.get("x-real-ip") or ""
    return (fwd.split(",")[0].strip() or h.client_address[0])[:64]


def make_handler(*, post=None, get=None, rate: int = 0, window: int = 600):
    """Build the `handler` class Vercel's Python runtime looks for. `post(data) -> dict` / `get() -> dict` may be sync or async."""
    limiter = Limiter(rate, window) if rate else None

    class handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # never log request lines
            pass

        def _send(self, obj: dict, code: int = 200) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _run(self, fn, *args):
            r = fn(*args)
            return asyncio.run(r) if asyncio.iscoroutine(r) else r

        def do_GET(self):
            if get is None:
                return self._send({"error": "method_not_allowed"}, 405)
            try:
                self._send(self._run(get))
            except Exception as e:  # noqa: BLE001
                self._send({"error": type(e).__name__}, 500)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._send({"error": "bad_length"}, 400)
            if n > MAX_BODY:
                self.close_connection = True      # do not read an oversized body at all
                return self._send({"error": "too_large"}, 413)
            raw = self.rfile.read(n)          # always consume the body so early rejections don't reset the connection
            if post is None:
                return self._send({"error": "method_not_allowed"}, 405)
            if limiter and not limiter.allow(client_ip(self)):
                return self._send({"error": "rate_limited", "fallback": True}, 429)
            try:
                data = json.loads(raw or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                return self._send({"error": "bad_json"}, 400)
            try:
                self._send(self._run(post, data))
            except Exception as e:  # noqa: BLE001 - the game falls back to scripted replies on any failure
                self._send({"error": type(e).__name__, "fallback": True}, 500)

    return handler
