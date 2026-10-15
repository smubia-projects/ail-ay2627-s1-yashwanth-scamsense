# ScamSense — working rules (summary of CLAUDE_CODE_PROMPT.md)

Hackathon project (AI Lodge, Track 1). Telegram bot that analyses multi-party scam conversations for people in Singapore.
Judged on: AI integration effectiveness, LLM safety/responsible AI (evidence > claims), usefulness.

## Hard rules
- **Never** `git push`, add/change remotes, or force anything. Commit locally, often, clear messages.
- Log every non-obvious decision in `DECISIONS.md`. Hotlines/wording to be double-checked by the owner are listed there.
- Verdict enum is exactly `Likely scam | Suspicious | Can't tell`. **Never "safe"/"legitimate"** — enforced in schema + output sanitiser.
- Calibration: disagreement or low confidence moves toward Suspicious / Can't tell, never toward reassurance.
- All user text is untrusted data: redact PII first (only redacted text reaches the LLM), delimit it, structured output only.
- No persistent storage of user content; logs never contain message text.
- Emergency / recovery advice is **static text**, never LLM-generated. Practice mode scenarios are authored YAML, never live-generated.
- Refuse to write/improve/translate scam messages. Rate-limit per user. Size-limit input.
- LLM failure → one retry → "Can't tell" with note. Never crash, never invent a verdict.
- Eval numbers are reported honestly (including failures). Keep dev/test split; do not tune on the held-out test split.
- Don't invent URLs/statistics in knowledge files; typologies are `verified: false` with TODO.

## Layout
`bot/` telegram · `pipeline/` redact, parse, extract, rules, stages, retrieve, verdict · `llm/` client abstraction (Groq default)
`knowledge/` typologies + official domains · `content/` static advice + practice scenarios · `eval/` · `tests/`

## Order of work
1 skeleton/redaction/schemas/LLM/never-safe+tests → 2 extraction/rules/CLI → 3 eval harness → 4 stages/retrieval →
5 Telegram bot → 6 full eval/injection/abuse → 7 deploy/README → 8 practice mode → 9 OCR stretch.
