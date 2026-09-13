# IPO Signal Telegram Bot

[![Tests](https://github.com/HarshBoricha404/TelegramBot/actions/workflows/tests.yml/badge.svg)](https://github.com/HarshBoricha404/TelegramBot/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A free, deterministic Indian IPO signal bot. It validates current grey-market data, ranks actionable IPOs, and posts one daily Telegram update at **9:00 AM IST** using GitHub Actions.

It uses no paid API, AI model, database, browser automation, or always-on server.

## Run your own bot

### 1. Fork the repository

Select **Fork** at the top of this GitHub repository. GitHub Actions will run from your fork, independently of the original bot.

### 2. Create a Telegram destination

1. Open [@BotFather](https://t.me/BotFather), run `/newbot`, and save the token.
2. Choose where the messages should go:
   - **Private channel:** create a channel and add the bot as an administrator with only **Post Messages** permission.
   - **Direct message:** open the new bot and send it a message first.
3. Obtain the destination ID. A channel ID normally looks like `-100...`; a public channel username can be supplied as `@channelname`.

Never put the token or destination ID in a committed file.

### 3. Configure GitHub

The workflow uses a protected GitHub Environment so deployment credentials remain separate from normal test runs.

1. In your fork, open **Settings → Environments → New environment**.
2. Name the environment exactly `TELEGRAM_BOT_TOKEN`.
3. In that environment, add these **environment secrets**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHANNEL_ID`
4. Optionally open **Settings → Secrets and variables → Actions → Variables** and add:
   - `MIN_GAIN_PCT` — minimum positive GMP percentage; defaults to `10`.

Environment secrets are not shared with forks or pull requests.

### 4. Test and enable it

1. Open **Actions → Daily IPO Signal**.
2. Select **Run workflow**.
3. Confirm the Telegram message and compare its data with the linked source pages.

The scheduled workflow runs daily at `30 3 * * *` UTC, which is **9:00 AM IST**. GitHub schedules can be delayed. GitHub may disable schedules in inactive public repositories after 60 days; re-enable the workflow from the Actions page if needed.

## What it checks

Primary sources:

- [IPO Watch live GMP](https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/) for Mainboard/SME type, GMP, trend, price, estimated listing gain, status, and timestamps
- [IPO Watch subscription status](https://ipowatch.in/ipo-subscription-status-today/) for QIB, NII, retail, and total demand
- IPO Watch detail pages for every closing-soon candidate: issue size, lot/application amount, listing venue, annual revenue/PAT, EPS/NAV, peer P/E, promoter holding, and objects of the issue

- IPO Watch [GMP vs listing history](https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/) to dampen rich premiums when recent IPOs listed below GMP

[IPO Premium](https://www.ipopremium.in/) is used to cross-check top GMP values and as a fallback when IPO Watch cannot be parsed.

The bot never averages unofficial GMP values. A material source disagreement lowers confidence.

## Signal rules

Only an IPO that is **open today**, **closes today or within the next 2 days**, has fresh and parseable data, positive GMP, and meets `MIN_GAIN_PCT` can receive `CONSIDER`.

- `CONSIDER`: actionable open IPO closing within 2 days, with signal score at least 60
- `WATCH`: stale/disputed, below the strong threshold, or still open but closing later
- `LOW SIGNAL`: non-positive GMP or weak/conflicting evidence

The 0–100 signal score now follows a listing-gain checklist, not “highest GMP wins”:

- GMP quality: 12–40% is the useful band; extreme SME GMP is treated as hype
- Recent listing-vs-GMP history dampens rich premiums; it never adds points when listings beat GMP
- Demand quality: QIB is weighted more than HNI/retail; weak or undersubscribed books are penalised, including on the last day
- Mainboard liquidity preference; SME must lead by 20 points to take #1
- Fresh GMP, rising trend, and source agreement
- Growing PAT/revenue help; losses, a sharp PAT drop, or a sudden profit spike hurt
- Implied P/E versus listed peers and high P/B are used when the detail page has EPS/NAV
- Fresh issue is preferred over a mostly-OFS exit; debt-repay objects and sharp promoter dilution are penalised
- Heavy oversubscription is flagged as a lottery, not extra strength

Detail pages are fetched for every open issue closing within 2 days (not only the GMP top 3).

The bot cannot read an RHP for promoter integrity or business model. Those still need a human.

Mainboard is preferred. An SME becomes the primary pick only when its score is at least 20 points above the best qualifying Mainboard IPO, or no Mainboard IPO qualifies.

At 9:00 AM, same-day bidding has not started. Subscription figures are therefore usually the latest prior-session snapshot; the Telegram message displays the source timestamps.

## Local test and one-off post

```bash
git clone https://github.com/YOUR_USERNAME/TelegramBot.git
cd TelegramBot
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

## Contributing

Contributions are welcome, especially parser fixtures, source-layout fixes, scoring tests, and clearer Telegram copy.

1. Fork the repository and create a focused branch.
2. Make the change and add or update offline tests.
3. Run `pytest -q`.
4. Open a pull request explaining the data source, scoring rationale, and user-visible effect.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before making a larger scoring or data-source change. Do not include real bot credentials, personal channel IDs, or scraped personal data in issues, fixtures, or pull requests.

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

## License

Released under the [MIT License](LICENSE).
