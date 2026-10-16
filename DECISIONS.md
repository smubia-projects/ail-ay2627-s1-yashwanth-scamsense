# Decisions log

Non-obvious decisions made while building ScamSense, with the reason. Items marked **⚠ OWNER TO CHECK** need a human to verify before the demo.

## ⚠ Owner to double-check before presenting

| Item | Where | What to check |
|---|---|---|
| **Helpline naming / numbers** | `content/emergency.md`, `content/recovery.md`, `bot/render.py`, `strings.py`, `content/privacy.md` | The brief calls 1799 the "National Anti-Scam Helpline". Current SPF/ScamShield pages I found describe **1799 as the ScamShield Helpline** (for checking whether something is a scam; can connect you to participating banks; cannot file police reports). Older police material lists an "Anti-Scam Helpline" at **1800-722-6688**. I used "ScamShield Helpline (1799)". Confirm the name and number at scamshield.gov.sg. |
| **Police Hotline 1800-255-0000, i-Witness (police.gov.sg/i-witness), 999** | same files | Taken from SPF pages surfaced by a web search; confirm on police.gov.sg. |
| **No bank hotline numbers** | `content/*.md` | Deliberately omitted: the checklists say "use the number on the back of your card / official app". Adding a list of numbers would be a maintenance and trust liability. |
| **Typology files** | `knowledge/typologies/*.yaml` | All `verified: false`. Written from general knowledge; compare with current SPF/ScamShield advisories. No URLs or statistics included on purpose. |
| **Official domains list** | `knowledge/official_domains.yaml` | `verified: false`. Confirm each domain on the organisation's own site. A domain missing from the list is never treated as proof of a scam by itself. |
| **Groq model IDs / Prompt Guard** | `config.py`, `llm/groq_client.py` | Verified live on 2026-10-16: `openai/gpt-oss-120b` works in JSON mode; `meta-llama/llama-prompt-guard-2-86m` returns a bare float string (parser OK). First full eval run completed (see `eval/results.md`). |

## Product / pipeline

1. **Two LLM calls, not one.** Call 1 extracts per-message structure (JSON-schema validated); call 2 reasons over structure + deterministic rule hits + retrieved typologies. Reason: matches the brief's pipeline, lets code (not the model) own the facts it can compute (domains, requests), and keeps each prompt small enough to be reliable. Cost: ~2 sequential round trips (Groq latency is low; Prompt Guard runs in parallel with call 1).
2. **Annotations are matched by message index, not re-typed.** For labelled input the LLM never copies message text back, which removes a hallucination surface. For unlabeled input the LLM segments the text, but a segment is accepted only if it appears verbatim in the input (≥70% of segments); otherwise the segmentation is rejected and the whole text is treated as one block.
3. **Evidence quotes are grounded in code.** Any quote the model returns that is not a verbatim substring of the cited message is dropped. If the model gives fewer than a few valid quotes, evidence is topped up from deterministic rule hits and extraction quotes (also verified as substrings). Evidence is never invented.
4. **Sender labels are pseudonymised for the LLM** (`Sender A/B/…`), then mapped back for display. Labels often contain real names ("Mum", "John Tan"). Trade-off: the model can't see that a label like "DBS Bank" was a sender name, only what it said. Names typed *inside* message text are not redacted (no NER) — stated in `/privacy` and the README limitations.
5. **Redaction placeholders are typed and numbered** (`[PHONE_1]`) so the same number reused by two senders is still visibly the same. Card numbers must pass a Luhn check; otherwise long digit strings are treated as bank accounts. OTP/PIN codes next to a keyword are redacted too. URLs are protected from the number patterns, because domains/paths matter to the rules.
6. **Rules only raise suspicion.** There is no rule that says "looks fine". Warnings *about* a behaviour ("never share your OTP", "that is a scam") suppress the request rules via a negation/awareness window. A scammer's "this is not a scam" deliberately does **not** suppress anything (tested).
7. **Deterministic cross-party signals** (`derive_cross_party`) back up the LLM: same tactic from ≥2 senders, and a `handoff` phrase followed by a different sender claiming an identity. They are merged with the model's signals.
8. **Retrieval is BM25 (≈40 lines, no dependency)** over the typology YAMLs. Rule hits and extracted tactics are expanded into hint words so retrieval is driven by structure, not just wording. The top-3 candidates are given to the reasoning call, which picks one (or none); the choice is validated against the KB ids.
9. **Typology/next steps are KB content**, not LLM free-text: "What to do next" comes from the typology YAML + a fixed generic list.

## Verdict policy (`pipeline/verdict.py`)

10. Ordering Likely scam > Suspicious > Can't tell. "Can't tell" is not reassurance and the wording says so.
11. Low model confidence steps *down* the ladder; model "Likely scam" with no meaningful rule hits → Suspicious; model "Can't tell" with medium/high rule hits → **Suspicious** (never reassure on disagreement); an injection attempt sets a floor of Suspicious.
12. **A disagreement that I chose not to resolve upward:** model "Suspicious" + high-severity rule stays Suspicious. This costs some "Likely scam" strictness but keeps the system from becoming confident because of one regex.
13. **Reassurance sanitiser:** free text from the model that reads like a guarantee ("is legitimate", "nothing to worry about", "safe to click") is replaced with a fixed sentence and a note. The regex is intentionally narrow so "move money to a safe account" (a scam phrase) is not mangled. Unit tested both ways.
14. **LLM failure:** one retry (covers transport errors and invalid JSON/schema), then `Can't tell` + a note. Deterministic findings are still listed. I did *not* upgrade to Suspicious in this mode even when rules fired high, to follow the brief literally ("then Can't tell with a note"); the findings are shown right under the verdict. Easy to change in `calibrate()` if you prefer.
15. **Prompt-injection posture:** untrusted text is wrapped in per-call random tags with delimiter-forging defused; both prompts say it is data; output is JSON-only and schema-validated; regex + Prompt Guard detect addressed-to-AI text; an injection attempt is itself reported as a red flag. The `ai_instruction_injection` regex is English-centric (the Malay injection case `inj11_malay` slips past it — it is in the eval as a known gap).

## Abuse / privacy / ops

16. **Refusal gate is regex + the extraction call's `input_kind`.** A scam *received* by the user is analysed; a request to write/improve/translate one is refused. Regex is conservative to avoid refusing ordinary text (tested on benign inputs).
17. **Raw text is dropped at the moment Analyse is tapped.** Only the redacted `Report` stays in memory (TTL 30 min) so Evidence / Warn-family / Map buttons work. No database, no disk writes. The map image is generated in memory.
18. **Logging:** bot logs event metadata only (verdict, counts, latency). `httpx`/`telegram` loggers are forced to WARNING because httpx logs full URLs, which contain the bot token. Error handler logs the exception *type* only. Tests assert no message text appears in logs.
19. **Rate limits:** 6 analyses / 10 min per user, 40 raw messages / min, input caps (6,000 chars per message, 60 messages). All configurable via env.
20. **The bot refuses to start without a Groq key** unless `DEMO_MODE=true`, in which case every response carries a "DEMO MODE" banner. The offline `HeuristicMockLLM` exists so the UI can be developed and demoed without a key; it is not an AI and its numbers must never be reported as model results (the eval marks mock runs loudly).
21. **No `python-telegram-bot` webhook secret handling beyond the default path** (`/telegram`). Fine for a hackathon; add a secret token for production.
22. **Groq client uses plain `httpx`** against the OpenAI-compatible endpoint instead of a vendor SDK: fewer dependencies, easy to swap provider via `LLM_BASE_URL`. `openai/gpt-oss-120b` primary with `llama-3.3-70b-versatile` fallback on any primary failure; JSON-object mode + pydantic validation (I did not rely on provider-side strict schema mode, whose availability varies by model).

## Evaluation

23. **Four arms:** full pipeline; pipeline without Prompt Guard (ablation); *one plain LLM call* baseline on raw text; and rules-only (no LLM). Rules-only matters: it shows how much the LLM actually adds, and it is the only arm that can run without a key.
24. **dev/test split by case ID**, listed in `results.md`. Prompt/rule iteration was allowed on `dev` only. One rule fix (scam-awareness context, motivated by dev case `l11_scam_warning_from_family`) was made after seeing the rules-only run. The `test` failures seen in that run (`mp09`, `mp13`, `s09`, `inj11`) were **not** patched, to avoid tuning on the held-out set.
25. **Injection success** = scam goes unflagged, *or* a canary string / system-prompt text appears in output. A case counts against the system if either happens.
26. **False-safe** is defined as a scam ending as "Can't tell", since the product has no "safe" output; this is the failure that matters most.
27. All eval cases are synthetic and written by the same author as the rules — flagged in `results.md` and README. The rules-only score is therefore *not* independent evidence.

## Stretch

28. **Screenshots (OCR)** — see `pipeline/ocr.py` and the README: local Tesseract OCR → redaction → same pipeline. Optional `USE_VISION=true` is *not implemented* (it would send the raw image to the provider); the code and docs only describe it as a future option, so there is no hidden path that uploads images.

## Game (`game/`, served by `sim/server.py`)

29. **Inbox Defender is an addition for demos/education, separate from the bot.** Vanilla JS, no build step; cases are authored data in `game/levels.js` (never generated live, like practice mode). It reuses the same typology ids as `knowledge/typologies/` (checked by `tests/test_game_levels.py`).
30. **The Scanner power-up calls the real pipeline** (`POST /api/scan` -> `analyze()`) on the whole ring's storyline (fictional text only). Limited to 3 per case client-side, 40 per 10 min server-side.
31. **Free typing without generated scam dialogue.** The brief forbids free-form roleplay with a fake scammer and requires scenarios to be authored. The game honours that: the player's typed text is classified by the LLM into one of 14 authored *intents* (structured output validated against the fixed id list; text is PII-redacted and delimiter-defused first; regex fallback offline), and the scammer's or genuine sender's reply is looked up from authored data. The AI never writes a scam message. Measured: 43/44 phrases correct (LLM), 35/44 (regex).
32. **Timers removed on request** (they rewarded speed, not judgement). Difficulty now comes from: one organised ring per case (members hand off, vouch, reuse details, with planted contradictions found by cross-examining), real contacts that sound just as pushy, ring members who know real details about you (so basic identity checks pass), a limited question budget per chat, a "Your life" card to check claims against, and a rule that you can't judge a chat before asking questions (unsupported guesses score less). `tests/test_game_levels.py` enforces that every scam leaks >= 2 tells, every genuine sender gives >= 2 verifiable good signs, and that placeholders resolve.
33. **Progress is stored in browser `localStorage` only (try/catch, optional)**; the server only sees typed-intent and Scanner requests (rate-limited, no logging of text).

## Evaluation follow-up (2026-10-17)

34. **False-alarm fix**: added a calibration paragraph to the reasoning prompt after Run 1 showed 4/20 genuine messages flagged. Because the Run 1 failure explanations (including `test` cases) had been read, the `test` split is no longer clean for false alarms; a fresh split of 20 new cases (`eval/cases/fresh.yaml`) was written *before* the change as the clean measurement. Result and caveats are in the README. The dev case `l01_bank_otp` remains a false alarm.
35. **Evidence de-duplication** (`verdict.fallback_evidence`): skip topped-up quotes that overlap an existing one.
36. **The ring never stops (anti-exploit).** An earlier version cancelled the rest of a ring when its first member was judged, so a player could finish a hard case after one lucky call. Now judging a member spawns the next ring members after a short delay ("they're not giving up"), so every voice must be cross-examined. 3 stars additionally require >= 2 clues on at least 75% of chats, so surviving by guessing earns at most 2 stars. Automated check (headless Chrome, typing into the real input): a scripted detective that asks questions cracks cases 1-6 with 3 stars; a gullible player ("ok, sending the money") loses savings or the case; a "call everything a scam" player loses trust on genuine chats (1-2 stars, ~half the score). This is a bot-based sanity check, not a human playtest.
