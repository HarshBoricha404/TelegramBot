# IPO Signal Telegram Bot

A free, deterministic Indian IPO signal bot. It validates current grey-market data, ranks actionable IPOs, and posts one daily Telegram update at **9:00 AM IST** using GitHub Actions.

It uses no paid API, AI model, database, browser automation, or always-on server.

## What it checks

Primary sources:

- [IPO Watch live GMP](https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/) for Mainboard/SME type, GMP, trend, price, estimated listing gain, status, and timestamps
- [IPO Watch subscription status](https://ipowatch.in/ipo-subscription-status-today/) for QIB, NII, retail, and total demand
- IPO Watch detail pages for the top three candidates' total issue size, lot/application amount, listing date, and annual revenue/PAT

[IPO Premium](https://www.ipopremium.in/) is used to cross-check top GMP values and as a fallback when IPO Watch cannot be parsed.

The bot never averages unofficial GMP values. A material source disagreement lowers confidence.

## Signal rules

Only an IPO that is **open today**, **closes today or within the next 2 days**, has fresh and parseable data, positive GMP, and meets `MIN_GAIN_PCT` can receive `CONSIDER`.

- `CONSIDER`: actionable open IPO closing within 2 days, with signal score at least 60
- `WATCH`: stale/disputed, below the strong threshold, or still open but closing later
- `LOW SIGNAL`: non-positive GMP or weak/conflicting evidence

The 0–100 signal score uses capped GMP strength, live subscription demand, Mainboard liquidity preference, freshness/source agreement, and GMP trend. Verified recent losses or persistent annual PAT decline reduce the score. Missing optional detail metadata is neutral.

Mainboard is preferred. An SME becomes the primary pick only when its score is at least 15 points above the best qualifying Mainboard IPO, or no Mainboard IPO qualifies.

At 9:00 AM, same-day bidding has not started. Subscription figures are therefore usually the latest prior-session snapshot; the Telegram message displays the source timestamps.

## Telegram setup

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. For a channel, add the bot as an administrator with permission to post.
3. For a direct message, send the bot a message first and use your numeric Telegram chat ID.

## Free GitHub Actions deployment

Push the repository to GitHub, then open:

**Settings → Secrets and variables → Actions**

Create repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID` — numeric chat ID, `@channel`, or `-100...` channel ID

Optionally create repository variable:

- `MIN_GAIN_PCT` — defaults to `10` when absent or empty

Open **Actions → Daily IPO Signal → Run workflow** and verify the first Telegram message against IPO Watch.

The workflow runs from the default branch at `30 3 * * *` UTC (9:00 AM IST). GitHub may delay or occasionally drop scheduled jobs. In public repositories, GitHub automatically disables scheduled workflows after 60 days without repository activity; open the workflow and select **Enable workflow** to resume it.

Standard runners are free for public repositories. GitHub Free private repositories include 2,000 Actions minutes per month; this bot normally uses far less than one minute per day.

## Local test and one-off post

```bash
cd /Users/harsh/Desktop/TelegramBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add the real token and destination to `.env`, then run:

```bash
pytest -q
python -m src.main
```

Tests use committed HTML fragments and make no network requests.

## Failure behavior

- Network timeouts, HTTP 429, and server errors receive bounded retries.
- Unexpected/stale page layouts fail closed instead of producing a confident pick.
- If both GMP sources fail, the bot attempts a short Telegram operational alert and the Actions job exits non-zero.
- Telegram messages use escaped HTML and stay below the 4096-character limit.
- Tokens are never included in source URLs, logs, or error messages.

## Project layout

- `src/models.py` — normalized market and signal models
- `src/scraper.py` — source parsing, validation, enrichment, and fallback
- `src/recommend.py` — eligibility, score, confidence, and Mainboard preference
- `src/formatter.py` — safe Telegram HTML
- `src/digest.py` — pipeline orchestration
- `src/main.py` — one-shot entry point used by GitHub Actions
- `tests/` — offline parser, scoring, and formatter tests

## Disclaimer

GMP is unofficial and unregulated by SEBI. This bot provides an informational signal, not personalized investment advice or guaranteed returns. Confirm the RHP, exchange data, application amount, and your own risk tolerance before investing.
