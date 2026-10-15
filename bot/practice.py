"""Practice mode: authored scenarios (content/practice_scenarios.yaml), tap-the-red-flags scoring.
No LLM is involved anywhere in this module. There is no free-form chat with a fake scammer."""
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import yaml
from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup as M
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot import keyboards
from bot.render import esc
from bot.session import Session

FILE = Path(__file__).resolve().parent.parent / "content" / "practice_scenarios.yaml"


@lru_cache(maxsize=1)
def load_scenarios() -> list[dict]:
    return yaml.safe_load(FILE.read_text(encoding="utf-8"))["scenarios"]


def score(scenario: dict, selected_ids: set[str]) -> tuple[int, int, list[str], list[str]]:
    """Return (points, max_points, missed_correct_labels, wrong_pick_labels). points = hits - wrong picks, floored at 0."""
    correct = {o["id"] for o in scenario["options"] if o["correct"]}
    hits = selected_ids & correct
    wrong = selected_ids - correct
    labels = {o["id"]: o["label"] for o in scenario["options"]}
    pts = max(0, len(hits) - len(wrong))
    return pts, len(correct), [labels[i] for i in sorted(correct - selected_ids)], [labels[i] for i in sorted(wrong)]


def _state(s: Session) -> dict:
    if s.practice is None:
        scen = load_scenarios()
        order = list(range(len(scen)))
        random.shuffle(order)
        s.practice = {"order": order, "pos": 0, "sel": set(), "pts": 0, "max": 0, "done": 0, "opts": [], "submitted": False}
    return s.practice


def _open_scenario(st: dict) -> dict:
    scen = load_scenarios()[st["order"][st["pos"] % len(st["order"])]]
    opts = list(range(len(scen["options"])))
    random.shuffle(opts)
    st.update(sel=set(), opts=opts, submitted=False)
    return scen


def render_scenario(scen: dict, st: dict) -> tuple[str, M]:
    lines = [f"🎯 <b>Practice — {esc(scen['title'])}</b>"]
    if scen.get("multiparty"):
        lines.append("👥 <i>Several senders — watch how they work together.</i>")
    lines.append("")
    for m in scen["messages"]:
        lines.append(f"<b>{esc(m['sender'])}</b>: {esc(m['text'])}")
    lines.append("\nTap everything that is a <b>red flag</b> (or a trap statement), then <b>Submit</b>.")
    rows = []
    for k, oi in enumerate(st["opts"]):
        o = scen["options"][oi]
        mark = "✅ " if oi in st["sel"] else "▫️ "
        rows.append([B(mark + o["label"], callback_data=f"p:t:{k}")])
    rows.append([B("📝 Submit", callback_data="p:s"), B("⬅️ Exit", callback_data="p:x")])
    lines.append(f"<i>Score so far: {st['pts']}/{st['max']} over {st['done']} scenario(s)</i>")
    return "\n".join(lines), M(rows)


def render_result(scen: dict, pts: int, mx: int, missed: list[str], wrong: list[str], st: dict) -> tuple[str, M]:
    lines = [f"🎯 <b>{esc(scen['title'])}</b>"]
    if scen.get("genuine"):
        lines.append(f"Points: <b>{pts}</b> (this one had no real red flags — {len(wrong)} wrong tap(s))")
    else:
        lines.append(f"Points: <b>{pts}/{mx}</b>")
    if missed:
        lines.append("\n🔴 <b>You missed:</b>\n" + "\n".join(f"• {esc(x)}" for x in missed))
    if wrong:
        lines.append("\n⚠️ <b>Not actually red flags:</b>\n" + "\n".join(f"• {esc(x)}" for x in wrong))
    if not missed and not wrong:
        lines.append("\n✅ Perfect!")
    lines.append(f"\n💡 {esc(scen['explanation'])}")
    from pipeline.retrieve import load_typologies
    typ = load_typologies().get(scen.get("typology_id", ""))
    if typ:
        lines.append(f"\n📚 <b>Scam type:</b> {esc(typ.name)}")
    lines.append(f"\n<i>Total: {st['pts']}/{st['max']} over {st['done']} scenario(s)</i>")
    return "\n".join(lines), M([[B("➡️ Next scenario", callback_data="p:n")], [B("⬅️ Menu", callback_data="menu")]])


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE, act: str) -> None:
    from bot.handlers import _c
    s = _c(context).sessions.get(update.effective_chat.id)
    q = update.callback_query
    st = _state(s)

    if act == "prc" or act == "p:n":
        if act == "p:n":
            st["pos"] += 1
        scen = _open_scenario(st)
        text, kb = render_scenario(scen, st)
        await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if act == "p:x":
        s.practice = None
        await update.effective_chat.send_message("Nice work. Back to the menu.", reply_markup=keyboards.main_menu())
        return

    scen = load_scenarios()[st["order"][st["pos"] % len(st["order"])]]
    if st["submitted"]:
        return
    if act.startswith("p:t:"):
        try:
            oi = st["opts"][int(act.split(":")[2])]
        except (ValueError, IndexError):
            return
        st["sel"] ^= {oi}
        text, kb = render_scenario(scen, st)
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            pass
    elif act == "p:s":
        ids = {scen["options"][oi]["id"] for oi in st["sel"]}
        pts, mx, missed, wrong = score(scen, ids)
        st["pts"] += pts
        st["max"] += mx
        st["done"] += 1
        st["submitted"] = True
        text, kb = render_result(scen, pts, mx, missed, wrong, st)
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=kb)
