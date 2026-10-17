from http.server import BaseHTTPRequestHandler  # noqa: F401  (Vercel detects the `handler` class)

import _lib


def _info() -> dict:
    from config import get_settings
    return {"demo": not get_settings().llm_api_key}


handler = _lib.make_handler(get=_info)
