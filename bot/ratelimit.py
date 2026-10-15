"""Sliding-window rate limiter, keyed by Telegram user id. In-memory only."""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_events: int, window_s: float, clock=time.monotonic) -> None:
        self.max, self.window, self.clock = max_events, window_s, clock
        self._ev: dict[int, deque[float]] = defaultdict(deque)

    def check(self, key: int) -> tuple[bool, float]:
        """Record an event if allowed. Returns (allowed, seconds_until_allowed)."""
        now = self.clock()
        q = self._ev[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False, self.window - (now - q[0])
        q.append(now)
        return True, 0.0

    def gc(self) -> None:
        now = self.clock()
        for k in [k for k, q in self._ev.items() if not q or now - q[-1] > self.window]:
            del self._ev[k]
