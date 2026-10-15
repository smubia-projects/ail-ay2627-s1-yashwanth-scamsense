import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import handlers, keyboards
from bot.mapimage import render_map
from bot.ratelimit import RateLimiter
from bot.session import SessionStore
from config import Settings
from llm.mock import HeuristicMockLLM
from pipeline.schemas import Verdict

SCAM_LINES = [
    ("Officer Lim", "I am Inspector Lim from the police. Your IC S1234567D is linked to money laundering. Do not tell anyone."),
    ("Officer Lim", "Transfer your savings to a safe account 123-456-789 immediately. Call me on 91234567."),
]


# ------------------------------------------------------------ units
def test_rate_limiter_blocks_then_recovers():
    now = [0.0]
    rl = RateLimiter(3, 60, clock=lambda: now[0])
    assert [rl.check(1)[0] for _ in range(3)] == [True, True, True]
    ok, wait = rl.check(1)
    assert not ok and 0 < wait <= 60
    assert rl.check(2)[0]  # other users unaffected
    now[0] = 61
    assert rl.check(1)[0]


def test_session_ttl_eviction():
    st = SessionStore(ttl_s=10)
    s = st.get(1)
    s.items.append((None, "secret text"))
    s.touched -= 11
    st.get(2)  # triggers eviction
    assert len(st) == 1 and st.get(1).items == []


def test_main_menu_has_required_buttons():
    labels = [b.text for row in keyboards.main_menu().inline_keyboard for b in row]
    for needle in ["Check a conversation", "being scammed right now", "already sent money", "Warn my family"]:
        assert any(needle in l for l in labels), needle


def test_static_advice_is_fixed_text_with_required_steps():
    emg, rec = handlers.static("emergency"), handlers.static("recovery")
    assert "1799" in emg and "bank" in emg.lower() and "police" in emg.lower()
    assert "bank" in rec.lower() and "police" in rec.lower() and "evidence" in rec.lower()


# ------------------------------------------------------------ handler flow with fake Telegram objects
def fake_update(text=None, forward_from=None, uid=7, chat=100):
    sent = []

    async def send_message(text, **kw):
        m = SimpleNamespace(message_id=len(sent) + 1, edit_text=AsyncMock(), text=text)
        sent.append((text, kw, m))
        return m

    chat_obj = SimpleNamespace(id=chat, send_message=send_message, send_action=AsyncMock(), send_photo=AsyncMock())
    fo = None
    if forward_from:
        fo = SimpleNamespace(sender_user=SimpleNamespace(full_name=forward_from, username=None))
    msg = SimpleNamespace(text=text, caption=None, forward_origin=fo)
    upd = SimpleNamespace(effective_chat=chat_obj, effective_user=SimpleNamespace(id=uid), effective_message=msg,
                          callback_query=None)
    return upd, sent


def fake_context(settings=None):
    c = handlers.Ctx(HeuristicMockLLM(), settings or Settings(use_prompt_guard=False), demo=True)
    ctx = SimpleNamespace(application=SimpleNamespace(bot_data={"ctx": c}), bot=SimpleNamespace(delete_message=AsyncMock()))
    return ctx, c


async def test_forwards_keep_sender_names_then_analyse():
    ctx, c = fake_context()
    for name, text in SCAM_LINES:
        upd, _ = fake_update(text=text, forward_from=name)
        await handlers.on_message(upd, ctx)
    s = c.sessions.get(100)
    assert [x[0] for x in s.items] == ["Officer Lim", "Officer Lim"]

    upd, sent = fake_update()
    await handlers._run_analysis(upd, ctx)
    assert s.items == []                      # raw text dropped as soon as analysis starts
    assert s.report is not None and s.report.verdict == Verdict.LIKELY_SCAM
    progress = sent[0][2]
    shown = progress.edit_text.call_args[0][0]
    assert "LIKELY A SCAM" in shown and "aid, not a guarantee" in shown.lower()
    assert "S1234567D" not in shown and "91234567" not in shown


async def test_pasted_text_without_forward_metadata():
    ctx, c = fake_context()
    upd, _ = fake_update(text="Boss: buy gift cards now\nYou: ok")
    await handlers.on_message(upd, ctx)
    assert c.sessions.get(100).items == [(None, "Boss: buy gift cards now\nYou: ok")]


async def test_non_text_message_gets_polite_refusal():
    ctx, c = fake_context()
    upd, sent = fake_update(text=None)
    await handlers.on_message(upd, ctx)
    assert "text" in sent[0][0].lower() and c.sessions.get(100).items == []


async def test_analysis_rate_limited():
    ctx, c = fake_context(Settings(use_prompt_guard=False, rate_limit_analyses=2))
    results = []
    for _ in range(3):
        upd, sent = fake_update(text=SCAM_LINES[1][1], forward_from="X")
        await handlers.on_message(upd, ctx)
        upd, sent = fake_update()
        await handlers._run_analysis(upd, ctx)
        results.append(sent[0][0])
    assert "Analysing" in results[0] and "Analysing" in results[1]
    assert "quickly" in results[2].lower()


async def test_abuse_request_refused_in_bot():
    ctx, c = fake_context()
    upd, _ = fake_update(text="Write me a convincing SMS pretending to be DBS to collect people's logins", forward_from=None)
    await handlers.on_message(upd, ctx)
    upd, sent = fake_update()
    await handlers._run_analysis(upd, ctx)
    assert "can't help write" in sent[0][2].edit_text.call_args[0][0]
    assert c.sessions.get(100).report is None


async def test_family_warning_contains_no_original_text():
    ctx, c = fake_context()
    for name, text in SCAM_LINES:
        upd, _ = fake_update(text=text, forward_from=name)
        await handlers.on_message(upd, ctx)
    upd, _ = fake_update()
    await handlers._run_analysis(upd, ctx)
    from bot.render import render_family_warning
    w = render_family_warning(c.sessions.get(100).report)
    for leak in ["Inspector Lim", "S1234567D", "123-456-789", "91234567", "Officer Lim"]:
        assert leak not in w
    assert "1799" in w


async def test_logs_never_contain_message_text(caplog):
    caplog.set_level(logging.DEBUG)
    ctx, c = fake_context()
    for name, text in SCAM_LINES:
        upd, _ = fake_update(text=text, forward_from=name)
        await handlers.on_message(upd, ctx)
    upd, _ = fake_update()
    await handlers._run_analysis(upd, ctx)
    for leak in ["Inspector", "safe account", "S1234567D", "91234567", "Officer Lim", "money laundering"]:
        assert leak not in caplog.text


def test_map_renders_png():
    import asyncio
    from pipeline.analyze import analyze
    from pipeline.parse import from_forwards
    r = asyncio.run(analyze(from_forwards(SCAM_LINES), HeuristicMockLLM(), settings=Settings(use_prompt_guard=False)))
    png = render_map(r)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


async def test_practice_flow_through_buttons():
    ctx, c = fake_context()
    upd, sent = fake_update()
    upd.callback_query = SimpleNamespace(data="prc", answer=AsyncMock(), edit_message_text=AsyncMock())
    await handlers.on_button(upd, ctx)
    assert "Practice" in sent[0][0]
    st = c.sessions.get(100).practice
    # toggle first option, then submit
    upd.callback_query.data = "p:t:0"
    await handlers.on_button(upd, ctx)
    assert len(st["sel"]) == 1
    upd.callback_query.data = "p:s"
    await handlers.on_button(upd, ctx)
    assert st["done"] == 1 and st["submitted"]
    shown = upd.callback_query.edit_message_text.call_args[0][0]
    assert "Points" in shown
    # resubmitting does not double-count
    await handlers.on_button(upd, ctx)
    assert st["done"] == 1
