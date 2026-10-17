"""The Vercel serverless functions (api/*.py) and deployment config, tested offline against a fake LLM."""
import contextlib
import importlib.util
import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from llm.mock import HeuristicMockLLM
from tests.test_game_chat import FakeLLM

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "api"
sys.path.insert(0, str(API))          # Vercel puts the function's directory on the path; so do we
import _lib  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"api_{name}", API / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()


def call(url, data=None, method=None, raw=None):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body is not None else "GET"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def with_llm(monkeypatch, llm, demo=False):
    @contextlib.asynccontextmanager
    async def fake():
        yield llm, demo
    monkeypatch.setattr(_lib, "llm_client", fake)


# ---------------------------------------------------------------- routes
def test_info_get_only_and_security_headers():
    with serve(load("info").handler) as u:
        code, body, hdr = call(u)
        assert code == 200 and isinstance(body["demo"], bool)
        assert hdr.get("X-Content-Type-Options") == "nosniff" and hdr.get("Cache-Control") == "no-store"
        assert call(u, {"x": 1})[0] == 405


def test_chat_returns_an_in_character_reply(monkeypatch):
    with_llm(monkeypatch, FakeLLM("callback", "Please use our direct line."))
    with serve(load("chat").handler) as u:
        code, body, _ = call(u, {"case": 6, "chat": "wong", "history": [], "text": "I'll call MAS myself", "counts": {"callback": 1}, "factCounts": {}})
    assert code == 200 and body["reply"] == "Please use our direct line." and body["signal"]["kind"] == "tell"


def test_chat_without_a_key_falls_back_to_scripted_replies(monkeypatch):
    with_llm(monkeypatch, HeuristicMockLLM(), demo=True)
    with serve(load("chat").handler) as u:
        assert call(u, {"case": 6, "chat": "wong", "text": "hi"})[1] == {"fallback": True}


def test_probe_classifies(monkeypatch):
    with_llm(monkeypatch, FakeLLM("video"))
    with serve(load("probe").handler) as u:
        code, body, _ = call(u, {"text": "can we video call", "intents": [{"id": "video", "desc": "asks for a video call"}]})
    assert code == 200 and body == {"intent": "video"}


def test_scan_runs_the_real_pipeline_in_demo_mode(monkeypatch):
    with_llm(monkeypatch, HeuristicMockLLM(), demo=True)
    msgs = [{"sender": "Officer", "text": "Transfer your savings to a safe account 123-456-789 now. Do not tell anyone."}]
    with serve(load("scan").handler) as u:
        code, body, _ = call(u, {"messages": msgs})
    assert code == 200 and body["verdict"] in ("Likely scam", "Suspicious", "Can't tell") and body["demo"] is True


# ---------------------------------------------------------------- hardening
def test_bad_input_is_rejected_not_crashed(monkeypatch):
    with_llm(monkeypatch, FakeLLM())
    with serve(load("chat").handler) as u:
        assert call(u, raw=b"not json {")[0] == 400
        assert call(u, raw=b"[1,2,3]")[0] == 400
        try:                                   # an oversized body is refused unread; some OSes surface that as a reset
            assert call(u, raw=b"x" * 70_000)[0] == 413
        except ConnectionError:
            pass


def test_per_ip_rate_limit():
    handler = _lib.make_handler(post=lambda d: {"ok": True}, rate=2)
    with serve(handler) as u:
        codes = [call(u, {"a": 1})[0] for _ in range(4)]
    assert codes == [200, 200, 429, 429]


def test_function_failures_return_a_fallback_flag_not_a_stack_trace():
    def boom(data):
        raise RuntimeError("secret internal detail")

    with serve(_lib.make_handler(post=boom)) as u:
        code, body, _ = call(u, {"a": 1})
    assert code == 500 and body == {"error": "RuntimeError", "fallback": True}


# ---------------------------------------------------------------- deployment config and secrets
def test_vercel_config_is_valid_and_serves_the_game_at_root():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["outputDirectory"] == "public" and "cp -r game public" in cfg["buildCommand"]
    assert {"source": "/", "destination": "/game/index.html"} in cfg["rewrites"]
    inc = cfg["functions"]["api/*.py"]["includeFiles"]
    for needed in ("game/personas.json", "knowledge/**", "pipeline/**", "llm/**", "sim/gamechat.py", "sim/gameapi.py", "config.py", "strings.py"):
        assert needed in inc, needed
    assert (ROOT / "game" / "personas.json").exists()


def test_runtime_requirements_are_lean_and_env_is_never_shipped():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "telegram" not in req and "pillow" not in req and "pydantic" in req and "httpx" in req
    ignore = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert ".env" in ignore.split() and ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_no_api_keys_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split()
    rx = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{30,}|\d{9,10}:[A-Za-z0-9_-]{35}")
    leaks = [f for f in files if (ROOT / f).is_file() and f.endswith((".py", ".js", ".json", ".md", ".yaml", ".yml", ".txt", ".html", ".example"))
             and rx.search((ROOT / f).read_text(encoding="utf-8", errors="ignore"))]
    assert not leaks, leaks


def test_the_telegram_simulator_is_not_part_of_the_vercel_deployment():
    names = {p.stem for p in API.glob("*.py") if not p.name.startswith("_")}
    assert names == {"info", "chat", "probe", "scan"}
