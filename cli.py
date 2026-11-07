"""Analyse a text file (or stdin) end to end:  python cli.py conversation.txt [--mock] [--json]"""
from __future__ import annotations

import argparse
import asyncio
import sys

from bot.render import render_checks, render_evidence, render_summary, to_plain
from config import get_settings
from llm.base import LLMClient
from llm.mock import HeuristicMockLLM
from pipeline.analyze import analyze
from pipeline.parse import parse_conversation


def make_llm(mock: bool) -> tuple[LLMClient, bool]:
    s = get_settings()
    if mock or not s.llm_api_key:
        return HeuristicMockLLM(), True
    from llm.openrouter_client import OpenRouterClient
    return OpenRouterClient(s), False


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="ScamSense CLI")
    ap.add_argument("file", nargs="?", help="text file with the conversation (default: stdin)")
    ap.add_argument("--mock", action="store_true", help="use the offline keyword stand-in instead of a real LLM")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    a = ap.parse_args()

    text = open(a.file, encoding="utf-8").read() if a.file else sys.stdin.read()
    msgs, inferred = parse_conversation(text)
    llm, is_mock = make_llm(a.mock)
    if is_mock:
        print(f"[{HeuristicMockLLM.DEMO_BANNER}]\n", file=sys.stderr)
    r = await analyze(msgs, llm, speakers_inferred=inferred)
    if a.json:
        print(r.model_dump_json(indent=2))
    else:
        print(to_plain(render_summary(r)))
        print("\n" + "-" * 60 + "\n" + to_plain(render_evidence(r)))
        print("\n" + "-" * 60 + "\n" + to_plain(render_checks(r)))
    if hasattr(llm, "aclose"):
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
