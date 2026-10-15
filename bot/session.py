"""In-memory, TTL-bound per-chat state. Nothing is written to disk or a database.

Raw message text is dropped the moment an analysis starts; only the (already redacted) Report is kept,
briefly, so the Evidence / Warn-family buttons work."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pipeline.schemas import Report


@dataclass
class Session:
    items: list[tuple[str | None, str]] = field(default_factory=list)  # (sender or None, text)
    report: Report | None = None
    collecting: bool = False
    status_msg_id: int | None = None
    practice: dict | None = None
    touched: float = field(default_factory=time.monotonic)

    @property
    def n_chars(self) -> int:
        return sum(len(t) for _, t in self.items)

    def senders(self) -> list[str]:
        return list(dict.fromkeys(s for s, _ in self.items if s))

    def clear_raw(self) -> None:
        self.items.clear()
        self.collecting = False


class SessionStore:
    def __init__(self, ttl_s: int = 1800, max_sessions: int = 5000) -> None:
        self.ttl_s, self.max_sessions = ttl_s, max_sessions
        self._d: dict[int, Session] = {}

    def get(self, chat_id: int) -> Session:
        self._evict()
        s = self._d.get(chat_id)
        if s is None:
            s = self._d[chat_id] = Session()
        s.touched = time.monotonic()
        return s

    def drop(self, chat_id: int) -> None:
        self._d.pop(chat_id, None)

    def _evict(self) -> None:
        now = time.monotonic()
        for k in [k for k, v in self._d.items() if now - v.touched > self.ttl_s]:
            del self._d[k]
        if len(self._d) > self.max_sessions:  # crude cap: drop oldest
            for k, _ in sorted(self._d.items(), key=lambda kv: kv[1].touched)[: len(self._d) - self.max_sessions]:
                del self._d[k]

    def __len__(self) -> int:
        return len(self._d)
