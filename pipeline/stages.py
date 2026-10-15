"""LLM call #2: stage detection + cross-party reasoning + proposed verdict, over the extracted structure
and the deterministic rule hits. Output is schema validated and grounded by verdict.py afterwards."""
from __future__ import annotations

from llm.base import LLMClient
from pipeline import prompts
from pipeline.schemas import (STAGE_ORDER, Message, MessageAnnotation, ReasoningResult, RuleHit, StageDetection,
                              Typology)


async def reason(messages: list[Message], annotations: list[MessageAnnotation], hits: list[RuleHit],
                 candidates: list[Typology], llm: LLMClient) -> ReasoningResult:
    nonce = prompts.new_nonce()
    res = await llm.structured(ReasoningResult, prompts.REASON_SYSTEM,
                               prompts.reason_user(messages, annotations, hits, candidates, nonce), max_tokens=2200)
    return normalise_stages(res, len(messages))


def normalise_stages(res: ReasoningResult, n_messages: int) -> ReasoningResult:
    """Exactly one entry per stage, in canonical order; message indices clamped to the real range."""
    by_stage: dict = {}
    for s in res.stages:
        s = s.model_copy(update={"message_idxs": [i for i in s.message_idxs if 0 <= i < n_messages]})
        prev = by_stage.get(s.stage)
        if prev is None or s.confidence > prev.confidence:
            by_stage[s.stage] = s
    stages = [by_stage.get(st, StageDetection(stage=st, present=False, confidence=0.0)) for st in STAGE_ORDER]
    cross = [c.model_copy(update={"message_idxs": [i for i in c.message_idxs if 0 <= i < n_messages]}) for c in res.cross_party]
    ev = [e for e in res.evidence if 0 <= e.message_idx < n_messages]
    return res.model_copy(update={"stages": stages, "cross_party": cross, "evidence": ev})
