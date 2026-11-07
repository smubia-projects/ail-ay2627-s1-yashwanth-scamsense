"""The FastAPI web service (main.py), tested offline against a fake LLM."""
import contextlib

from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from llm.mock import HeuristicMockLLM
from tests.test_game_chat import FakeLLM

client = TestClient(main.app)


def with_llm(monkeypatch, llm, demo=False):
    @contextlib.asynccontextmanager
    async def fake():
        yield llm, demo
    monkeypatch.setattr(main, "llm_client", fake)


# ---------------------------------------------------------------- routes
def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_info_and_security_headers():
    r = client.get("/api/info")
    assert r.status_code == 200 and isinstance(r.json()["demo"], bool)
    assert r.headers.get("X-Content-Type-Options") == "nosniff" and r.headers.get("Cache-Control") == "no-store"
    assert client.post("/api/info", json={"x": 1}).status_code == 405


def test_api_only_no_frontend_served():
    assert client.get("/").status_code == 404
    assert client.get("/game/index.html").status_code == 404


def test_chat_returns_an_in_character_reply(monkeypatch):
    with_llm(monkeypatch, FakeLLM("callback", "Please use our direct line."))
    r = client.post("/api/chat", json={"case": 6, "chat": "wong", "history": [], "text": "I'll call MAS myself",
                                       "counts": {"callback": 1}, "factCounts": {}})
    assert r.status_code == 200 and r.json()["reply"] == "Please use our direct line." and r.json()["signal"]["kind"] == "tell"


def test_chat_without_a_key_falls_back_to_scripted_replies(monkeypatch):
    with_llm(monkeypatch, HeuristicMockLLM(), demo=True)
    assert client.post("/api/chat", json={"case": 6, "chat": "wong", "text": "hi"}).json() == {"fallback": True}


def test_probe_classifies(monkeypatch):
    with_llm(monkeypatch, FakeLLM("video"))
    r = client.post("/api/probe", json={"text": "can we video call", "intents": [{"id": "video", "desc": "asks for a video call"}]})
    assert r.status_code == 200 and r.json() == {"intent": "video"}


def test_scan_runs_the_real_pipeline_in_demo_mode(monkeypatch):
    with_llm(monkeypatch, HeuristicMockLLM(), demo=True)
    msgs = [{"sender": "Officer", "text": "Transfer your savings to a safe account 123-456-789 now. Do not tell anyone."}]
    r = client.post("/api/scan", json={"messages": msgs})
    assert r.status_code == 200 and r.json()["verdict"] in ("Likely scam", "Suspicious", "Can't tell") and r.json()["demo"] is True


# ---------------------------------------------------------------- hardening
def test_bad_input_is_rejected_not_crashed(monkeypatch):
    with_llm(monkeypatch, FakeLLM())
    hdr = {"Content-Type": "application/json"}
    assert client.post("/api/chat", content=b"not json {", headers=hdr).status_code == 400
    assert client.post("/api/chat", content=b"[1,2,3]", headers=hdr).status_code == 400
    assert client.post("/api/chat", content=b"x" * 70_000, headers=hdr).status_code == 413


def test_rate_limit_429_and_pause_503_come_from_the_shared_engine(monkeypatch):
    seen = []

    def limited(request, bucket):
        seen.append(bucket)
        raise HTTPException(429, detail={"message": "Rate limit exceeded.", "queries_used": 5})

    monkeypatch.setattr(main, "check_rate_limit", limited)
    for path, bucket in (("/api/chat", "chat"), ("/api/probe", "probe"), ("/api/scan", "scan")):
        r = client.post(path, json={})
        assert r.status_code == 429 and r.json()["detail"]["queries_used"] == 5
    assert seen == ["chat", "probe", "scan"]

    def paused(request, bucket):
        raise HTTPException(503, detail={"message": "This demo is temporarily paused. Check back soon."})

    monkeypatch.setattr(main, "check_rate_limit", paused)
    r = client.post("/api/scan", json={})
    assert r.status_code == 503 and "paused" in r.json()["detail"]["message"]


def test_non_llm_routes_are_not_rate_limited(monkeypatch):
    def boom(request, bucket):
        raise AssertionError("rate limit must only apply to LLM routes")

    monkeypatch.setattr(main, "check_rate_limit", boom)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/info").status_code == 200


def test_function_failures_return_a_fallback_flag_not_a_stack_trace(monkeypatch):
    @contextlib.asynccontextmanager
    async def broken():
        raise RuntimeError("secret internal detail")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "llm_client", broken)
    r = client.post("/api/chat", json={"case": 6, "chat": "wong", "text": "hi"})
    assert r.status_code == 500 and r.json() == {"error": "RuntimeError", "fallback": True}
