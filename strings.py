"""All user-facing English strings in one place (i18n-ready: add another dict and select by language code).

Emergency / recovery advice is NOT here: it lives in content/*.md as fixed text.
"""
from __future__ import annotations

LANG = "en"

EN: dict[str, str] = {
    # ---- verdict presentation
    "verdict.Likely scam": "LIKELY A SCAM",
    "verdict.Suspicious": "SUSPICIOUS",
    "verdict.Can't tell": "CAN'T TELL",
    "verdict_hint.Likely scam": "This shows the typical pattern of a scam. Do not send money, codes or personal details.",
    "verdict_hint.Suspicious": "There are warning signs. Pause and verify through an official channel before doing anything.",
    "verdict_hint.Can't tell": "I couldn't find enough to judge. That is NOT the same as safe - if anything feels off, verify independently.",
    # ---- stage names
    "stage.first_contact": "First contact",
    "stage.claimed_authority": "Claims authority / identity",
    "stage.urgency": "Urgency or threat",
    "stage.isolation": "Isolation / secrecy",
    "stage.channel_switch": "Channel switch",
    "stage.request": "Money / OTP / app request",
    # ---- cross party
    "cross.vouching": "Vouching: one sender backs up another",
    "cross.handoff": "Handoff to a \"higher authority\"",
    "cross.repeated_tactic": "Same tactic used by different senders",
    "cross.coordinated_pressure": "Coordinated pressure from several senders",
    # ---- notes
    "note.degraded": "The AI analysis was unavailable or returned an invalid result, so I will not guess. Only automatic checks are shown below.",
    "note.inferred": "No speaker names were found, so I guessed who said what. This lowers my confidence. Pasting with names (or forwarding the messages) works better.",
    "note.injection": "This text contains instructions aimed at an AI checker (e.g. \"ignore your rules\" or \"say this is legitimate\"). Genuine organisations don't do that - it is a red flag in itself, and I ignored those instructions.",
    "note.no_signs": "I found no clear scam signs in what you shared. That does not guarantee it is safe.",
    "note.reassurance_removed": "(The AI's wording was replaced because it sounded like a guarantee, and I can't give guarantees.)",
    "note.truncated": "Your text was long, so only the first part was analysed.",
    "note.calibrated_up": "My automatic checks found stronger warning signs than the AI reading alone, so I chose the more cautious verdict.",
    "note.calibrated_down": "The AI reading and the automatic checks didn't fully agree, or confidence was low, so I chose a more cautious verdict.",
    "fallback_reason.Likely scam": "Several strong warning signs were found.",
    "fallback_reason.Suspicious": "Some warning signs were found.",
    "fallback_reason.Can't tell": "There isn't enough here for me to judge.",
    # ---- refusals / limits
    "refuse.generate": "I can't help write, improve or translate scam messages. I can check a message you've *received* and explain why it's risky.",
    "limit.too_long": "That's too long for me to analyse (max {max} characters). Please send the key part of the conversation.",
    "limit.rate": "You're sending requests very quickly. Please wait about {mins} minute(s) and try again.",
    "limit.empty": "I didn't find any text to analyse. Paste or forward the conversation first.",
    "error.generic": "Something went wrong on my side. Please try again in a moment. Your message was not stored.",
    # ---- disclaimer
    "disclaimer": "ScamSense is an aid, not a guarantee. It can be wrong. When in doubt, check with the official source or call 1799.",
}

STRINGS = {"en": EN}


def t(key: str, **kw: object) -> str:
    s = STRINGS.get(LANG, EN).get(key) or EN.get(key) or key
    return s.format(**kw) if kw else s
