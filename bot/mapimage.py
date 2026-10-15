"""Render the 'conversation map': one lane per sender, messages as bubbles coloured by the severity of what
automatic checks found in them, arrows showing who hands the victim to whom. Pure Pillow, generated in memory,
never written to disk. Shows redacted text only."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from pipeline.schemas import Report, Verdict
from strings import t

W = 960
PAD = 28
BG = (15, 19, 28)
PANEL = (28, 34, 48)
TEXT = (232, 236, 244)
MUTED = (140, 150, 170)
SEV = {"high": (239, 83, 80), "medium": (255, 167, 38), "low": (253, 216, 53), None: (96, 108, 130)}
VERDICT_COL = {Verdict.LIKELY_SCAM: (239, 83, 80), Verdict.SUSPICIOUS: (255, 167, 38), Verdict.CANT_TELL: (144, 164, 174)}
LANE_COLS = [(66, 165, 245), (171, 71, 188), (38, 166, 154), (255, 112, 67), (156, 204, 101)]
_FONT_CANDIDATES = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "LiberationSans-Regular.ttf", "/System/Library/Fonts/Helvetica.ttc"]
_BOLD_CANDIDATES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "LiberationSans-Bold.ttf"]


def _font(size: int, bold: bool = False):
    for name in (_BOLD_CANDIDATES if bold else _FONT_CANDIDATES) + _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        lines[-1] = lines[-1].rstrip(".,; ")[: max(0, len(lines[-1]) - 1)] + "…"
    return lines or [""]


def render_map(r: Report, max_rows: int = 10) -> bytes:
    msgs = r.messages[:60]
    senders = list(dict.fromkeys(m.sender for m in msgs))[:5] or ["Unknown"]
    lane_w = (W - 2 * PAD) // len(senders)
    lane_x = {s: PAD + lane_w * i + lane_w // 2 for i, s in enumerate(senders)}

    # which messages to show: prefer ones with findings, keep order
    sev_of: dict[int, str | None] = {}
    for h in r.rule_hits:
        if h.message_idx is None or h.rule_id == "ai_instruction_injection":
            continue
        cur = sev_of.get(h.message_idx)
        order = {None: 0, "low": 1, "medium": 2, "high": 3}
        if order[h.severity.value] > order[cur]:
            sev_of[h.message_idx] = h.severity.value
    shown = msgs
    if len(msgs) > max_rows:
        keep = sorted(sorted(msgs, key=lambda m: (-{None: 0, "low": 1, "medium": 2, "high": 3}[sev_of.get(m.idx)], m.idx))[:max_rows],
                      key=lambda m: m.idx)
        shown = keep

    stage_by_msg: dict[int, list[str]] = {}
    for s in r.stages:
        if s.present:
            for i in s.message_idxs:
                stage_by_msg.setdefault(i, []).append(t("stage." + s.stage.value))
    handoff_pairs = {tuple(sorted(c.message_idxs[:2])) for c in r.cross_party if c.kind.value == "handoff" and len(c.message_idxs) >= 2}

    f_t, f_h, f_b, f_s = _font(30, True), _font(18, True), _font(17), _font(14)
    bubble_w = min(lane_w - 18, 300)
    row_h = 120
    H = 150 + row_h * len(shown) + 80
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # header
    col = VERDICT_COL[r.verdict]
    d.rounded_rectangle([PAD, PAD, W - PAD, PAD + 70], 16, fill=PANEL, outline=col, width=3)
    d.ellipse([PAD + 18, PAD + 20, PAD + 48, PAD + 50], fill=col)
    d.text((PAD + 64, PAD + 14), t("verdict." + r.verdict.value), font=f_t, fill=col)
    d.text((W - PAD - 250, PAD + 26), f"{len(senders)} sender(s) · {len(msgs)} message(s)", font=f_b, fill=MUTED)

    # lane headers + guides
    y0 = PAD + 100
    for i, s in enumerate(senders):
        x = lane_x[s]
        lc = LANE_COLS[i % len(LANE_COLS)]
        d.rounded_rectangle([x - lane_w // 2 + 8, y0, x + lane_w // 2 - 8, y0 + 34], 10, fill=lc)
        name = s if len(s) <= 22 else s[:21] + "…"
        d.text((x - d.textlength(name, font=f_h) / 2, y0 + 7), name, font=f_h, fill=(10, 14, 22))
        d.line([x, y0 + 40, x, H - 70], fill=(40, 48, 66), width=2)

    # messages
    pos: dict[int, tuple[int, int, int]] = {}
    y = y0 + 56
    for m in shown:
        x = lane_x.get(m.sender, lane_x[senders[-1]])
        sev = sev_of.get(m.idx)
        c = SEV[sev]
        lines = _wrap(d, m.text.replace("\n", " "), f_s, bubble_w - 28, 3)
        h = 24 + 19 * len(lines)
        x1, x2 = x - bubble_w // 2, x + bubble_w // 2
        d.rounded_rectangle([x1, y, x2, y + h], 12, fill=PANEL)
        d.rounded_rectangle([x1, y, x1 + 7, y + h], 4, fill=c)
        d.text((x1 + 16, y + 6), f"#{m.idx + 1}", font=_font(12, True), fill=c)
        for k, ln in enumerate(lines):
            d.text((x1 + 16, y + 22 + 19 * k), ln, font=f_s, fill=TEXT)
        tags = (stage_by_msg.get(m.idx) or [])[:2]
        tx = x1
        for tg in tags:
            tw = d.textlength(tg, font=_font(12)) + 14
            d.rounded_rectangle([tx, y + h + 4, tx + tw, y + h + 22], 8, outline=c, width=1)
            d.text((tx + 7, y + h + 6), tg, font=_font(12), fill=c)
            tx += tw + 6
        pos[m.idx] = (x, y, y + h)
        y += row_h

    # arrows between consecutive shown messages from different senders
    ids = [m.idx for m in shown]
    for a, b in zip(ids, ids[1:]):
        (xa, _, ya2), (xb, yb1, _) = pos[a], pos[b]
        hand = tuple(sorted((a, b))) in handoff_pairs
        if xa == xb:
            continue
        colr = SEV["high"] if hand else (70, 80, 104)
        w = 4 if hand else 2
        d.line([xa, ya2 + 22, xa, ya2 + 30, xb, yb1 - 6, xb, yb1], fill=colr, width=w)
        d.polygon([(xb - 6, yb1 - 9), (xb + 6, yb1 - 9), (xb, yb1)], fill=colr)
        if hand:
            d.text(((xa + xb) / 2 - 30, ya2 + 4), "HANDOFF", font=_font(13, True), fill=SEV["high"])

    # footer legend
    fy = H - 52
    lx = PAD
    for label, key in [("serious finding", "high"), ("warning sign", "medium"), ("minor", "low"), ("nothing flagged", None)]:
        d.rectangle([lx, fy + 4, lx + 14, fy + 18], fill=SEV[key])
        d.text((lx + 20, fy + 2), label, font=f_s, fill=MUTED)
        lx += 170
    d.text((PAD, fy + 24), "Personal details are removed. Aid, not a guarantee.", font=_font(12), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
