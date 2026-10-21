"""Input-safety gates: prompt-injection detection and the abuse (scam-generation) refusal.

Layers (each independently measured in the eval):
  1. regex rule `ai_instruction_injection` (pipeline/rules.py)         - free, deterministic
  2. Prompt Guard classifier (optional; off by default, needs a client that implements classify_injection)
  3. prompt design: random delimiters + "untrusted data" clauses + JSON-only output
  4. schema validation: verdict enum has no "safe"; reassurance sanitiser on free text
An injection attempt can only ever RAISE suspicion: it is treated as a red flag in itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import Settings, get_settings
from llm.base import LLMClient

_WRITE = r"(?:write|draft|compose|create|generate|make|craft|produce|prepare|come up with|give me)"
_SCAMWORD = r"(?:scam|phishing|fraud(?:ulent)?|fake (?:bank|police|government|parcel|delivery|job)|spam|con\b)"
_ABUSE_PATTERNS = [
    re.compile(rf"(?i)\b{_WRITE}\b[^.\n]{{0,60}}\b{_SCAMWORD}\b[^.\n]{{0,40}}\b(?:message|sms|text|email|e-mail|script|letter|whatsapp|call|template|post)"),
    re.compile(rf"(?i)\b{_WRITE}\b[^.\n]{{0,40}}\b(?:message|sms|text|email|script)\b[^.\n]{{0,60}}\b(?:pretend(?:ing)?|pose|posing|impersonat\w+|as if (?:i am|from)|from (?:dbs|ocbc|uob|police|the bank|mas|singpost|ica))"),
    re.compile(r"(?i)\b(?:improve|polish|rewrite|reword|rephrase|enhance|optimi[sz]e|refine)\b[^.\n]{0,50}\b(?:scam|phishing|this message)\b"),
    re.compile(r"(?i)\bmake\b[^.\n]{0,40}\b(?:more )?(?:convincing|believable|persuasive|realistic|trustworthy|legit)\b"),
    re.compile(rf"(?i)\btranslate\b[^.\n]{{0,60}}\b{_SCAMWORD}\b|\b{_SCAMWORD}\b[^.\n]{{0,60}}\btranslat\w+"),
    re.compile(r"(?i)\bhow (?:do|can|could|to|should) (?:i|we|one) (?:\w+ )?(?:scam|defraud|cheat|trick|phish|con)\b[^.\n]{0,40}(?:people|victims|someone|elderly|auntie|uncle|seniors|them)"),
    re.compile(r"(?i)\b(?:help me|teach me|show me)\b[^.\n]{0,20}\b(?:scam|phish|defraud)\b"),
    re.compile(r"(?i)\bscript for (?:a |my )?(?:scam|phishing|vishing|scam call)\b"),
]


def is_abuse_request(text: str) -> bool:
    return any(p.search(text) for p in _ABUSE_PATTERNS)


@dataclass
class GuardResult:
    flagged: bool
    score: float | None
    via: str  # "prompt_guard" | "none"


async def prompt_guard(text: str, llm: LLMClient, settings: Settings | None = None) -> GuardResult:
    s = settings or get_settings()
    if not s.use_prompt_guard:
        return GuardResult(False, None, "none")
    score = await llm.classify_injection(text)
    if score is None:
        return GuardResult(False, None, "none")
    return GuardResult(score >= s.prompt_guard_threshold, score, "prompt_guard")
