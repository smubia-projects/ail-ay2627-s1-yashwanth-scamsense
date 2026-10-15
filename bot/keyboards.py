"""Inline keyboards. Callback data is a short opaque action id."""
from __future__ import annotations

from pathlib import Path

from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup as M

PRACTICE_FILE = Path(__file__).resolve().parent.parent / "content" / "practice_scenarios.yaml"


def main_menu() -> M:
    rows = [
        [B("🔍 Check a conversation", callback_data="chk")],
        [B("🚨 I think I'm being scammed right now", callback_data="emg")],
        [B("💸 I already sent money", callback_data="rec")],
        [B("👪 Warn my family", callback_data="fam")],
    ]
    last = [B("🔒 Privacy", callback_data="prv")]
    if PRACTICE_FILE.exists():
        last.insert(0, B("🎯 Practice mode", callback_data="prc"))
    rows.append(last)
    return M(rows)


def collecting(n: int) -> M:
    return M([[B(f"✅ Analyse ({n} message{'s' if n != 1 else ''})", callback_data="ana")],
              [B("🗑 Clear", callback_data="clr"), B("⬅️ Menu", callback_data="menu")]])


def after_report(has_cross: bool = False) -> M:
    return M([
        [B("🔎 Evidence", callback_data="evd"), B("🧪 Automatic checks", callback_data="rls")],
        [B("🗺 Conversation map", callback_data="map")],
        [B("👪 Warn my family", callback_data="fam"), B("🚨 Act now", callback_data="emg")],
        [B("🆕 Check another", callback_data="chk"), B("⬅️ Menu", callback_data="menu")],
    ])


def back_menu() -> M:
    return M([[B("🔍 Check a conversation", callback_data="chk"), B("⬅️ Menu", callback_data="menu")]])
