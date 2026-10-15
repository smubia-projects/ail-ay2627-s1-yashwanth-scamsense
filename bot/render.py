"""Turn a Report into Telegram-HTML messages (and plain text for the CLI).

All content is escaped; quotes shown are from the REDACTED text. Nothing here is LLM-free-form except the
short `reason` (already sanitised) and the quoted evidence."""
from __future__ import annotations

import html
import re

from pipeline.schemas import Report, Stage, Verdict
from strings import t

EMOJI = {Verdict.LIKELY_SCAM: "🔴", Verdict.SUSPICIOUS: "🟠", Verdict.CANT_TELL: "⚪"}
CROSS_EMOJI = {"vouching": "🤝", "handoff": "🔀", "repeated_tactic": "🔁", "coordinated_pressure": "👥"}
STAGE_EMOJI = {Stage.FIRST_CONTACT: "👋", Stage.CLAIMED_AUTHORITY: "🎭", Stage.URGENCY: "⏱️", Stage.ISOLATION: "🤫",
               Stage.CHANNEL_SWITCH: "📲", Stage.REQUEST: "💸"}

GENERIC_NEXT = [
    "Don't send money, codes (OTP) or passwords, and don't install anything they ask for.",
    "Stop replying. Verify by contacting the organisation yourself using a number or app you already trust.",
    "Keep the messages as evidence. If you're unsure, call the National Anti-Scam Helpline at 1799.",
]


def bar(p: float, width: int = 5) -> str:
    n = round(max(0.0, min(1.0, p)) * width)
    return "▰" * n + "▱" * (width - n)


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _trim(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def render_summary(r: Report) -> str:
    if r.refused:
        return f"🚫 {esc(r.reason)}"
    v = r.verdict
    lines = [f"{EMOJI[v]} <b>{esc(t('verdict.' + v.value))}</b>"
             + ("" if r.degraded else f"   ·   confidence {bar(r.confidence)} {round(r.confidence * 100)}%")]
    lines.append(f"<i>{esc(t('verdict_hint.' + v.value))}</i>")
    if r.reason and not r.degraded:
        lines.append("")
        lines.append(esc(r.reason))
    for n in r.notes:
        lines.append(f"\n⚠️ <i>{esc(n)}</i>")

    senders = list(dict.fromkeys(m.sender for m in r.messages))
    if len(senders) >= 2:
        lines.append(f"\n👥 <b>{len(senders)} senders analysed together:</b> " + esc(", ".join(senders[:6])))

    if r.stages and not r.degraded:
        lines.append("\n<b>Stage timeline</b>")
        for s in r.stages:
            mark = "✅" if s.present else "▫️"
            where = f" (msg {', '.join(str(i + 1) for i in s.message_idxs[:4])})" if s.present and s.message_idxs else ""
            conf = f" {bar(s.confidence)} {round(s.confidence * 100)}%" if s.present else ""
            lines.append(f"{mark} {STAGE_EMOJI[s.stage]} {esc(t('stage.' + s.stage.value))}{esc(where)}{conf}")

    if r.cross_party:
        lines.append("\n<b>Cross-party signals</b>")
        for c in r.cross_party[:4]:
            lines.append(f"{CROSS_EMOJI.get(c.kind.value, '•')} {esc(t('cross.' + c.kind.value))}"
                         + (f"\n    <i>{esc(_trim(c.description, 160))}</i>" if c.description else ""))

    if r.typology and v != Verdict.CANT_TELL or (r.typology and r.rule_hits):
        lines.append(f"\n📚 <b>Closest known scam type:</b> {esc(r.typology.name)}")
        lines.append(f"<i>{esc(_trim(r.typology.summary, 260))}</i>")

    if v != Verdict.CANT_TELL or r.rule_hits:
        lines.append("\n<b>What to do next</b>")
        steps = (r.typology.what_to_do if r.typology else []) + GENERIC_NEXT
        for i, st in enumerate(dict.fromkeys(steps)):
            if i >= 5:
                break
            lines.append(f"• {esc(st)}")

    lines.append(f"\n<i>{esc(t('disclaimer'))}</i>")
    return _cap("\n".join(lines))


def render_evidence(r: Report) -> str:
    lines = ["🔎 <b>Evidence</b> <i>(quotes are shown with personal details removed)</i>"]
    if r.evidence:
        for e in r.evidence:
            sender = r.messages[e.message_idx].sender if 0 <= e.message_idx < len(r.messages) else "?"
            lines.append(f"\n<b>Msg {e.message_idx + 1} · {esc(sender)}</b>\n“{esc(_trim(e.quote, 160))}”"
                         + (f"\n→ <i>{esc(_trim(e.why, 140))}</i>" if e.why else ""))
    else:
        lines.append("\nNo quotable evidence was extracted.")
    return _cap("\n".join(lines))


def render_checks(r: Report) -> str:
    lines = ["🧪 <b>Automatic checks</b> <i>(plain code, no AI - these can't be talked out of it)</i>"]
    if r.rule_hits:
        sev = {"high": "🔴", "medium": "🟠", "low": "🟡"}
        for h in sorted(r.rule_hits, key=lambda h: ["high", "medium", "low"].index(h.severity.value))[:12]:
            who = f"msg {h.message_idx + 1}" if h.message_idx is not None else ""
            lines.append(f"{sev[h.severity.value]} {esc(h.description)} <i>({who})</i>"
                         + (f"\n    <code>{esc(_trim(h.evidence, 100))}</code>" if h.evidence else ""))
    else:
        lines.append("\nNothing triggered. (That alone doesn't mean it's safe.)")
    if r.redaction_counts:
        red = ", ".join(f"{v}× {k.lower()}" for k, v in r.redaction_counts.items())
        lines.append(f"\n🔒 Removed before analysis: {esc(red)}")
    if r.calibration:
        lines.append("\n<b>Verdict adjustments</b>")
        lines += [f"• {esc(c)}" for c in r.calibration[:6]]
    lines.append(f"\n⏱ {r.latency_s:.1f}s")
    return _cap("\n".join(lines))


def render_family_warning(r: Report) -> str:
    """Forwardable summary with NO personal data: built only from verdict, typology and generic advice."""
    name = r.typology.name if r.typology else "a suspicious message"
    flags = []
    for s in r.stages:
        if s.present and s.stage != Stage.FIRST_CONTACT:
            flags.append(t("stage." + s.stage.value))
    lines = ["⚠️ Scam alert from ScamSense", "",
             f"I checked a conversation I received and it looked like: {name}.",
             f"Result: {t('verdict.' + r.verdict.value).title()}."]
    if flags:
        lines.append("Warning signs: " + "; ".join(flags[:5]) + ".")
    lines += ["", "Please remember:",
              "• Police, banks and government agencies will never ask you to transfer money, share your OTP or Singpass, or install apps.",
              "• Don't click links in unexpected messages. Call the organisation on a number you already trust.",
              "• If you're unsure, call the National Anti-Scam Helpline: 1799.",
              "", "(This is a general warning - it contains none of the original messages.)"]
    return "\n".join(lines)


def _cap(s: str, n: int = 3900) -> str:
    return s if len(s) <= n else s[: n - 20].rsplit("\n", 1)[0] + "\n…"


def to_plain(s: str) -> str:
    return html.unescape(re.sub(r"</?(?:b|i|code|pre|u)>", "", s))
