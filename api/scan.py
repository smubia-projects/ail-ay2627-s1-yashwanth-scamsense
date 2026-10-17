import os

import _lib


async def _scan(data: dict) -> dict:
    from config import get_settings
    from sim import gameapi
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.scan_storyline(llm, get_settings(), list(data.get("messages", [])), demo)


handler = _lib.make_handler(post=_scan, rate=int(os.getenv("GAME_RATE_SCAN", "10")))
