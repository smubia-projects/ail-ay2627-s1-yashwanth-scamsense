"""Offline stand-ins for the LLM.

* ScriptedLLM    - returns canned JSON; used by unit tests to exercise failure handling.
* HeuristicMockLLM - a keyword/rule-based imitation of the two pipeline prompts so the whole bot can be run and
  demoed WITHOUT an API key. It is NOT an AI model: results from it must never be reported as LLM results.
  Every entry point that can use it prints/sends a visible "DEMO MODE" banner.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from llm.base import LLMClient, LLMError
from pipeline.rules import check_text
from pipeline.schemas import Message, Severity

_MSG = re.compile(r'<msg_(\w+) idx="(\d+)" sender="(.*?)">\n(.*?)\n</msg_\1>', re.S)


class ScriptedLLM(LLMClient):
    """`script` is a list of str | Exception | callable(system,user)->str, consumed in order (last repeats)."""
    name = "scripted"

    def __init__(self, script: list, guard_score: float | None = None) -> None:
        self.script, self.calls, self.guard_score = list(script), 0, guard_score
        self.seen_prompts: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1800) -> str:
        self.seen_prompts.append((system, user))
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item(system, user) if callable(item) else item

    async def classify_injection(self, text: str) -> float | None:
        return self.guard_score


class HeuristicMockLLM(LLMClient):
    name = "heuristic-mock"
    DEMO_BANNER = "DEMO MODE: no LLM key configured - using an offline keyword stand-in, not a real AI model."

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1800) -> str:
        if "TASK=EXTRACT" in system:
            return json.dumps(self._extract(user))
        if "TASK=REASON" in system:
            return json.dumps(self._reason(user))
        # baseline-style single call
        msgs = [Message(idx=i, sender="x", text=m[3]) for i, m in enumerate(_MSG.findall(user))] or \
               [Message(idx=0, sender="x", text=user)]
        hits = [h for m in msgs for h in check_text(m)]
        v = ("Likely scam" if any(h.severity == Severity.HIGH for h in hits)
             else "Suspicious" if any(h.severity == Severity.MEDIUM for h in hits) else "Can't tell")
        return json.dumps({"verdict": v, "reason": "Keyword stand-in."})

    async def classify_injection(self, text: str) -> float | None:
        return 0.0

    # ---------------------------------------------------------------- extraction
    def _extract(self, user: str) -> dict:
        rows = _MSG.findall(user)
        out = []
        seg = "unlabeled" in user.lower()[:60]
        for _n, idx, sender, text in rows:
            hits = check_text(Message(idx=int(idx), sender=sender, text=text))
            ids = {h.rule_id for h in hits}
            tactics = []
            for rid, tac in [("urgency", "urgency"), ("authority_claim", "authority"), ("authority_threat", "fear"),
                             ("prize_reward", "reward"), ("isolation", "isolation"), ("channel_switch", "channel_switch"),
                             ("remote_access_app", "app_install"), ("app_install", "app_install"),
                             ("credential_request", "credential_request")]:
                if rid in ids:
                    tactics.append(tac)
            if ids & {"gift_card_request", "crypto_request", "personal_transfer", "upfront_fee", "safe_account"}:
                tactics.append("payment_request")
            if "authority_threat" in ids and "authority" not in tactics and "authority_claim" in ids:
                tactics.append("authority")
            pm = ("gift_card" if "gift_card_request" in ids else "crypto" if "crypto_request" in ids
                  else "bank_transfer" if ids & {"personal_transfer", "safe_account"} else "other" if "upfront_fee" in ids else "none")
            ident = re.search(r"(?i)(?:i am|i'm|this is|calling from|we are|from)\s+((?:the\s+)?[A-Z][\w .&'-]{2,38}?)(?:[.,\n]| and | at | from |$)", text)
            order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
            top = sorted(hits, key=lambda h: order[h.severity])
            quote = None
            for h in top:
                if h.rule_id in ("urgency", "channel_switch") and len(top) > 1:
                    continue
                if h.evidence and h.evidence.lower() in text.lower():
                    quote = h.evidence
                    break
            out.append({"idx": int(idx), "claimed_identity": ident.group(1).strip() if ident else None,
                        "tactics": tactics, "links": re.findall(r"https?://\S+|\b[\w-]+\.(?:com|sg|xyz|top|net|org)\S*", text)[:3],
                        "payment_method": pm, "quote": quote})
        res = {"input_kind": "conversation", "speakers_inferred": False, "messages": out}
        if seg and rows:
            res["speakers_inferred"] = True
            for o, row in zip(res["messages"], rows):
                o["sender"], o["text"] = "Speaker A", row[3]
        return res

    # ---------------------------------------------------------------- reasoning
    def _reason(self, user: str) -> dict:
        def block(tag: str):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", user, re.S)
            return json.loads(m.group(1)) if m else []

        msgs = {int(i): (s, tx) for _n, i, s, tx in _MSG.findall(user)}
        ann, hits, cands = block("annotations"), block("code_check_hits"), block("candidate_typologies")
        sev = {h["severity"] for h in hits}
        verdict, conf = (("Likely scam", 0.8) if "high" in sev else ("Suspicious", 0.6) if "medium" in sev
                         else ("Suspicious", 0.45) if len(hits) >= 3 else ("Can't tell", 0.5))
        tac_by_idx = {a["idx"]: set(a["tactics"]) for a in ann}

        def where(*tacs):
            return [i for i, t_ in tac_by_idx.items() if t_ & set(tacs)]

        stage_map = {
            "first_contact": ([0] if msgs else [], 0.5),
            "claimed_authority": (where("authority") or [a["idx"] for a in ann if a.get("claimed_identity")], 0.6),
            "urgency": (where("urgency", "fear"), 0.6),
            "isolation": (where("isolation"), 0.6),
            "channel_switch": (where("channel_switch"), 0.55),
            "request": (where("payment_request", "credential_request", "app_install"), 0.7),
        }
        stages = [{"stage": k, "present": bool(v[0]), "message_idxs": v[0][:6], "confidence": v[1] if v[0] else 0.0,
                   "note": ""} for k, v in stage_map.items()]
        evidence = [{"message_idx": a["idx"], "quote": a["quote"], "why": "Matches a known scam tactic."}
                    for a in ann if a.get("quote")][:5]
        reason = {"Likely scam": "This conversation uses several well-known scam tactics, including a request that real organisations do not make.",
                  "Suspicious": "There are some warning signs in this conversation, so please verify before acting.",
                  "Can't tell": "I did not find clear scam signs, but I cannot guarantee anything either way."}[verdict]
        return {"verdict": verdict, "confidence": conf, "reason": reason, "stages": stages, "cross_party": [],
                "evidence": evidence, "typology_id": cands[0]["id"] if cands and hits else None}
