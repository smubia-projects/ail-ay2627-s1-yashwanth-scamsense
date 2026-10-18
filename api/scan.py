import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make the sibling helper importable however the runtime starts us
import _lib  # noqa: E402

async def _scan(data: dict) -> dict:
    from config import get_settings
    from sim import gameapi
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.scan_storyline(llm, get_settings(), list(data.get("messages", [])), demo)


_LIMITER = _lib.Limiter(int(os.getenv("GAME_RATE_SCAN", "10")), 600)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        _lib.handle_get(self, None)

    def do_POST(self):
        _lib.handle_post(self, _scan, _LIMITER)
