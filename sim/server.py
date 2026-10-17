"""Local Telegram simulator: a browser chat UI that drives the REAL bot handlers (bot/handlers.py) through fake
Telegram objects. No Telegram account, bot token or network access to Telegram is needed.

    python -m sim.server            # then open http://127.0.0.1:8765

LLM: uses Groq if GROQ_API_KEY is set, otherwise the offline keyword stand-in (clearly bannered DEMO MODE).
Everything is in memory; nothing is written to disk.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from bot import handlers
from config import get_settings
from bot.ratelimit import RateLimiter
from llm.mock import HeuristicMockLLM

INDEX = Path(__file__).with_name("index.html")
GAME_DIR = Path(__file__).resolve().parent.parent / "game"
GAME_FILES = {"index.html": "text/html; charset=utf-8", "style.css": "text/css; charset=utf-8",
              "game.js": "application/javascript; charset=utf-8", "levels.js": "application/javascript; charset=utf-8"}
CHAT_ID, USER_ID = 1, 1


class FakeBotState:
    """The 'Telegram server': an ordered list of messages the bot has sent, with inline keyboards."""

    def __init__(self) -> None:
        self.msgs: list[dict] = []
        self._next = 1

    def add(self, **kw) -> dict:
        m = {"id": self._next, "from": "bot", "html": "", "photo": None, "buttons": [], "deleted": False, **kw}
        self._next += 1
        self.msgs.append(m)
        return m

    def get(self, mid: int) -> dict | None:
        return next((m for m in self.msgs if m["id"] == mid), None)


def _buttons(markup) -> list[list[dict]]:
    if markup is None:
        return []
    return [[{"text": b.text, "data": b.callback_data} for b in row] for row in markup.inline_keyboard]


class Sim:
    def __init__(self) -> None:
        s = get_settings()
        demo = False
        if s.llm_api_key:
            from llm.groq_client import GroqClient
            llm = GroqClient(s)
        else:
            llm, demo = HeuristicMockLLM(), True
        self.demo = demo
        from sim import gamechat
        self.personas = gamechat.load_personas()
        self.state = FakeBotState()
        self.ctx = SimpleNamespace(
            application=SimpleNamespace(bot_data={"ctx": handlers.Ctx(llm, s, demo)}),
            bot=SimpleNamespace(delete_message=self._delete),
        )

    async def _delete(self, chat_id: int, message_id: int) -> None:
        m = self.state.get(message_id)
        if m:
            m["deleted"] = True

    # ---- fake telegram objects -------------------------------------------------
    def _wrap(self, m: dict):
        state = self.state

        async def edit_text(text, parse_mode=None, reply_markup=None, **kw):
            m["html"] = text
            m["buttons"] = _buttons(reply_markup)

        return SimpleNamespace(message_id=m["id"], edit_text=edit_text, text=text_of(m))

    def _chat(self):
        state = self.state
        sim = self

        async def send_message(text, parse_mode=None, reply_markup=None, **kw):
            return sim._wrap(state.add(html=text, buttons=_buttons(reply_markup)))

        async def send_photo(photo, caption=None, **kw):
            data = base64.b64encode(photo.read()).decode()
            return sim._wrap(state.add(html=caption or "", photo="data:image/png;base64," + data))

        async def send_action(*a, **kw):
            return None

        return SimpleNamespace(id=CHAT_ID, send_message=send_message, send_photo=send_photo, send_action=send_action)

    def _update(self, text: str | None = None, forward_from: str | None = None, callback: tuple[str, int] | None = None):
        fo = SimpleNamespace(sender_user=SimpleNamespace(full_name=forward_from, username=None)) if forward_from else None
        msg = SimpleNamespace(text=text, caption=None, forward_origin=fo, photo=None)
        cq = None
        if callback:
            data, mid = callback
            target = self.state.get(mid)

            async def answer(*a, **kw):
                return None

            async def edit_message_text(text, parse_mode=None, reply_markup=None, **kw):
                if target:
                    target["html"] = text
                    target["buttons"] = _buttons(reply_markup)

            cq = SimpleNamespace(data=data, answer=answer, edit_message_text=edit_message_text)
        return SimpleNamespace(effective_chat=self._chat(), effective_user=SimpleNamespace(id=USER_ID),
                               effective_message=msg, callback_query=cq)

    # ---- user actions ----------------------------------------------------------
    async def user_text(self, text: str, forward_from: str | None) -> None:
        text = text.strip()
        if not text:
            return
        self.state.add(**{"from": "user", "html": "", "text": text, "forward_from": forward_from})
        if text.startswith("/") and not forward_from:
            cmd = text.split()[0][1:].split("@")[0].lower()
            fn = {"start": handlers.cmd_start, "help": handlers.cmd_start, "privacy": handlers.cmd_privacy,
                  "new": handlers.cmd_new, "analyse": handlers.cmd_analyse, "analyze": handlers.cmd_analyse}.get(cmd)
            if fn:
                await fn(self._update(), self.ctx)
                return
        await handlers.on_message(self._update(text=text, forward_from=forward_from), self.ctx)

    async def press(self, data: str, mid: int) -> None:
        await handlers.on_button(self._update(callback=(data, mid)), self.ctx)

    async def scan(self, msgs: list[dict]) -> dict:
        from sim import gameapi
        c = self.ctx.application.bot_data["ctx"]
        return await gameapi.scan_storyline(c.llm, c.s, msgs, self.demo)

    async def probe(self, text: str, intents: list[dict]) -> dict:
        from sim import gameapi
        c = self.ctx.application.bot_data["ctx"]
        return await gameapi.probe(c.llm, text, intents, self.demo)

    async def game_chat(self, data: dict) -> dict:
        from sim import gameapi
        c = self.ctx.application.bot_data["ctx"]
        return await gameapi.game_chat(c.llm, self.personas, data, self.demo)

    def reset(self) -> None:
        self.ctx.application.bot_data["ctx"].sessions.drop(CHAT_ID)
        self.state = FakeBotState()


def text_of(m: dict) -> str:
    return m.get("html", "")


def make_server(port: int) -> tuple[ThreadingHTTPServer, Sim]:
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    sim = Sim()
    scan_limit = RateLimiter(40, 600)
    probe_limit = RateLimiter(400, 600)

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=120)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console free of request lines (and of any message text)
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _state(self):
            return {"demo": sim.demo, "messages": [m for m in sim.state.msgs if not m["deleted"]]}

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html", "/sim") or path.startswith("/game/"):
                if path in ("/", "/index.html"):
                    f, ctype = GAME_DIR / "index.html", GAME_FILES["index.html"]
                elif path == "/sim":
                    f, ctype = INDEX, "text/html; charset=utf-8"
                else:
                    name = path[len("/game/"):]
                    if name not in GAME_FILES or name == "index.html":
                        return self.send_error(404)
                    f, ctype = GAME_DIR / name, GAME_FILES[name]
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/info"):
                self._json({"demo": sim.demo})
            elif self.path.startswith("/api/state"):
                self._json(self._state())
            else:
                self.send_error(404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            try:
                if self.path == "/api/send":
                    run(sim.user_text(str(data.get("text", ""))[:20000], (data.get("forward_from") or "").strip()[:40] or None))
                elif self.path == "/api/press":
                    run(sim.press(str(data.get("data", "")), int(data.get("msg_id", 0))))
                elif self.path == "/api/scan":
                    if not scan_limit.check(0)[0]:
                        return self._json({"error": "rate_limited"}, 429)
                    return self._json(run(sim.scan(list(data.get("messages", [])))))
                elif self.path == "/api/chat":
                    if not probe_limit.check(1)[0]:
                        return self._json({"fallback": True})
                    return self._json(run(sim.game_chat(data)))
                elif self.path == "/api/probe":
                    if not probe_limit.check(0)[0]:
                        return self._json({"intent": None, "fallback": True})
                    return self._json(run(sim.probe(str(data.get("text", "")), list(data.get("intents", [])))))
                elif self.path == "/api/reset":
                    sim.reset()
                else:
                    return self.send_error(404)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": type(e).__name__}, 500)
            self._json(self._state())

    return ThreadingHTTPServer(("127.0.0.1", port), H), sim


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv, sim = make_server(a.port)
    url = f"http://127.0.0.1:{a.port}"
    print(f"ScamSense simulator on {url}  ({'DEMO MODE: offline keyword stand-in' if sim.demo else 'real LLM'})")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
