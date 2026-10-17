"""Preview the Vercel deployment locally: static game from a built `public/` + the four api/*.py functions on one port.

    python scripts/preview_vercel.py            # then open http://127.0.0.1:3000
Uses your local .env (GROQ_API_KEY) exactly like Vercel would use its environment variables.
"""
from __future__ import annotations

import argparse
import importlib.util
import mimetypes
import shutil
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"api_{name}", ROOT / "api" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3000)
    a = ap.parse_args()

    public = Path(tempfile.mkdtemp(prefix="scamsense_public_"))
    shutil.copytree(ROOT / "game", public / "game")           # same as vercel.json buildCommand: cp -r game public/
    backends = {}
    for name in ("info", "chat", "probe", "scan"):
        srv = HTTPServer(("127.0.0.1", 0), load(name))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        backends[name] = srv.server_port

    class Front(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _proxy(self):
            name = self.path.split("?")[0].removeprefix("/api/").strip("/")
            if name not in backends:
                return self.send_error(404)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))) if self.command == "POST" else None
            req = urllib.request.Request(f"http://127.0.0.1:{backends[name]}/", data=body, method=self.command,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    code, data = r.status, r.read()
            except urllib.error.HTTPError as e:
                code, data = e.code, e.read()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.startswith("/api/"):
                return self._proxy()
            f = public / ("game/index.html" if path == "/" else path.lstrip("/"))
            if not f.is_file() or public not in f.resolve().parents:
                return self.send_error(404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = _proxy

    print(f"Vercel preview on http://127.0.0.1:{a.port}")
    HTTPServer(("127.0.0.1", a.port), Front).serve_forever()


if __name__ == "__main__":
    main()
