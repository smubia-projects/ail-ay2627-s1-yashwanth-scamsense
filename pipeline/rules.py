"""Deterministic checks: plain code, no LLM. Everything here is unit tested (tests/test_rules.py).

Rules can only RAISE suspicion. There is intentionally no rule that says "this looks fine".
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from pipeline.redact import URL_RE
from pipeline.schemas import Message, RuleHit, Severity

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

_SECOND_LEVEL = {"com", "co", "gov", "org", "edu", "net", "ac"}
_HOMOGLYPHS = {
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "|": "l", "$": "s", "@": "a",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",  # Cyrillic
    "і": "i", "ѕ": "s", "ӏ": "l", "ο": "o", "α": "a", "ı": "i",  # Cyrillic/Greek/dotless i
}
_BRAND_TEXT_MIN = {"dbs", "uob", "cpf", "hdb", "ocbc", "posb", "ica", "iras"}  # short tokens safe to match in prose
_AMBIGUOUS_TEXT_TOKENS = {"mas", "mom", "police", "apple", "grab", "ica", "spf", "gov.sg", "govsg"}


# ---------------------------------------------------------------- knowledge loading

@lru_cache(maxsize=1)
def load_domains() -> dict:
    data = yaml.safe_load((KNOWLEDGE_DIR / "official_domains.yaml").read_text(encoding="utf-8"))
    entities = data["entities"]
    official: dict[str, str] = {}  # registrable domain -> entity name
    for e in entities:
        for d in e["domains"]:
            official[d.lower()] = e["name"]
    return {
        "entities": entities,
        "official": official,
        "shorteners": {s.lower() for s in data.get("url_shorteners", [])},
        "risky_tlds": {s.lower() for s in data.get("risky_tlds", [])},
    }


# ---------------------------------------------------------------- domain helpers

def edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein with early exit above `cap`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def normalise_homoglyphs(s: str) -> str:
    s = unicodedata.normalize("NFKC", s.lower())
    s = s.replace("rn", "m").replace("vv", "w")
    return "".join(_HOMOGLYPHS.get(c, c) for c in s)


def extract_urls(text: str) -> list[str]:
    urls = [m.group(0).rstrip(".,;:!?)") for m in URL_RE.finditer(text)]
    # bare domains like "dbs-secure.xyz/login" without scheme
    for m in re.finditer(r"(?i)\b((?:[a-z0-9¡-￿\-]+\.)+[a-z]{2,24})(/[^\s]*)?", text):
        cand = m.group(0).rstrip(".,;:!?)")
        host = m.group(1).lower()
        if any(cand in u for u in urls):
            continue
        if "@" in text[max(0, m.start() - 1): m.start()]:
            continue  # part of an email
        tld = host.rsplit(".", 1)[-1]
        known = {"com", "sg", "net", "org", "co", "info", "xyz", "top", "icu", "vip", "click", "cc", "app", "me", "io", "ly", "to",
                 "gl", "is", "gd", "tk", "cyou", "buzz", "shop", "online", "site", "live", "cfd", "sbs", "link", "pw", "ws", "gov"}
        if tld in known and not re.fullmatch(r"\d+\.\d+", host) and host not in {"e.g", "i.e"}:
            urls.append(cand)
    return urls


def host_of(url: str) -> str:
    u = url if "://" in url else "http://" + url
    try:
        host = urlparse(u).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:  # e.g. com.sg, co.uk
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_official_host(host: str) -> str | None:
    off = load_domains()["official"]
    reg = registrable(host)
    if reg in off:
        return off[reg]
    # parent-suffix match (e.g. foo.singpass.gov.sg -> gov.sg family)
    for d, name in off.items():
        if host == d or host.endswith("." + d):
            return name
    return None


def _collapse_repeats(s: str) -> str:
    return re.sub(r"(.)+", r"", s)


def _is_lookalike(label: str, off_label: str) -> bool:
    """Is `label` a typo / homoglyph / repeated-letter imitation of the official `off_label`?

    Short official labels (dbs, uob, cpf...) are matched strictly to avoid flagging ordinary words.
    """
    if label == off_label or len(off_label) < 3:
        return False
    norm = normalise_homoglyphs(label)
    if norm == off_label or _collapse_repeats(label) == off_label:
        return True
    if len(off_label) <= 4:
        return False
    return edit_distance(label, off_label, 2) <= 2 or edit_distance(norm, off_label, 1) <= 1


def check_domain(url: str, claimed_brand_text: set[str] | None = None) -> list[tuple[str, Severity, str]]:
    """Return [(rule_id, severity, description)] for one URL."""
    dom = load_domains()
    host = host_of(url)
    out: list[tuple[str, Severity, str]] = []
    if not host:
        return out
    reg = registrable(host)

    if reg in dom["shorteners"] or host in dom["shorteners"]:
        out.append(("url_shortener", Severity.MEDIUM, f"Shortened link ({host}) hides where it really goes"))
        return out
    if re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", host):
        out.append(("ip_url", Severity.MEDIUM, "Link points to a raw IP address instead of a named website"))
        return out
    if "xn--" in host:
        out.append(("punycode_domain", Severity.HIGH, f"Link uses look-alike international characters ({host})"))
    if "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        out.append(("url_userinfo", Severity.MEDIUM, "Link contains '@' — it can disguise the true destination"))

    official_name = is_official_host(host)
    if official_name:
        return out  # genuine official domain/subdomain

    label = reg.split(".")[0]
    label_norm = normalise_homoglyphs(label)
    flagged = False
    for e in dom["entities"]:
        for d in e["domains"]:
            off_label = d.split(".")[0]
            if _is_lookalike(label, off_label):
                out.append(("lookalike_domain", Severity.HIGH,
                            f"'{host}' imitates the real {e['name']} domain '{d}'"))
                flagged = True
                break
        if flagged:
            break
    if not flagged:
        # 2. brand name used inside somebody else's domain (dbs-secure-login.com, sing-post.top, 0cbc-online.com)
        label_n = normalise_homoglyphs(label)
        parts = set(re.split(r"[-_.]", label)) | set(re.split(r"[-_.]", label_n)) | {label, label_n}
        flat = re.sub(r"[-_.]", "", normalise_homoglyphs(host))
        flat_raw = re.sub(r"[-_.]", "", host)
        for e in dom["entities"]:
            for tok in e["tokens"]:
                t = tok.replace(".", "")
                if len(t) < 3:
                    continue
                if (t in parts or (len(t) >= 5 and (t in flat or t in flat_raw))
                        or (t == "govsg" and "govsg" in flat_raw)):
                    out.append(("brand_in_domain", Severity.HIGH,
                                f"'{host}' uses the {e['name']} name but is not a {e['name']} domain"))
                    flagged = True
                    break
            if flagged:
                break
        # 3. an official domain pasted as a sub-label of another domain: dbs.com.sg.verify.xyz
        if not flagged:
            for d in dom["official"]:
                if (d + ".") in host + "." and not host.endswith(d):
                    out.append(("official_domain_as_subdomain", Severity.HIGH,
                                f"'{host}' embeds '{d}' to look official"))
                    flagged = True
                    break
    if not flagged and claimed_brand_text:
        out.append(("brand_link_mismatch", Severity.MEDIUM,
                    f"Message names {', '.join(sorted(claimed_brand_text))} but links to '{host}', which is not an official domain"))
    if reg.rsplit(".", 1)[-1] in dom["risky_tlds"]:
        out.append(("risky_tld", Severity.LOW, f"'.{reg.rsplit('.', 1)[-1]}' domains are common on throw-away scam sites"))
    return out


def brands_mentioned(text: str) -> set[str]:
    low = text.lower()
    found: set[str] = set()
    for e in load_domains()["entities"]:
        for tok in e["tokens"]:
            if "." in tok:
                continue
            if tok in _AMBIGUOUS_TEXT_TOKENS and tok not in _BRAND_TEXT_MIN:
                continue
            if len(tok) < 3:
                continue
            if tok in _BRAND_TEXT_MIN or len(tok) >= 4:
                if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", low):
                    found.add(e["name"])
    return found


# ---------------------------------------------------------------- text patterns

NEG = r"(?:do not|don't|dont|never|won't|will not|not to|no one will|nobody will|we (?:will )?never|wouldn't)"

_P = lambda s: re.compile(s, re.I | re.S)  # noqa: E731

PATTERNS: list[tuple[str, Severity, re.Pattern, str]] = [
    ("gift_card_request", Severity.HIGH,
     _P(r"(?:buy|purchase|get|send|scratch|read(?: out)?|give|top[- ]?up|pay (?:with|using|in))\b[^.\n]{0,60}\b(?:gift ?cards?|itunes|google play (?:card|code)|steam (?:card|wallet)|razer gold|apple card)|\b(?:gift ?cards?|itunes cards?)\b[^.\n]{0,50}\b(?:code|pin|serial|photo|picture|scratch)"),
     "Asks you to pay or send codes using gift cards"),
    ("crypto_request", Severity.MEDIUM,
     _P(r"(?:send|transfer|deposit|pay|buy|convert|invest)\b[^.\n]{0,60}\b(?:bitcoin|btc|usdt|tether|ethereum|eth|crypto(?:currency)?|binance|bitcoin atm|wallet address)|\b(?:wallet address|bitcoin atm)\b"),
     "Asks for payment or deposits in cryptocurrency"),
    ("safe_account", Severity.HIGH,
     _P(r"\b(?:safe|secure|holding|temporary|escrow|audit|verification|protection|neutral|government|custody) account\b"),
     "Asks you to move money to a 'safe/holding' account — a hallmark of impersonation scams"),
    ("personal_transfer", Severity.MEDIUM,
     _P(r"(?:transfer|pay|send|deposit|remit|bank in|paynow|pay ?lah)\b[^.\n]{0,70}(?:to|into)\b[^.\n]{0,45}(?:account|\[ACCOUNT_\d+\]|\[PHONE_\d+\]|paynow|uen)|\bpaynow\b[^.\n]{0,40}(?:\[PHONE_\d+\]|\d{8})"),
     "Asks for a transfer to a specific account or PayNow number"),
    ("upfront_fee", Severity.MEDIUM,
     _P(r"(?:pay|settle|transfer|send)\b[^.\n]{0,40}\b(?:deposit|processing fee|admin(?:istration)? fee|release fee|customs? (?:fee|duty)|clearance fee|redelivery fee|insurance fee|tax|handling fee|activation fee|registration fee)|\b(?:redelivery|re-delivery|re-schedule|reschedule)\b[^.\n]{0,40}\b(?:fee|pay|charge|\$)"),
     "Asks for an upfront fee before something is released or delivered"),
    ("remote_access_app", Severity.HIGH,
     _P(r"\b(?:anydesk|teamviewer|quicksupport|ultraviewer|rustdesk|airdroid|remote (?:access|control|desktop)|screen[- ]?shar(?:e|ing)|\.apk|apk file|\bapk\b)\b|(?:enable|allow|turn on)\b[^.\n]{0,30}\bunknown sources"),
     "Asks you to install remote-control software or an app from outside the app store"),
    ("app_install", Severity.LOW,
     _P(r"(?:install|download|sideload)\b[^.\n]{0,40}\b(?:app|software|application|program|link)\b"),
     "Asks you to download or install an app"),
    ("credential_request", Severity.HIGH,
     _P(r"(?:share|send|give|provide|tell|read out|read me|enter|key in|type in|confirm|verify|submit|reply with|screenshot)\b[^.\n]{0,45}\b(?:otp|one[- ]time (?:password|pin|code)|singpass|passcode|password|pin\b|cvv|cvc|card number|internet banking|login|log-in|credentials|tac\b|verification code|security code|\[otp_\d+\])"),
     "Asks for an OTP, password, Singpass or card detail — real organisations never ask for these"),
    ("isolation", Severity.MEDIUM,
     _P(r"(?:" + NEG + r")\b[^.\n]{0,25}\b(?:tell|inform|discuss|speak|talk|let)\b[^.\n]{0,45}\b(?:anyone|anybody|family|friends?|bank|colleague|wife|husband|parents?|children|boss|police)|keep (?:this|it) (?:confidential|secret|private|between us)|\bconfidential (?:investigation|case|matter)|\b(?:do not|don't|dont) (?:hang up|end the call|disconnect)|stay on the (?:line|call)"),
     "Tells you to keep this secret or not to talk to others"),
    ("channel_switch", Severity.LOW,
     _P(r"(?:add|contact|message|whatsapp|text|dm|move|continue|chat|reach|talk)\b[^.\n]{0,40}\b(?:on|via|to|through)\b[^.\n]{0,15}\b(?:whatsapp|telegram|wechat|signal|line|skype)\b|\bt\.me/|\bwa\.me/|\bwhatsapp me\b"),
     "Moves the conversation to another app"),
    ("authority_threat", Severity.MEDIUM,
     _P(r"(?:arrest\w*|warrants?|money[- ]laundering|detain\w*|prosecut\w*|legal action|court (?:summons|order|case)|criminal (?:case|investigation|charge)|frozen|freez\w+|blacklist\w*|suspend\w*|terminat\w+)\b"),
     "Threatens arrest, legal action or account suspension"),
    ("authority_claim", Severity.LOW,
     _P(r"\b(?:i am|this is|i'm|calling from|we are|with)\b[^.\n]{0,30}\b(?:police|inspector|officer|mas\b|ica\b|iras\b|mom\b|court|prosecutor|detective|customs|immigration|ministry|cyber ?security|bank officer|investigat)"),
     "Claims to be a government or bank official"),
    ("prize_reward", Severity.MEDIUM,
     _P(r"(?:you(?:'ve| have)? (?:won|been selected)|congratulations[^.\n]{0,30}(?:won|winner|selected|prize)|claim your (?:prize|reward|refund|gift|points)|lucky draw|unclaimed (?:refund|prize|funds)|tax refund|points (?:are )?(?:about to )?expir)"),
     "Promises a prize, refund or reward you did not ask for"),
    ("job_task_scam", Severity.MEDIUM,
     _P(r"(?:earn|make)\b[^.\n]{0,25}\$?\d[\d,]*\s*(?:/|per|a|every)\s*(?:day|hour|week)|(?:like|follow|rate|boost)\b[^.\n]{0,30}\b(?:videos?|products?|hotels?|apps?|merchants?)\b[^.\n]{0,40}\b(?:commission|earn|paid)|(?:complete|finish)\b[^.\n]{0,30}\btasks?\b[^.\n]{0,60}(?:commission|earn|top[- ]?up|deposit|prepay)|top[- ]?up\b[^.\n]{0,40}\b(?:task|order|account|set)|part[- ]?time job[^.\n]{0,60}(?:\$\d|commission|daily)"),
     "Offers easy online money for 'tasks' — typical of task/prepayment job scams"),
    ("investment_promise", Severity.MEDIUM,
     _P(r"guaranteed (?:returns?|profits?|income)|\b\d{2,4}\s?% (?:returns?|profit|gains?|monthly|weekly|daily)|(?:insider|inside) (?:tip|info|trading)|trading signals?|risk[- ]free|can't lose|double your (?:money|investment)|\bforex\b[^.\n]{0,40}\bprofit"),
     "Promises guaranteed or unusually high investment returns"),
    ("impersonated_relative", Severity.LOW,
     _P(r"(?:this is my new number|changed my number|new (?:phone )?number|lost my phone|phone (?:is )?broken|hi (?:mum|mom|dad|mama|papa|ma|pa)\b|it'?s me\b)"),
     "Looks like a 'family/friend with a new number' opener"),
    ("urgency", Severity.LOW,
     _P(r"\b(?:immediately|right now|within (?:the next )?\d+\s*(?:minutes?|mins?|hours?|hrs?)|today only|last (?:chance|warning|notice)|final notice|urgent(?:ly)?|asap|as soon as possible|expire[sd]? (?:today|in)|before (?:midnight|5pm|today)|or else|act now|time is running)\b"),
     "Pressures you to act immediately"),
    ("handoff", Severity.LOW,
     _P(r"(?:transfer|connect|pass|refer|escalate|hand)\w*\b[^.\n]{0,25}\b(?:you|your (?:call|case))\b[^.\n]{0,40}\b(?:officer|senior|supervisor|inspector|police|mas\b|investigat|specialist|manager|department|team|agent)|(?:my|our) (?:senior|supervisor|superior|colleague|officer)\b[^.\n]{0,30}\b(?:will|shall) (?:contact|call|message|speak|assist|handle)"),
     "Hands you over to another 'official' or 'senior'"),
    ("ai_instruction_injection", Severity.MEDIUM,
     _P(r"ignore (?:all |any |the |your )?(?:previous|prior|above|earlier|preceding)|disregard (?:all |any |the |your )?(?:previous|prior|above|instructions|rules)|forget (?:all |your )?(?:previous|prior|instructions)|system prompt|you are now\b|new instructions?\s*:|\b(?:as|you are) an? (?:ai|language model|assistant|chatbot)\b|(?:this|the) (?:message|conversation|chat|text|sender|link)(?: is| are| was)\b[^.\n]{0,20}\b(?:safe|legit(?:imate)?|genuine|authentic|verified|not (?:a )?scam)|(?:mark|classify|label|rate|output|respond|reply|answer|say|verdict)\b[^.\n]{0,40}\b(?:as )?(?:safe|legit(?:imate)?|not (?:a )?scam|genuine)|<\s*/?\s*(?:system|instructions?)\s*>|\[/?INST\]|###\s*(?:system|instruction)|do not (?:flag|warn|report)"),
     "Contains text addressed to an AI checker, telling it to ignore its rules or call this 'safe'"),
]

# patterns whose negation ("never share your OTP") must suppress the hit
_NEGATABLE = {"safe_account", "credential_request", "personal_transfer", "remote_access_app", "app_install", "gift_card_request", "crypto_request"}
# phrases showing the message is a warning *about* the behaviour, not a request for it
_WARNING_CONTEXT = re.compile(r"(?i)\b(?:never|do not|don't|dont|will not|won't|not)\b[^.\n]{0,40}\b(?:ask|request|share|give|disclose|reveal|provide|tell|call you)\b")


# the message is *describing* the behaviour as a scam ("asked her to transfer money... That is a scam"), not requesting it
_AWARENESS = re.compile(r"(?i)\b(?:that|this|it|which|these|those|such)\s+(?:is|are|was|were)\s+(?:a\s+)?(?:scams?|frauds?)\b|\bbeware\b|\bbe careful\b|\bwatch out\b|\bscam (?:alert|warning)\b")


def _hit_is_negated(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 60): end + 20]
    if _AWARENESS.search(text[max(0, start - 100): end + 60]):
        return True
    return bool(_WARNING_CONTEXT.search(window)) or bool(re.search(NEG + r"\b[^.\n]{0,30}$", text[max(0, start - 45): start], re.I))


def _excerpt(text: str, start: int, end: int, pad: int = 30) -> str:
    """Matched span plus some context, widened to whole words so it reads (and quotes) cleanly."""
    a, b = max(0, start - pad), min(len(text), end + pad)
    if a > 0:  # move forward to the next word start
        while a < start and not text[a - 1].isspace():
            a += 1
    if b < len(text):  # move back to the previous word end
        while b > end and not text[b].isspace():
            b -= 1
    return re.sub(r"\s+", " ", text[a:b]).strip()


def check_text(msg: Message) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for rule_id, sev, rx, desc in PATTERNS:
        for m in rx.finditer(msg.text):
            if rule_id in _NEGATABLE and _hit_is_negated(msg.text, m.start(), m.end()):
                continue
            ev = _excerpt(msg.text, m.start(), m.end())
            hits.append(RuleHit(rule_id=rule_id, message_idx=msg.idx, severity=sev, description=desc, evidence=ev[:140]))
            break  # one hit per rule per message
    # links
    brands = brands_mentioned(msg.text)
    seen: set[str] = set()
    for url in extract_urls(msg.text):
        for rule_id, sev, desc in check_domain(url, brands):
            key = f"{rule_id}:{host_of(url)}"
            if key in seen:
                continue
            seen.add(key)
            hits.append(RuleHit(rule_id=rule_id, message_idx=msg.idx, severity=sev, description=desc, evidence=url[:120]))
    return hits


def run_rules(messages: list[Message]) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for m in messages:
        hits.extend(check_text(m))
    return hits


_POINTS = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


def rule_level(hits: list[RuleHit]) -> str:
    """none | low | medium | high — a coarse summary the calibration step compares against the LLM."""
    if not hits:
        return "none"
    # injection attempts are suspicious by themselves but are not evidence of a specific scam type
    pts = sum(_POINTS[h.severity] for h in hits)
    if any(h.severity == Severity.HIGH for h in hits) or pts >= 6:
        return "high"
    if pts >= 3 or any(h.severity == Severity.MEDIUM for h in hits):
        return "medium"
    return "low"
