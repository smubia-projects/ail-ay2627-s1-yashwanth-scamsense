"""Rate-limit adapter for ScamSense.

Wraps the shared engine (rate_limit_engine.py, vendored unmodified) with this project's slug and one bucket per
LLM-calling route. The engine handles X-Forwarded-For, central config, event mode, the kill switch (503), caching
and fail-open. With no Upstash env vars set, limiting is disabled (local dev).
"""
from __future__ import annotations

import os

from rate_limit_engine import RateLimiter


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


limiter = RateLimiter(
    # Slug = full project folder name (canonical identifier across code + control sheet).
    project="ail-ay2627-s1-yashwanth-scamsense",
    buckets={
        "chat": _int("RATE_LIMIT_CHAT_MAX", 5),    # in-character reply (intent classification + reply)
        "probe": _int("RATE_LIMIT_PROBE_MAX", 5),  # intent classification only (used when chat is unavailable)
        "scan": _int("RATE_LIMIT_SCAN_MAX", 5),    # full ScamSense pipeline over a storyline
    },
    redis_url=os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL", ""),
    redis_token=os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN", ""),
    default_window=_int("RATE_LIMIT_WINDOW_SECONDS", 432000),
)


def check_rate_limit(request, bucket: str) -> None:
    """Raise 503 if the demo is paused, or 429 (with queries_used) if over the limit."""
    limiter.enforce(request, bucket)
