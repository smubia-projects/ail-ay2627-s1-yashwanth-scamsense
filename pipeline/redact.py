"""PII redaction. Runs BEFORE any LLM call; only redacted text ever leaves the process.

Typed, numbered placeholders keep cross-message structure (same number reused by two senders
-> same placeholder) without leaking the value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NRIC_RE = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.I)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# 13-19 digits, optionally separated by single spaces / dashes
CARD_RE = re.compile(r"(?<![\d])(?:\d[ \-]?){12,18}\d(?![\d])")
# Singapore numbers (6/8/9 + 7 digits, optional +65/65/0065, optional space/dash after 4 digits)
# plus generic international numbers starting with +
SG_PHONE_RE = re.compile(r"(?<![\w.])(?:(?:\+|00)?65[ \-]?)?[689]\d{3}[ \-]?\d{4}(?![\w])")
INTL_PHONE_RE = re.compile(r"(?<![\w])\+(?!65\b)\d{1,3}[ \-]?\(?\d{1,4}\)?(?:[ \-]?\d{2,4}){2,4}(?![\w])")
# OTP / PIN codes mentioned next to a keyword
OTP_RE = re.compile(r"(?i)\b(otp|one[- ]time (?:password|pin)|pin|passcode|verification code|code|tac)\b([^\d\n]{0,20})(\d{4,8})\b")
# Bank-account-like numbers: 9-14 digits, optionally dashed in groups (e.g. 123-456-789-0, 012-34567-8)
ACCOUNT_RE = re.compile(r"(?<![\d])\d{3}[ \-]?\d{3,6}[ \-]?\d{1,6}(?:[ \-]?\d{1,4})?(?![\d])")

URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"')]+")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)


class Redactor:
    """Stateful per-conversation redactor so identical values map to the same placeholder."""

    def __init__(self) -> None:
        self._maps: dict[str, dict[str, str]] = {}
        self.counts: dict[str, int] = {}

    def _ph(self, kind: str, raw: str) -> str:
        key = re.sub(r"[\s\-]", "", raw).lower()
        m = self._maps.setdefault(kind, {})
        if key not in m:
            m[key] = f"[{kind}_{len(m) + 1}]"
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return m[key]

    def redact(self, text: str) -> str:
        # Protect URLs: digits inside URLs (ids, query strings) must not be eaten by number patterns.
        urls: list[str] = []

        def _stash(m: re.Match) -> str:
            urls.append(m.group(0))
            return f"\x00U{len(urls) - 1}\x00"

        text = URL_RE.sub(_stash, text)

        text = EMAIL_RE.sub(lambda m: self._ph("EMAIL", m.group(0)), text)
        text = NRIC_RE.sub(lambda m: self._ph("NRIC", m.group(0).upper()), text)
        text = OTP_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{self._ph('OTP', m.group(3))}", text)

        def _card(m: re.Match) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                return self._ph("CARD", digits)
            return m.group(0)

        text = CARD_RE.sub(_card, text)
        text = SG_PHONE_RE.sub(lambda m: self._ph("PHONE", self._norm_phone(m.group(0))), text)
        text = INTL_PHONE_RE.sub(lambda m: self._ph("PHONE", m.group(0)), text)

        def _acct(m: re.Match) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            if 9 <= len(digits) <= 16:
                return self._ph("ACCOUNT", digits)
            return m.group(0)

        text = ACCOUNT_RE.sub(_acct, text)

        for i, u in enumerate(urls):
            text = text.replace(f"\x00U{i}\x00", u)
        return text

    @staticmethod
    def _norm_phone(raw: str) -> str:
        d = re.sub(r"\D", "", raw)
        return d[-8:] if len(d) >= 8 else d


def redact_text(text: str) -> RedactionResult:
    r = Redactor()
    out = r.redact(text)
    return RedactionResult(out, dict(r.counts))
