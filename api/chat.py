import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make the sibling helper importable however the runtime starts us
import _lib  # noqa: E402

_PERSONAS = None


async def _chat(data: dict) -> dict:
    global _PERSONAS
    from sim import gameapi, gamechat
    if _PERSONAS is None:
        _PERSONAS = gamechat.load_personas()
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.game_chat(llm, _PERSONAS, data, demo)


_LIMITER = _lib.Limiter(int(os.getenv("GAME_RATE_CHAT", "90")), 600)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        _lib.handle_get(self, None)

    def do_POST(self):
        _lib.handle_post(self, _chat, _LIMITER)
