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
        from llm.openrouter_client import OpenRouterClient
        c = OpenRouterClient(s)
        try:
            yield c, False
        finally:
            await c.aclose()
    else:
        yield HeuristicMockLLM(), True


def client_ip(h: BaseHTTPRequestHandler) -> str:
    fwd = h.headers.get("x-forwarded-for") or h.headers.get("x-real-ip") or ""
    return (fwd.split(",")[0].strip() or h.client_address[0])[:64]


def send_json(h: BaseHTTPRequestHandler, obj: dict, code: int = 200) -> None:
    body = json.dumps(obj).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    for k, v in SECURITY_HEADERS.items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)


def _run(fn, *args):
    r = fn(*args)
    return asyncio.run(r) if asyncio.iscoroutine(r) else r


def handle_get(h: BaseHTTPRequestHandler, fn=None) -> None:
    if fn is None:
        return send_json(h, {"error": "method_not_allowed"}, 405)
    try:
        send_json(h, _run(fn))
    except Exception as e:  # noqa: BLE001
        send_json(h, {"error": type(e).__name__}, 500)


def handle_post(h: BaseHTTPRequestHandler, fn=None, limiter: Limiter | None = None) -> None:
    try:
        n = int(h.headers.get("Content-Length", 0))
    except ValueError:
        return send_json(h, {"error": "bad_length"}, 400)
    if n > MAX_BODY:
        h.close_connection = True          # do not read an oversized body at all
        return send_json(h, {"error": "too_large"}, 413)
    raw = h.rfile.read(n)                  # always consume the body so early rejections don't reset the connection
    if fn is None:
        return send_json(h, {"error": "method_not_allowed"}, 405)
    if limiter and not limiter.allow(client_ip(h)):
        return send_json(h, {"error": "rate_limited", "fallback": True}, 429)
    try:
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return send_json(h, {"error": "bad_json"}, 400)
    try:
        send_json(h, _run(fn, data))
    except Exception as e:  # noqa: BLE001 - the game falls back to scripted replies on any failure
        send_json(h, {"error": type(e).__name__, "fallback": True}, 500)


def make_handler(*, post=None, get=None, rate: int = 0, window: int = 600):
    """Convenience for tests: build a handler class from the same functions the api/*.py files use."""
    limiter = Limiter(rate, window) if rate else None

    class handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            handle_get(self, get)

        def do_POST(self):
            handle_post(self, post, limiter)

    return handler
