"""Retrieval over the scam-typology knowledge base (knowledge/typologies/*.yaml).

BM25 implemented in ~40 lines: no heavy infra, no embeddings service, fully offline and deterministic.
Rule hits and extracted tactics are expanded into hint words so structure (not just wording) drives retrieval.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from pipeline.schemas import MessageAnnotation, Message, RuleHit, Typology

TYPOLOGY_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "typologies"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or to of in on for is are was be you your i we it this that with at by from as not do me my have has will can please".split())

# rule id -> words that pull retrieval toward the typologies where that rule is characteristic
RULE_HINTS: dict[str, str] = {
    "safe_account": "police officer investigation safe account money laundering",
    "authority_threat": "police officer arrest warrant investigation court",
    "authority_claim": "police officer investigation",
    "handoff": "senior officer transfer you investigation",
    "isolation": "confidential do not tell investigation",
    "remote_access_app": "anydesk teamviewer remote install support virus",
    "gift_card_request": "gift card urgent new number tech support",
    "crypto_request": "crypto bitcoin usdt invest wallet",
    "investment_promise": "invest returns profit trading guaranteed",
    "job_task_scam": "job part-time tasks commission top up earn",
    "upfront_fee": "parcel delivery fee customs courier loan processing",
    "prize_reward": "refund prize reward claim",
    "impersonated_relative": "new number mum dad urgent family friend",
    "brand_in_domain": "bank login verify account locked",
    "lookalike_domain": "bank login verify account locked parcel",
    "brand_link_mismatch": "bank login verify account",
    "credential_request": "otp password login verify bank singpass",
    "url_shortener": "link click parcel bank",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


@lru_cache(maxsize=1)
def load_typologies() -> dict[str, Typology]:
    out: dict[str, Typology] = {}
    for p in sorted(TYPOLOGY_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        out[data["id"]] = Typology.model_validate(data)
    return out


class _BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.4, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(len(d) for d in docs.values()) / max(len(docs), 1)
        df: Counter = Counter()
        for d in docs.values():
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = {k: Counter(v) for k, v in docs.items()}

    def score(self, q: list[str], doc_id: str) -> float:
        tf, dl = self.tf[doc_id], len(self.docs[doc_id])
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


@lru_cache(maxsize=1)
def _index() -> _BM25:
    docs = {}
    for tid, t in load_typologies().items():
        # keywords are repeated to weight them above prose
        blob = " ".join([t.name, t.summary, " ".join(t.typical_flow), " ".join(t.red_flags), " ".join(t.keywords) * 2])
        docs[tid] = _tokens(blob)
    return _BM25(docs)


def retrieve(messages: list[Message], annotations: list[MessageAnnotation], hits: list[RuleHit],
             k: int = 3) -> list[tuple[Typology, float]]:
    parts = [m.text for m in messages]
    parts += [a.claimed_identity or "" for a in annotations]
    parts += [t.value.replace("_", " ") for a in annotations for t in a.tactics]
    parts += [RULE_HINTS.get(h.rule_id, "") for h in hits]
    # rule-derived hints are repeated so structured evidence outweighs incidental wording
    parts += [RULE_HINTS.get(h.rule_id, "") for h in hits if h.severity.value != "low"]
    q = _tokens(" ".join(parts))
    if not q:
        return []
    idx, typs = _index(), load_typologies()
    scored = sorted(((idx.score(q, tid), tid) for tid in typs), reverse=True)
    return [(typs[tid], s) for s, tid in scored[:k] if s > 0]
