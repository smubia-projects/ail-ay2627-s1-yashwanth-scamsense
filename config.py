"""Central configuration, read from environment variables (see .env.example). No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional dependency in prod images
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM: all inference goes through OpenRouter (OpenAI-compatible API)
    llm_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
    llm_fallback_model: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "meta-llama/llama-3.3-70b-instruct")
    llm_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    llm_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "25"))
    # Prompt Guard classifier layer: off (not on OpenRouter; the eval showed no measurable difference)
    use_prompt_guard: bool = _bool("USE_PROMPT_GUARD", False)
    prompt_guard_threshold: float = float(os.getenv("PROMPT_GUARD_THRESHOLD", "0.8"))

    # Telegram bot (phase 2, not part of the web deployment)
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    port: int = int(os.getenv("PORT", "8080"))

    max_input_chars: int = int(os.getenv("MAX_INPUT_CHARS", "6000"))
    max_messages: int = int(os.getenv("MAX_MESSAGES", "60"))
    rate_limit_analyses: int = int(os.getenv("RATE_LIMIT_ANALYSES", "6"))
    rate_limit_window_s: int = int(os.getenv("RATE_LIMIT_WINDOW_S", "600"))
    session_ttl_s: int = int(os.getenv("SESSION_TTL_S", "1800"))

    use_vision: bool = _bool("USE_VISION", False)


def get_settings() -> Settings:
    return Settings()
