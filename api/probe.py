import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make the sibling helper importable however the runtime starts us
import _lib  # noqa: E402

async def _probe(data: dict) -> dict:
    from sim import gameapi
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.probe(llm, str(data.get("text", "")), list(data.get("intents", [])), demo)


_LIMITER = _lib.Limiter(int(os.getenv("GAME_RATE_CHAT", "90")), 600)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        _lib.handle_get(self, None)

    def do_POST(self):
        _lib.handle_post(self, _probe, _LIMITER)
