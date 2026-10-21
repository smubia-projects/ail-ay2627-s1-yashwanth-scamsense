"""ScamSense web API (FastAPI, deployed on Cloud Run). API-only: the game itself is a static site on Vercel.

Routes (all stateless: the browser sends the conversation each time; nothing stores or logs player text):
    GET  /api/health  liveness probe
    GET  /api/info    {"demo": bool}  (demo = no LLM key configured)
    POST /api/chat    one in-character reply for the game           (rate-limited: bucket "chat")
    POST /api/probe   classify what the player typed into an intent  (rate-limited: bucket "probe")
    POST /api/scan    run the real ScamSense pipeline over a storyline (rate-limited: bucket "scan")

Run locally:  uvicorn main:app --reload --port 8080
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from config import get_settings  # loads .env before anything else reads the environment
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rate_limit import check_rate_limit

MAX_BODY = 64_000
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

_PERSONAS: dict | None = None


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


app = FastAPI(title="ScamSense API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


@asynccontextmanager
async def llm_client():
    """Yield (llm, demo). A fresh client per request: no state is shared between requests."""
    from llm.mock import HeuristicMockLLM

    s = get_settings()
    if s.llm_api_key:
        from llm.openrouter_client import OpenRouterClient
        c = OpenRouterClient(s)
        try:
            yield c, False
        finally:
            await c.aclose()
    else:
        yield HeuristicMockLLM(), True


def _personas() -> dict:
    global _PERSONAS
    if _PERSONAS is None:
        from sim import gamechat
        _PERSONAS = gamechat.load_personas()
    return _PERSONAS


async def _read_json(request: Request) -> dict | JSONResponse:
    try:
        declared = int(request.headers.get("content-length", 0))
    except ValueError:
        return JSONResponse({"error": "bad_length"}, 400)
    if declared > MAX_BODY:
        return JSONResponse({"error": "too_large"}, 413)
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse({"error": "too_large"}, 413)
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        return JSONResponse({"error": "bad_json"}, 400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "bad_json"}, 400)
    return data


async def _llm_route(request: Request, bucket: str, fn):
    """Shared POST flow: validate body -> rate limit (LLM routes only) -> handler. Failures return a fallback flag
    so the game switches to its authored scripted replies instead of breaking."""
    data = await _read_json(request)
    if isinstance(data, JSONResponse):
        return data
    await run_in_threadpool(check_rate_limit, request, bucket)  # raises 429 / 503 (HTTPException)
    try:
        async with llm_client() as (llm, demo):
            return await fn(llm, demo, data)
    except Exception as e:  # noqa: BLE001 - never leak internals; the game falls back on any failure
        return JSONResponse({"error": type(e).__name__, "fallback": True}, 500)


# ---------------------------------------------------------------- handlers (logic lives in sim/gameapi.py)
async def _chat(llm, demo: bool, data: dict) -> dict:
    from sim import gameapi
    return await gameapi.game_chat(llm, _personas(), data, demo)


async def _probe(llm, demo: bool, data: dict) -> dict:
    from sim import gameapi
    return await gameapi.probe(llm, str(data.get("text", "")), list(data.get("intents", []) or []), demo)


async def _scan(llm, demo: bool, data: dict) -> dict:
    from sim import gameapi
    return await gameapi.scan_storyline(llm, get_settings(), list(data.get("messages", []) or []), demo)


# ---------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/info")
def info() -> dict:
    return {"demo": not get_settings().llm_api_key}


@app.post("/api/chat")
async def chat(request: Request):
    return await _llm_route(request, "chat", _chat)


@app.post("/api/probe")
async def probe(request: Request):
    return await _llm_route(request, "probe", _probe)


@app.post("/api/scan")
async def scan(request: Request):
    return await _llm_route(request, "scan", _scan)
