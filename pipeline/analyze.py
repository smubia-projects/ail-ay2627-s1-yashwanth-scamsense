"""End-to-end orchestration:

 abuse gate -> redact -> [rules | prompt-guard | LLM extraction] -> retrieval -> LLM stage reasoning
 -> grounding -> calibration -> sanitised Report

Privacy: nothing here logs or persists message text. Only redacted text is passed to the LLM.
Failure: any LLM error after one retry degrades to "Can't tell" + note. This function does not raise.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from config import Settings, get_settings
from llm.base import LLMClient, LLMError
from pipeline import extract as extract_mod
from pipeline import guard, retrieve, stages, verdict
from pipeline.redact import Redactor
from pipeline.rules import run_rules
from pipeline.schemas import InputKind, Message, Report, Verdict
from strings import t

log = logging.getLogger("scamsense.pipeline")
STAGE_TIMEOUT_S = 40  # hard cap per LLM stage (covers rate-limit back-off); on timeout we degrade to Can't tell


def _pseudonyms(messages: list[Message]) -> dict[str, str]:
    """Real sender label -> neutral label sent to the LLM (labels can contain real names)."""
    mapping: dict[str, str] = {}
    for m in messages:
        if m.sender not in mapping:
            mapping[m.sender] = "Unknown sender" if m.sender in ("Unknown", "") else f"Sender {chr(65 + len(mapping) % 26)}"
    return mapping


def _restore(text: str, back: dict[str, str]) -> str:
    for pseudo, real in back.items():
        text = re.sub(rf"\b{re.escape(pseudo)}\b", real, text)
    return text


def redact_messages(messages: list[Message]) -> tuple[list[Message], dict[str, int]]:
    r = Redactor()
    out = [m.model_copy(update={"text": r.redact(m.text)}) for m in messages]
    return out, dict(r.counts)


async def analyze(messages: list[Message], llm: LLMClient | None, *, speakers_inferred: bool = False,
                  settings: Settings | None = None, use_guard: bool | None = None) -> Report:
    s = settings or get_settings()
    t0 = time.perf_counter()
    notes: list[str] = []

    raw_joined = "\n".join(m.text for m in messages)
    if not raw_joined.strip():
        return Report(verdict=Verdict.CANT_TELL, confidence=0.0, reason=t("limit.empty"), refused=True)

    # 1. abuse gate (deterministic, before anything else)
    if guard.is_abuse_request(raw_joined):
        return Report(verdict=Verdict.CANT_TELL, confidence=0.0, reason=t("refuse.generate"), refused=True,
                      latency_s=time.perf_counter() - t0)

    # 2. size limits
    if len(raw_joined) > s.max_input_chars:
        messages = _truncate(messages, s.max_input_chars)
        notes.append(t("note.truncated"))
    messages = messages[: s.max_messages]
    messages = [m.model_copy(update={"idx": i}) for i, m in enumerate(messages)]

    # 3. redaction BEFORE any LLM call; sender labels are pseudonymised for the LLM only
    red_msgs, counts = redact_messages(messages)
    mapping = _pseudonyms(red_msgs)
    back = {v: k for k, v in mapping.items() if k not in ("Unknown", "")}
    llm_msgs = [m.model_copy(update={"sender": mapping[m.sender]}) for m in red_msgs]

    # 4. deterministic rules on the redacted text
    hits = run_rules(red_msgs)
    injection = any(h.rule_id == "ai_instruction_injection" for h in hits)

    if llm is None:
        return _degraded(red_msgs, hits, counts, notes, t0, speakers_inferred, injection)

    segment = len(llm_msgs) == 1 and llm_msgs[0].inferred_sender
    do_guard = s.use_prompt_guard if use_guard is None else use_guard

    # 5. LLM extraction (+ prompt guard in parallel)
    try:
        async def _guard():
            if not do_guard:
                return guard.GuardResult(False, None, "none")
            return await guard.prompt_guard("\n".join(m.text for m in llm_msgs), llm, s)

        ex, gres = await asyncio.wait_for(
            asyncio.gather(extract_mod.extract(llm_msgs, llm, segment=segment), _guard()), STAGE_TIMEOUT_S)
    except (LLMError, Exception) as e:  # noqa: BLE001 - must never crash
        log.warning("extraction failed: %s", type(e).__name__)
        return _degraded(red_msgs, hits, counts, notes, t0, speakers_inferred, injection)

    if gres.flagged:
        injection = True
    if ex.input_kind == InputKind.GENERATE_SCAM_REQUEST:
        return Report(verdict=Verdict.CANT_TELL, confidence=0.0, reason=t("refuse.generate"), refused=True,
                      latency_s=time.perf_counter() - t0)

    llm_msgs, annotations, anote = extract_mod.align_annotations(llm_msgs, ex)
    speakers_inferred = speakers_inferred or ex.speakers_inferred or any(m.inferred_sender for m in llm_msgs)
    if len(llm_msgs) != len(red_msgs):  # LLM segmented an unlabeled block: re-run rules + redaction view on segments
        red_msgs = llm_msgs
        hits = run_rules(red_msgs)
        injection = injection or any(h.rule_id == "ai_instruction_injection" for h in hits)
        back = {}

    # 6. retrieval -> 7. reasoning
    ranked = retrieve.retrieve(llm_msgs, annotations, hits, k=3)
    candidates = [t_ for t_, _ in ranked]
    try:
        reasoning = await asyncio.wait_for(stages.reason(llm_msgs, annotations, hits, candidates, llm), STAGE_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        log.warning("reasoning failed: %s", type(e).__name__)
        return _degraded(red_msgs, hits, counts, notes, t0, speakers_inferred, injection, annotations=annotations,
                         typology=candidates[0] if candidates else None)

    # 8. grounding + calibration + sanitising
    v, conf, vnotes, vlog = verdict.calibrate(reasoning, hits, injection=injection, inferred_speakers=speakers_inferred)
    notes.extend(vnotes)

    reason, replaced = verdict.sanitise_text(_restore(reasoning.reason, back), t(f"fallback_reason.{v.value}"))
    if replaced:
        notes.append(t("note.reassurance_removed"))
        vlog.append("reassurance wording replaced")
    if v == Verdict.CANT_TELL and not reason.strip():
        reason = t("fallback_reason.Can't tell")

    evidence = verdict.ground_evidence(reasoning.evidence, llm_msgs)
    if len(evidence) < len(reasoning.evidence):
        vlog.append(f"dropped {len(reasoning.evidence) - len(evidence)} ungrounded evidence quote(s)")
    evidence = verdict.fallback_evidence(annotations, hits, llm_msgs, evidence)
    for e in evidence:
        e.why = _restore(e.why, back)
    cross = verdict.merge_cross_party(reasoning.cross_party, verdict.derive_cross_party(llm_msgs, annotations, hits))
    for c in cross:
        c.description = _restore(c.description, back)
    for st in reasoning.stages:
        st.note = _restore(sanitise_note(st.note), back)

    # typology: LLM's choice if it is a real KB entry, else top retrieval hit (only if it scored)
    typs = retrieve.load_typologies()
    typology = typs.get(reasoning.typology_id or "") or (candidates[0] if candidates and v != Verdict.CANT_TELL else None)
    if v == Verdict.CANT_TELL and not hits:
        typology = typs.get(reasoning.typology_id or "") if reasoning.typology_id else None

    # restore real sender labels for display
    display = [m.model_copy(update={"sender": back.get(m.sender, m.sender)}) for m in llm_msgs]

    return Report(
        verdict=v, confidence=conf, reason=reason, messages=display, annotations=annotations, rule_hits=hits,
        stages=reasoning.stages, cross_party=cross, evidence=evidence, typology=typology, notes=notes,
        speakers_inferred=speakers_inferred, injection_detected=injection, redaction_counts=counts,
        latency_s=round(time.perf_counter() - t0, 2), calibration=vlog,
    )


def sanitise_note(text: str) -> str:
    out, _ = verdict.sanitise_text(text, "")
    return out


def _truncate(messages: list[Message], limit: int) -> list[Message]:
    out, used = [], 0
    for m in messages:
        if used + len(m.text) > limit:
            room = limit - used
            if room > 80:
                out.append(m.model_copy(update={"text": m.text[:room]}))
            break
        out.append(m)
        used += len(m.text)
    return out or [messages[0].model_copy(update={"text": messages[0].text[:limit]})]


def _degraded(msgs, hits, counts, notes, t0, inferred, injection, *, annotations=None, typology=None) -> Report:
    v, conf, vnotes, vlog = verdict.calibrate(None, hits, injection=injection, inferred_speakers=inferred)
    return Report(
        verdict=v, confidence=conf, reason=t("note.degraded"), messages=msgs, annotations=annotations or [], rule_hits=hits,
        typology=typology, notes=notes + vnotes, degraded=True, speakers_inferred=inferred, injection_detected=injection,
        redaction_counts=counts, latency_s=round(time.perf_counter() - t0, 2), calibration=vlog,
    )
