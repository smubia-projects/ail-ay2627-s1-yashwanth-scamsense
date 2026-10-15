"""LLM call #1: structured, schema-validated per-message extraction (and speaker segmentation if unlabeled)."""
from __future__ import annotations

import re

from llm.base import LLMClient
from pipeline import prompts
from pipeline.schemas import ExtractionResult, Message, MessageAnnotation


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


async def extract(messages: list[Message], llm: LLMClient, *, segment: bool) -> ExtractionResult:
    nonce = prompts.new_nonce()
    system = prompts.EXTRACT_SYSTEM + (prompts.EXTRACT_SEGMENT_ADDENDUM if segment else "")
    result = await llm.structured(ExtractionResult, system, prompts.extract_user(messages, nonce, segment))
    return result


def align_annotations(messages: list[Message], ex: ExtractionResult) -> tuple[list[Message], list[MessageAnnotation], list[str]]:
    """Make annotations line up 1:1 with messages and ground every quote in the real text.

    * labelled input: annotations are matched by idx; missing ones become empty annotations.
    * unlabeled input: the LLM's segmentation is accepted only if its text is found verbatim in the input.
    * quotes that are not verbatim substrings are dropped (they could be hallucinated).
    """
    notes: list[str] = []
    if messages and messages[0].inferred_sender and len(messages) == 1:
        original = _norm(messages[0].text)
        segs = [a for a in ex.messages if a.text and a.text.strip()]
        grounded = [a for a in segs if _norm(a.text) in original]
        if segs and len(grounded) / len(segs) >= 0.7 and len(grounded) >= 1:
            new_msgs, anns = [], []
            for i, a in enumerate(grounded[:40]):
                new_msgs.append(Message(idx=i, sender=(a.sender or f"Speaker {chr(65 + min(i, 25))}")[:30], text=a.text.strip(),
                                        inferred_sender=True))
                anns.append(a.model_copy(update={"idx": i}))
            messages, ex_ann = new_msgs, anns
            if len(grounded) < len(segs):
                notes.append("dropped_ungrounded_segments")
        else:
            ex_ann = [a.model_copy(update={"idx": 0}) for a in ex.messages[:1]]
            if segs:
                notes.append("segmentation_rejected")
    else:
        by_idx = {a.idx: a for a in ex.messages}
        ex_ann = [by_idx.get(m.idx, MessageAnnotation(idx=m.idx)) for m in messages]

    out: list[MessageAnnotation] = []
    for m, a in zip(messages, ex_ann, strict=False):
        a = a.model_copy(update={"idx": m.idx})
        if a.quote and _norm(a.quote) not in _norm(m.text):
            a = a.model_copy(update={"quote": None})
            notes.append("dropped_ungrounded_quote")
        out.append(a)
    while len(out) < len(messages):
        out.append(MessageAnnotation(idx=len(out)))
    return messages, out, notes
