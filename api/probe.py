import os

import _lib


async def _probe(data: dict) -> dict:
    from sim import gameapi
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.probe(llm, str(data.get("text", "")), list(data.get("intents", [])), demo)


handler = _lib.make_handler(post=_probe, rate=int(os.getenv("GAME_RATE_CHAT", "90")))
