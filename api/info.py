import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make the sibling helper importable however the runtime starts us
import _lib  # noqa: E402


def _info() -> dict:
    from config import get_settings
    return {"demo": not get_settings().llm_api_key}


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        _lib.handle_get(self, _info)

    def do_POST(self):
        _lib.handle_post(self, None)
