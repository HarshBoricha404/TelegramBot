# IPO GMP Daily Telegram Reminder Bot

Scrapes [IPO Watch GMP](https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/), filters profitable Upcoming/Open IPOs (default ≥ 10% est. gain), and:

1. **Posts automatically every morning at 9:00 AM IST** to `TELEGRAM_CHANNEL_ID`
2. **Replies when you send `/gmp`** in a DM with the bot

GMP is unofficial and not investment advice.

## Setup

```bash
cd /Users/harshboricha/Desktop/TelegramBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_ID=...          # your user id, @channel, or -100... channel id
MIN_GAIN_PCT=10
TIMEZONE=Asia/Kolkata
DAILY_POST_HOUR=9
```

### Telegram bot

1. Create a bot with [@BotFather](https://t.me/BotFather) → put token in `.env`
2. For channel posts: add the bot as channel **admin** (Post Messages) and set channel id
3. For DM-only: set `TELEGRAM_CHANNEL_ID` to your numeric user id (works today)

## Deploy free with GitHub Actions (recommended)

The workflow [`.github/workflows/daily-gmp.yml`](.github/workflows/daily-gmp.yml) posts the digest every day at **9:00 AM IST** in the cloud — your Mac does not need to be awake.

1. Push this repo to GitHub
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHANNEL_ID`
   - `MIN_GAIN_PCT` (optional; defaults unused if empty — set `10`)
3. Repo → **Actions → Daily IPO GMP Digest → Run workflow** to test
4. Schedule runs automatically at 9:00 AM IST (`cron: 30 3 * * *` UTC)

`/gmp` replies still need the local listener (`python -m src.listen`) or a separate always-on host.

---

## Run automatically on Mac (optional /gmp + backup)

### Morning digest (9:00 AM)
A cron job is used:

```
0 9 * * * cd /Users/harshboricha/Desktop/TelegramBot && .venv/bin/python -m src.main >> logs/cron.log 2>&1
```

Your Mac timezone should be set to IST (or change the cron hour). The Mac must be awake at 9 AM.

### `/gmp` replies anytime
The listener must be running:

```bash
cd /Users/harshboricha/Desktop/TelegramBot
nohup .venv/bin/python -m src.listen >> logs/bot.out.log 2>> logs/bot.err.log &
```

It also posts the morning digest itself at 9:00 AM IST while running (in addition to cron as a backup).

Optional LaunchAgent: `./scripts/install_launchd.sh`  
If the project stays on Desktop, grant **Full Disk Access** to `.venv/bin/python` or LaunchAgent cannot read the folder.

## Manual commands

```bash
# Always-on bot (DM commands + morning schedule)
python -m src.listen

# One-off digest post
python -m src.main
```

In Telegram, message the bot:

- `/start` — help
- `/gmp` — profitable IPO digest now

## Filter rules

- Status: `Upcoming` or `Open` only
- Types: Mainboard and SME
- Gain: estimated listing % ≥ `MIN_GAIN_PCT` (default `10`)

## Project layout

- `src/listen.py` — always-on bot (`/gmp` + 9 AM schedule)
- `src/main.py` — one-off digest post
- `src/scraper.py` / `filter.py` / `formatter.py` / `digest.py`
- `launchd/com.telegrambot.ipogmp.plist` — macOS auto-start
