"""Turn pasted text into speaker-labelled messages.

Supported: `[12/03/24, 3:45 PM] Name: msg` / `12/03/2024, 15:45 - Name: msg` (WhatsApp exports),
`Name: msg` blocks, and plain unlabeled text (-> one block, speakers inferred by the LLM later).
"""
from __future__ import annotations

import re

from pipeline.schemas import Message

# WhatsApp (iOS-style brackets and Android-style dash)
_WA_BRACKET = re.compile(r"^‎?\[(\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}),?\s+[\d:.]+\s*(?:[APap]\.?[Mm]\.?)?\]\s*(?P<name>[^:]{1,40}):\s?(?P<msg>.*)$")
_WA_DASH = re.compile(r"^‎?(\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}),?\s+[\d:.]+\s*(?:[APap]\.?[Mm]\.?)?\s+-\s+(?P<name>[^:]{1,40}):\s?(?P<msg>.*)$")
# generic "Name: message" (name: 1-4 words, <=32 chars, starts with a letter, no URL-ish chars)
_LABEL = re.compile(r"^(?P<name>[A-Za-zÀ-ɏ一-鿿][\wÀ-ɏ一-鿿 .'()\-]{0,31}?)\s*[:：]\s+(?P<msg>\S.*)$")

# Words that look like labels but are almost certainly not speaker names.
_NOT_NAMES = {
    "note", "notice", "urgent", "important", "warning", "reminder", "re", "fw", "fwd", "subject", "p.s", "ps",
    "attention", "alert", "dear", "hi", "hello", "update", "tip", "fyi", "otp", "ref", "reference", "http", "https",
    "total", "amount", "bank", "account", "payment", "step", "case", "name", "date", "time", "link", "address",
}

_SYSTEM_LINES = re.compile(r"(?i)^(messages and calls are end-to-end encrypted|<media omitted>|‎?.*(image|video|sticker|audio) omitted)\s*$")


def _plausible_name(name: str) -> bool:
    n = name.strip().lower().rstrip(".")
    if not n or n in _NOT_NAMES:
        return False
    if len(n.split()) > 4:
        return False
    if re.search(r"https?|www\.|\.com|\d{5,}", n):
        return False
    return True


def parse_conversation(text: str) -> tuple[list[Message], bool]:
    """Return (messages, speakers_inferred). If no labels are found, a single unlabeled block is returned."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if not _SYSTEM_LINES.match(ln.strip())]

    for rx in (_WA_BRACKET, _WA_DASH):
        parsed = _parse_with(lines, rx)
        if parsed:
            return parsed, False

    parsed = _parse_with(lines, _LABEL, require_plausible=True)
    if parsed:
        return parsed, False

    body = "\n".join(l for l in lines if l.strip()).strip()
    if not body:
        return [], True
    return [Message(idx=0, sender="Unknown", text=body, inferred_sender=True)], True


def _parse_with(lines: list[str], rx: re.Pattern, require_plausible: bool = False) -> list[Message] | None:
    msgs: list[list] = []  # [name, text]
    matched = 0
    nonempty = 0
    for ln in lines:
        if not ln.strip():
            continue
        nonempty += 1
        m = rx.match(ln.strip())
        if m and (not require_plausible or _plausible_name(m.group("name"))):
            matched += 1
            msgs.append([m.group("name").strip(), m.group("msg").strip()])
        elif msgs:
            msgs[-1][1] += "\n" + ln.strip()  # continuation of the previous message
        else:
            msgs.append(["Unknown", ln.strip()])  # preamble before the first label
    if matched == 0:
        return None
    # A lone "Note: ..." style line inside prose is not a conversation; need decent label coverage.
    if require_plausible and (matched < 2 or matched / max(nonempty, 1) < 0.4):
        return None
    out = []
    for i, (name, msg) in enumerate(msgs):
        out.append(Message(idx=i, sender=name, text=msg.strip(), inferred_sender=False))
    return out


def from_forwards(items: list[tuple[str, str]]) -> list[Message]:
    """Build messages from (sender, text) pairs, e.g. collected from Telegram forward metadata."""
    return [Message(idx=i, sender=s or "Unknown", text=t.strip()) for i, (s, t) in enumerate(items) if t and t.strip()]


def merge_sources(items: list[tuple[str | None, str]]) -> tuple[list[Message], bool]:
    """Combine forwarded (labelled) messages and pasted blocks (parsed) into one ordered conversation."""
    out: list[Message] = []
    inferred = False
    for sender, text in items:
        if sender:
            out.append(Message(idx=len(out), sender=sender, text=text.strip()))
        else:
            parsed, inf = parse_conversation(text)
            inferred = inferred or inf
            for m in parsed:
                out.append(Message(idx=len(out), sender=m.sender, text=m.text, inferred_sender=m.inferred_sender))
    return out, inferred
