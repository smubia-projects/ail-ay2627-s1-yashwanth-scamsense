import os

import _lib

_PERSONAS = None


async def _chat(data: dict) -> dict:
    global _PERSONAS
    from sim import gameapi, gamechat
    if _PERSONAS is None:
        _PERSONAS = gamechat.load_personas()
    async with _lib.llm_client() as (llm, demo):
        return await gameapi.game_chat(llm, _PERSONAS, data, demo)


handler = _lib.make_handler(post=_chat, rate=int(os.getenv("GAME_RATE_CHAT", "90")))
