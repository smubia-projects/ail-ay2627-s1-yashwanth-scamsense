"""Entry point:  python -m bot.app     (long polling by default; webhook if WEBHOOK_URL is set)"""
from __future__ import annotations

import logging
import os
import sys

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot import handlers
from config import get_settings
from llm.mock import HeuristicMockLLM


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs, which contain the bot token -> keep them out of logs entirely
    for noisy in ("httpx", "httpcore", "telegram", "telegram.ext", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def build_app() -> Application:
    s = get_settings()
    if not s.telegram_token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set (see .env.example)")
    demo = False
    if s.llm_api_key:
        from llm.openrouter_client import OpenRouterClient
        llm = OpenRouterClient(s)
    elif os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes"):
        llm, demo = HeuristicMockLLM(), True
        logging.getLogger("scamsense").warning(HeuristicMockLLM.DEMO_BANNER)
    else:
        sys.exit("OPENROUTER_API_KEY is not set. (Set DEMO_MODE=true to run with the offline keyword stand-in for demos only.)")

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands([
            BotCommand("start", "Show the menu"), BotCommand("new", "Check a conversation"),
            BotCommand("analyse", "Analyse what I've sent"), BotCommand("privacy", "How your data is handled"),
        ])

    app = Application.builder().token(s.telegram_token).post_init(post_init).build()
    app.bot_data["ctx"] = handlers.Ctx(llm, s, demo)
    app.add_handler(CommandHandler(["start", "help"], handlers.cmd_start))
    app.add_handler(CommandHandler("privacy", handlers.cmd_privacy))
    app.add_handler(CommandHandler("new", handlers.cmd_new))
    app.add_handler(CommandHandler(["analyse", "analyze"], handlers.cmd_analyse))
    app.add_handler(CallbackQueryHandler(handlers.on_button))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handlers.on_message))
    app.add_error_handler(handlers.on_error)
    return app


def main() -> None:
    setup_logging()
    s = get_settings()
    app = build_app()
    if s.webhook_url:
        app.run_webhook(listen="0.0.0.0", port=s.port, webhook_url=s.webhook_url.rstrip("/") + "/telegram",
                        url_path="telegram", allowed_updates=Update.ALL_TYPES)
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
