"""Verdict calibration, grounding and the never-safe output guard.

Calibration policy (see DECISIONS.md):
  * ordering: Likely scam > Suspicious > Can't tell. "Can't tell" is not reassurance.
  * LLM low confidence            -> step DOWN the ladder (never to "safe": there is no such rung).
  * LLM "Likely scam" but code found little -> Suspicious (model is more alarmed than the evidence).
  * LLM "Can't tell" but code found medium/high -> Suspicious (never reassure on disagreement).
  * injection attempt detected    -> floor of Suspicious.
  * LLM failed                    -> Can't tell + note (never invent a verdict).
"""
from __future__ import annotations

import re

from pipeline.rules import rule_level
from pipeline.schemas import (CrossPartyKind, CrossPartySignal, EvidenceItem, Message, MessageAnnotation, ReasoningResult,
                              RuleHit, Verdict)
from strings import t

# Free text that sounds like a guarantee. Deliberately narrow: "move money to a safe account" must pass.
_REASSURANCE = re.compile(
    r"(?i)\b(?:is|are|was|were|seems?|appears?|looks?|be|being|totally|completely|probably|likely|certainly|definitely)\s+"
    r"(?:\w+\s+)?(?:safe|legit(?:imate)?|genuine|authentic|trustworthy|harmless|not a scam|no scam)\b"
    r"|\bnot (?:a )?(?:scam|fraud|phishing)\b|\bnothing (?:to worry|suspicious|wrong)\b|\bno (?:risk|danger|cause for concern|reason to worry)\b"
    r"|\bsafe to (?:click|proceed|ignore|trust|reply|respond|open|use|pay)\b|\byou(?:'re| are) (?:safe|fine|okay)\b|\bgenuine (?:message|bank|notice)\b"
)
_NORM = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()  # noqa: E731


def sounds_reassuring(text: str) -> bool:
    return bool(_REASSURANCE.search(text or ""))


def sanitise_text(text: str, fallback: str) -> tuple[str, bool]:
    """Replace free text that reads like a guarantee. Returns (text, was_replaced)."""
    if sounds_reassuring(text):
        return fallback, True
    return text, False


def ground_evidence(evidence: list[EvidenceItem], messages: list[Message]) -> list[EvidenceItem]:
    """Keep only quotes that literally appear in the cited message (drops hallucinated evidence)."""
    out: list[EvidenceItem] = []
    by_idx = {m.idx: _NORM(m.text) for m in messages}
    for e in evidence:
        q = _NORM(e.quote).strip(" .…\"'")
        if q and e.message_idx in by_idx and q in by_idx[e.message_idx]:
            why, _ = sanitise_text(e.why, "")
            out.append(e.model_copy(update={"why": why}))
    return out[:6]


def derive_cross_party(messages: list[Message], annotations: list[MessageAnnotation], hits: list[RuleHit]) -> list[CrossPartySignal]:
    """Deterministic cross-party signals (a backstop that does not depend on the LLM)."""
    sig: list[CrossPartySignal] = []
    sender_of = {m.idx: m.sender for m in messages}
    if len({m.sender for m in messages}) < 2:
        return sig
    # repeated tactic: same tactic by >= 2 different senders
    by_tactic: dict[str, dict[str, list[int]]] = {}
    for a in annotations:
        s = sender_of.get(a.idx)
        for tac in a.tactics:
            by_tactic.setdefault(tac.value, {}).setdefault(s, []).append(a.idx)
    for tac, per_sender in by_tactic.items():
        if len(per_sender) >= 2:
            idxs = sorted(i for v in per_sender.values() for i in v)[:6]
            sig.append(CrossPartySignal(kind=CrossPartyKind.REPEATED_TACTIC, message_idxs=idxs,
                                        description=f"{len(per_sender)} different senders each use '{tac.replace('_', ' ')}'"))
            break
    # handoff: a 'handoff' rule hit followed by a different sender claiming an identity
    for h in hits:
        if h.rule_id == "handoff" and h.message_idx is not None:
            later = [a for a in annotations if a.idx > h.message_idx and a.claimed_identity
                     and sender_of.get(a.idx) != sender_of.get(h.message_idx)]
            if later:
                sig.append(CrossPartySignal(kind=CrossPartyKind.HANDOFF, message_idxs=[h.message_idx, later[0].idx],
                                            description=f"{sender_of[h.message_idx]} passes you to {sender_of[later[0].idx]} ({later[0].claimed_identity})"))
                break
    return sig


def merge_cross_party(llm_sigs: list[CrossPartySignal], derived: list[CrossPartySignal]) -> list[CrossPartySignal]:
    have = {s.kind for s in llm_sigs}
    return llm_sigs + [d for d in derived if d.kind not in have]


def calibrate(reasoning: ReasoningResult | None, hits: list[RuleHit], *, injection: bool,
              inferred_speakers: bool) -> tuple[Verdict, float, list[str], list[str]]:
    """Return (verdict, confidence, user_notes, calibration_log)."""
    notes: list[str] = []
    log: list[str] = []
    non_inj = [h for h in hits if h.rule_id != "ai_instruction_injection"]
    rl = rule_level(non_inj)

    if reasoning is None:
        return Verdict.CANT_TELL, 0.0, [t("note.degraded")], ["llm_unavailable -> Can't tell"]

    v, c = reasoning.verdict, reasoning.confidence
    start = v

    if inferred_speakers:
        c = max(0.0, c - 0.1)
        notes.append(t("note.inferred"))
        log.append("speakers_inferred: -0.10 confidence")

    # --- low confidence: step down, never to reassurance
    if c < 0.55 and v == Verdict.LIKELY_SCAM:
        v = Verdict.SUSPICIOUS
        log.append(f"low confidence ({c:.2f}): Likely scam -> Suspicious")
    if c < 0.30 and v == Verdict.SUSPICIOUS and rl in ("none", "low"):
        v = Verdict.CANT_TELL
        log.append(f"very low confidence ({c:.2f}) and weak rules: Suspicious -> Can't tell")

    # --- disagreement between model and rules
    if v == Verdict.LIKELY_SCAM and rl in ("none", "low"):
        v = Verdict.SUSPICIOUS
        log.append(f"model says Likely scam but code checks are {rl}: -> Suspicious")
    if v == Verdict.CANT_TELL and rl in ("medium", "high"):
        v = Verdict.SUSPICIOUS
        log.append(f"model says Can't tell but code checks are {rl}: -> Suspicious")
    if v == Verdict.SUSPICIOUS and rl == "high" and c >= 0.8 and reasoning.verdict == Verdict.SUSPICIOUS:
        log.append("rules high + model Suspicious: kept Suspicious (disagreement is not resolved upward)")

    # --- injection attempt: floor
    if injection and v == Verdict.CANT_TELL:
        v = Verdict.SUSPICIOUS
        log.append("prompt-injection attempt: floor Suspicious")
    if injection:
        notes.append(t("note.injection"))

    if v.rank > start.rank:
        notes.append(t("note.calibrated_up"))
    elif v.rank < start.rank:
        notes.append(t("note.calibrated_down"))

    if v == Verdict.CANT_TELL and not non_inj:
        notes.append(t("note.no_signs"))

    return v, round(c, 2), notes, log


def fallback_evidence(annotations: list[MessageAnnotation], hits: list[RuleHit], messages: list[Message],
                      have: list[EvidenceItem], limit: int = 5) -> list[EvidenceItem]:
    """Top up evidence with verbatim, grounded quotes from extraction + deterministic hits (never invented)."""
    out = list(have)
    seen = {(e.message_idx, _NORM(e.quote)) for e in out}
    cands: list[EvidenceItem] = []
    order = {"high": 0, "medium": 1, "low": 2}
    for h in sorted(hits, key=lambda h: order[h.severity.value]):
        if h.message_idx is not None and h.evidence and h.rule_id != "ai_instruction_injection" and h.severity.value != "low":
            cands.append(EvidenceItem(message_idx=h.message_idx, quote=h.evidence, why=h.description))
    for a in annotations:
        if a.quote:
            why = ("Uses: " + ", ".join(t_.value.replace("_", " ") for t_ in a.tactics)) if a.tactics else ""
            cands.append(EvidenceItem(message_idx=a.idx, quote=a.quote, why=why))
    for c in ground_evidence(cands, messages):
        key = (c.message_idx, _NORM(c.quote))
        if key not in seen and len(out) < limit:
            seen.add(key)
            out.append(c)
    return sorted(out, key=lambda e: e.message_idx)
