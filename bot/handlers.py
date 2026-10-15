"""Telegram handlers. No handler ever logs message text; errors are logged by exception type only."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot import keyboards, render
from bot.mapimage import render_map
from bot.ratelimit import RateLimiter
from bot.session import SessionStore
from config import Settings
from pipeline.analyze import analyze
from pipeline.parse import merge_sources
from strings import t

log = logging.getLogger("scamsense.bot")
CONTENT = Path(__file__).resolve().parent.parent / "content"
HTML = ParseMode.HTML

_CACHE: dict[str, str] = {}


def static(name: str) -> str:
    """Fixed-content advice, read from content/*.md (never LLM-generated)."""
    if name not in _CACHE:
        _CACHE[name] = (CONTENT / f"{name}.md").read_text(encoding="utf-8").strip()
    return _CACHE[name]


class Ctx:
    """Shared objects stored in application.bot_data['ctx']."""

    def __init__(self, llm, settings: Settings, demo: bool) -> None:
        self.llm, self.s, self.demo = llm, settings, demo
        self.sessions = SessionStore(settings.session_ttl_s)
        self.analysis_limit = RateLimiter(settings.rate_limit_analyses, settings.rate_limit_window_s)
        self.msg_limit = RateLimiter(40, 60)  # raw messages per minute (flood guard)


def _c(context: ContextTypes.DEFAULT_TYPE) -> Ctx:
    return context.application.bot_data["ctx"]


def _uid(update: Update) -> int:
    return update.effective_user.id if update.effective_user else 0


async def _send(update: Update, text: str, **kw):
    kw.setdefault("parse_mode", HTML)
    kw.setdefault("disable_web_page_preview", True)
    return await update.effective_chat.send_message(text, **kw)


# ------------------------------------------------------------------ commands

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _c(context).sessions.get(update.effective_chat.id).clear_raw()
    demo = f"\n\n⚠️ <i>{render.esc('DEMO MODE: offline keyword stand-in, not a real AI model.')}</i>" if _c(context).demo else ""
    await _send(update, static("welcome") + demo, reply_markup=keyboards.main_menu())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send(update, static("privacy"), reply_markup=keyboards.back_menu())


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _begin_collecting(update, context)


async def cmd_analyse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_analysis(update, context)


# ------------------------------------------------------------------ collecting messages

HOW_TO = (
    "📥 <b>Send me the conversation.</b>\n\n"
    "Best results:\n"
    "• <b>Forward</b> the messages here (I keep each sender's name), or\n"
    "• Paste as <code>Name: message</code> lines, or a WhatsApp chat export.\n"
    "• Include <i>everyone</i> who contacted you — the whole chain matters.\n"
    "• Screenshots work too if enabled: add the sender's name as the photo caption.\n\n"
    "You can send several messages. Tap <b>Analyse</b> when you're done."
)


async def _begin_collecting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    c = _c(context)
    s = c.sessions.get(update.effective_chat.id)
    s.clear_raw()
    s.collecting = True
    s.status_msg_id = None
    await _send(update, HOW_TO, reply_markup=keyboards.collecting(0))


def _forward_name(msg) -> str | None:
    fo = getattr(msg, "forward_origin", None)
    if fo is None:
        return None
    u = getattr(fo, "sender_user", None)
    if u is not None:
        return (u.full_name or u.username or "Unknown")[:40]
    name = getattr(fo, "sender_user_name", None)
    if name:
        return name[:40]
    for attr in ("sender_chat", "chat"):
        ch = getattr(fo, attr, None)
        if ch is not None and getattr(ch, "title", None):
            return ch.title[:40]
    return "Unknown"


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    c = _c(context)
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if getattr(msg, "photo", None):
        await _on_photo(update, context)
        return
    text = msg.text or msg.caption
    if not text:
        await _send(update, "I can only read <b>text</b> for now. Please type or paste the key lines of the conversation.")
        return
    ok, wait = c.msg_limit.check(_uid(update))
    if not ok:
        await _send(update, t("limit.rate", mins=max(1, round(wait / 60))))
        return
    s = c.sessions.get(chat_id)
    if s.n_chars + len(text) > c.s.max_input_chars * 2 or len(s.items) >= c.s.max_messages:
        await _send(update, t("limit.too_long", max=c.s.max_input_chars), reply_markup=keyboards.collecting(len(s.items)))
        return
    s.collecting = True
    s.items.append((_forward_name(msg), text[: c.s.max_input_chars]))
    await _update_status(update, context)


async def _on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Screenshot input (stretch): local OCR only. The image never leaves this server and is not stored."""
    from pipeline import ocr
    c = _c(context)
    msg = update.effective_message
    if not ocr.available():
        await _send(update, "I can't read screenshots on this server yet. Please type or paste the key lines of the conversation "
                            "(or forward the original messages).")
        return
    ok, wait = c.msg_limit.check(_uid(update))
    if not ok:
        await _send(update, t("limit.rate", mins=max(1, round(wait / 60))))
        return
    s = c.sessions.get(update.effective_chat.id)
    if len(s.items) >= c.s.max_messages:
        await _send(update, t("limit.too_long", max=c.s.max_input_chars), reply_markup=keyboards.collecting(len(s.items)))
        return
    try:
        tg_file = await msg.photo[-1].get_file()
        data = bytes(await tg_file.download_as_bytearray())
        text = await ocr.ocr_image(data)
    except Exception as e:  # noqa: BLE001
        log.error("ocr failed: %s", type(e).__name__)
        await _send(update, "I couldn't read that image. Please type or paste the text instead.")
        return
    if len(text.strip()) < 8:
        await _send(update, "I couldn't find readable text in that image. A clearer, cropped screenshot helps — or paste the text.")
        return
    caption = (msg.caption or "").strip()[:40] or None  # the user's caption is used as the sender label
    s.collecting = True
    s.items.append((caption, text[: c.s.max_input_chars]))
    await _send(update, "🖼 Read the screenshot <b>locally</b> (the image is not stored or sent to any AI). "
                        "Tip: add the sender's name as the photo caption so I know who said what.")
    await _update_status(update, context)


async def _update_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    c = _c(context)
    s = c.sessions.get(update.effective_chat.id)
    names = s.senders()
    who = f" from {len(names)} sender{'s' if len(names) != 1 else ''}: {render.esc(', '.join(names[:4]))}" if names else ""
    body = f"📥 Got <b>{len(s.items)}</b> message{'s' if len(s.items) != 1 else ''}{who}. Send more, or tap Analyse."
    if s.status_msg_id:  # keep the chat tidy: replace the previous status
        try:
            await context.bot.delete_message(update.effective_chat.id, s.status_msg_id)
        except TelegramError:
            pass
    m = await _send(update, body, reply_markup=keyboards.collecting(len(s.items)))
    s.status_msg_id = m.message_id


# ------------------------------------------------------------------ analysis

async def _run_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    c = _c(context)
    chat_id = update.effective_chat.id
    s = c.sessions.get(chat_id)
    if not s.items:
        await _send(update, t("limit.empty"), reply_markup=keyboards.back_menu())
        return
    ok, wait = c.analysis_limit.check(_uid(update))
    if not ok:
        await _send(update, t("limit.rate", mins=max(1, round(wait / 60))))
        return

    items = list(s.items)
    s.clear_raw()  # raw text is dropped as soon as analysis starts
    s.status_msg_id = None
    progress = await _send(update, "🔎 <b>Analysing…</b>\n<i>Removing personal details → reading each message → checking tactics → comparing with known scams</i>")
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except TelegramError:
        pass
    try:
        messages, inferred = merge_sources(items)
        report = await analyze(messages, c.llm, speakers_inferred=inferred, settings=c.s)
    except Exception as e:  # noqa: BLE001 - the bot must never crash on analysis
        log.error("analysis crashed: %s", type(e).__name__)
        await progress.edit_text(t("error.generic"))
        return
    log.info("analysis done verdict=%s degraded=%s refused=%s msgs=%d latency=%.1fs", report.verdict.value, report.degraded,
             report.refused, len(report.messages), report.latency_s)
    s.report = None if report.refused else report
    demo = f"\n\n⚠️ <i>DEMO MODE: offline keyword stand-in, not a real AI model.</i>" if c.demo else ""
    try:
        await progress.edit_text(render.render_summary(report) + demo, parse_mode=HTML,
                                 reply_markup=keyboards.back_menu() if report.refused else keyboards.after_report())
    except TelegramError as e:
        log.error("edit failed: %s", type(e).__name__)
        await _send(update, render.render_summary(report) + demo, reply_markup=keyboards.after_report())


# ------------------------------------------------------------------ buttons

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    try:
        await q.answer()
    except TelegramError:
        pass
    c = _c(context)
    act = q.data or ""
    chat_id = update.effective_chat.id
    s = c.sessions.get(chat_id)

    if act == "menu":
        s.clear_raw()
        await _send(update, "What would you like to do?", reply_markup=keyboards.main_menu())
    elif act in ("chk", "new"):
        await _begin_collecting(update, context)
    elif act == "clr":
        s.clear_raw()
        s.collecting = True
        await _send(update, "Cleared. Send the conversation again whenever you're ready.", reply_markup=keyboards.collecting(0))
    elif act == "ana":
        await _run_analysis(update, context)
    elif act == "emg":
        await _send(update, static("emergency"), reply_markup=keyboards.back_menu())
    elif act == "rec":
        await _send(update, static("recovery"), reply_markup=keyboards.back_menu())
    elif act == "prv":
        await _send(update, static("privacy"), reply_markup=keyboards.back_menu())
    elif act == "fam":
        if s.report is None:
            await _send(update, "Check a conversation first and I'll turn the result into a short, forwardable warning (with no personal details).",
                        reply_markup=keyboards.back_menu())
        else:
            await _send(update, "👪 <b>Forward the message below to your family:</b>")
            await update.effective_chat.send_message(render.render_family_warning(s.report))
    elif act in ("evd", "rls", "map"):
        if s.report is None:
            await _send(update, "That result has expired (results are only kept in memory for a short time). Please run the check again.",
                        reply_markup=keyboards.back_menu())
        elif act == "evd":
            await _send(update, render.render_evidence(s.report))
        elif act == "rls":
            await _send(update, render.render_checks(s.report))
        else:
            try:
                png = render_map(s.report)
                await update.effective_chat.send_photo(io.BytesIO(png), caption="🗺 Conversation map — who said what, and where the red flags are.")
            except Exception as e:  # noqa: BLE001
                log.error("map failed: %s", type(e).__name__)
                await _send(update, "Sorry, I couldn't draw the map this time.")
    elif act.startswith("p:") or act == "prc":
        from bot import practice
        await practice.handle(update, context, act)
    else:
        await _send(update, "Sorry, that button has expired.", reply_markup=keyboards.main_menu())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # exception TYPE only: tracebacks can include message text in locals/args
    log.error("unhandled error: %s", type(context.error).__name__)
