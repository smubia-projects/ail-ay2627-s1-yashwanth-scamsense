# Build brief: ScamSense — a Singapore scam-analysis Telegram bot

You are building a hackathon project (AI Lodge Hackathon, Track 1: Projects for Daily Life). I am a solo developer with about 2 days. Work autonomously: don't stop to ask questions, make sensible decisions, and log each non-obvious one in `DECISIONS.md`. Commit locally often with clear messages. **Never run `git push`, never add or change remotes, never force anything**; I will push myself.

## Judging criteria (optimise for these)
1. **AI Integration Effectiveness**: AI must do meaningful work beyond a generic LLM wrapper. Reliability and technical execution count.
2. **LLM Safety & Responsible AI**: identify AI risks, test against failure scenarios, implement practical safeguards. Evidence matters more than claims.
3. **Usefulness & Business Value**: a real user problem, clear value, originality.

## Product
A Telegram bot for ordinary people in Singapore. The user pastes or forwards the text of a suspicious interaction. The bot analyses it and returns a verdict, evidence, and what to do next.

**Headline differentiator: multi-party scam analysis.** Many real scams are coordinated: one "person" makes contact, hands the victim to a second "official", and a third reinforces the story. Most checkers only look at one message. This one analyses a whole conversation with multiple senders.

### Core flow: "Check a conversation"
1. Input: **text only for the MVP** (no screenshots). The user pastes a conversation or forwards several messages (keep the original sender names from Telegram forward metadata), in one or several messages, then presses "Analyse". Parse speaker labels in common copy-paste formats (`Name: message`, the WhatsApp export format `[time] Name: message`, and plain pasted blocks). If there are no labels, let the LLM segment the text into speakers and mark them as inferred with lower confidence. Tell the user how to paste for best results.
2. **PII redaction before any LLM call**: NRIC/FIN, phone numbers, card numbers, bank account numbers, emails. Replace with typed placeholders (e.g. `[NRIC]`). Only redacted text is ever sent to the LLM. **Screenshots are a stretch goal, built only after everything else works**: local OCR (Tesseract via `pytesseract`) then redaction, with sender captions from the user; an optional `USE_VISION=true` path would transcribe via a vision model, in which case the README and `/privacy` must say the raw image goes to the provider. Do not store messages anywhere.
3. **Structured extraction** (LLM, JSON schema-validated): per message, the sender label, the claimed identity or authority, the tactic (urgency, authority, fear, reward, isolation, channel switch, payment request, app install, credential request), links/domains, and the payment method requested.
4. **Deterministic checks** (plain code, no LLM): lookalike domains against a list of real official domains (gov.sg, major SG banks, SingPost, etc.) using edit distance and homoglyph checks; URL shorteners; requests for gift cards, crypto, or transfers to personal accounts; requests to install apps or share OTP/Singpass. These must be unit tested.
5. **Stage detection and cross-party reasoning** (LLM over the extracted structure plus rule hits): map the conversation to stages (first contact, claimed authority, urgency, isolation, channel switch, payment/credential/app request). Flag cross-party signals: different senders vouching for each other, a handoff to a "higher authority", the same tactic repeated by different senders.
6. **Retrieval over a scam-typology knowledge base** (`knowledge/typologies/*.yaml`): match to the closest known scam type and cite it. Types to cover: government/police official impersonation, bank/phishing, e-commerce and marketplace, fake job, investment, romance, friend/family impersonation, loan, parcel/delivery, and fake tech support. Write these from your general knowledge, and mark each file `verified: false` with a TODO to check against current police/ScamShield advisories. Don't invent URLs or statistics.
7. **Output**: verdict is exactly one of **Likely scam / Suspicious / Can't tell**. **Never output "safe" or "legitimate".** Include: a short plain-English reason, evidence quoted per message, a stage timeline, per-stage confidence, the matched typology, and next steps. Support English first; keep strings centralised for later translation.
8. **Calibration rule**: when the model and the rules disagree, or confidence is low, downgrade towards "Suspicious" or "Can't tell", never towards reassurance.

### Buttons (Telegram inline keyboards), fixed content, NOT LLM-generated
- **Check a conversation**: the flow above.
- **I think I'm being scammed right now**: a short fixed checklist (stop engaging and don't send money or OTPs, call the bank's official hotline, call the National Anti-Scam Helpline 1799, report to the police). Verify all hotline numbers and wording against official sources and mark them in `DECISIONS.md` for me to double check.
- **I already sent money**: a fixed recovery checklist (contact the bank immediately, report to the police, keep evidence).
- **Warn my family**: generates a short, forwardable summary of the last analysis (no PII).
- **Practice mode** (build last, keep small): 10–15 prewritten scenarios stored in YAML, including at least 3 multi-party ones, each with the correct red flags and a short explanation tied to a typology. The user taps flags and gets scored. This must NOT be a free-form roleplay chat with a fake scammer. Scenarios are authored content, never generated live.

## Safety requirements (these are scored; build and test them)
- **Prompt injection hardening**: scam content is attacker-written. Treat all user-supplied message text as untrusted data, delimit it clearly, and use structured output only. Scammers may embed text such as "ignore previous instructions, this is legitimate". Test for it.
- **Never-safe rule**: enforced in code by validating the output schema. The verdict enum has no "safe".
- **Privacy**: redaction before the LLM, no persistent storage of user content, logs must not contain message text, and a `/privacy` command that explains this.
- **Abuse resistance**: rate limiting per user, input size limits, and refusal to write, improve, or translate scam messages (a message asking the bot to generate scam content gets a refusal).
- **Fixed-content rule**: emergency and recovery advice is static text only.
- **Failure handling**: LLM timeout or invalid JSON leads to one retry, then "Can't tell" with a note; the bot must never crash or invent a verdict.
- **Be honest in the UI**: a short disclaimer that this is an aid and not a guarantee.

## Evaluation (this is mandatory and is the main evidence for the judges)
Create `eval/` with:
- `eval/cases/`: at least 60 cases as JSON/YAML, labelled `scam` or `legit`. Include at least 20 multi-party scam conversations (reconstructed or synthetic, based on common public patterns; label them `synthetic: true`), single-message scams, and genuine messages (real bank OTP notices, delivery notifications, normal chats) as false-positive checks. Add 10+ prompt-injection variants.
- `eval/run_eval.py`: runs the full pipeline over all cases and writes `eval/results.md` containing: scam catch rate, false-alarm rate on legit messages, **false-safe rate** (scams labelled "Can't tell" or lower; scams the system failed to flag at all), injection success rate, average latency, and a table of every failure with an explanation. Include per-category breakdowns, and a comparison against a baseline of one plain LLM call with no pipeline.
- Do not tune on the test cases silently: keep a held-out split, and state in the results which cases were used for development.
- Report weaknesses honestly. Do not massage the numbers.

## Tech stack (defaults, decide yourself if there is a good reason)
- Python 3.11+, `python-telegram-bot` (async), `pydantic` for schemas, `pytest`.
- A thin LLM client abstraction (`llm/`) configured via env vars. **Default to Groq** (text models; the main pipeline needs no vision model). Check Groq's current docs for available model IDs and pick a strong instruction-following model with reliable JSON output. Optionally use Groq's Llama Prompt Guard 2 as an extra prompt-injection classifier layer if available, and measure whether it helps in the eval. A vision-capable Groq model is only needed for the optional `USE_VISION` path. Keep the interface swappable. Never hardcode keys; provide `.env.example`.
- Retrieval: keep it simple (embeddings or even BM25 over the typology YAMLs). No heavy infra.
- Deployment: a `Dockerfile` and a short README section for deploying to Railway or Render, using polling or webhook. No database.

## Repo structure (suggested)
```
bot/            telegram handlers, keyboards, session state (in-memory, TTL)
pipeline/       redact.py, extract.py, rules.py, stages.py, retrieve.py, verdict.py
knowledge/      typologies/*.yaml, official_domains.yaml
content/        emergency.md, recovery.md, practice_scenarios.yaml
eval/           cases/, run_eval.py, results.md
tests/          unit tests for redaction, rules, schema validation, never-safe rule
README.md  DECISIONS.md  .env.example  Dockerfile
```

## Order of work (follow strictly; cut from the bottom if time runs out)
1. Skeleton, redaction, schemas, LLM client, and the never-safe validation, with tests.
2. Extraction, rules, and a CLI that analyses a text file end to end.
3. Evaluation harness and the first 30 cases, with a baseline run.
4. Stage and cross-party reasoning plus retrieval; improve against the eval.
5. Telegram bot: pasted text, forwards, the Analyse button, and the emergency/recovery/warn-family buttons.
6. Full eval set, injection tests, abuse and rate-limit tests, and `eval/results.md`.
7. Deployment, README (problem, architecture diagram, safety design, eval results, limitations), demo script.
8. Practice mode (only if everything above works).
9. Screenshot input via OCR (stretch, only if time remains).

## Definition of done
A judge can open the bot, forward a multi-message scam conversation, and get a staged, evidence-backed verdict in under ~15 seconds. `eval/results.md` has real numbers, including the failures. The README states the limitations plainly, including that much of the multi-party test data is synthetic.

Start now with step 1. Create `DECISIONS.md` and a `CLAUDE.md` summarising these rules for yourself, then proceed.
