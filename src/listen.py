from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import load_config, load_daily_post_hour, load_timezone
from src.digest import build_digest
from src.scraper import ScrapeError
from src.telegram_client import TelegramError, get_me, get_updates, send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "IPO GMP bot is online.\n\n"
    "Commands:\n"
    "/start — check that the bot replies\n"
    "/gmp — scrape IPO Watch and send profitable IPOs here\n"
    "/help — show this message\n\n"
    "A digest is also posted automatically every morning at 9:00 AM IST."
)


def _normalize_command(text: str) -> str:
    command = text.strip().split()[0].lower() if text.strip() else ""
    if "@" in command:
        command = command.split("@", 1)[0]
    return command


def _handle_message(bot_token: str, chat_id: str, text: str, min_gain: float) -> None:
    command = _normalize_command(text)

    if command in {"/start", "/help"}:
        send_message(bot_token, chat_id, HELP_TEXT)
        return

    if command == "/gmp":
        send_message(bot_token, chat_id, "Fetching IPO GMP…")
        try:
            send_message(bot_token, chat_id, build_digest(min_gain))
        except (ScrapeError, TelegramError) as exc:
            send_message(bot_token, chat_id, f"Failed: {exc}")
        return

    send_message(
        bot_token,
        chat_id,
        "Send /start to test, or /gmp for today's profitable IPOs.",
    )


def _maybe_daily_post(
    bot_token: str,
    destination_id: str,
    min_gain: float,
    *,
    tz: ZoneInfo,
    hour: int,
    last_posted_on: date | None,
) -> date | None:
    now = datetime.now(tz)
    if now.hour != hour:
        return last_posted_on
    if last_posted_on == now.date():
        return last_posted_on

    logger.info("Running scheduled 9 AM digest → %s", destination_id)
    try:
        message = "🌅 Morning IPO GMP digest\n\n" + build_digest(min_gain)
        send_message(bot_token, destination_id, message)
        logger.info("Daily digest posted")
        return now.date()
    except (ScrapeError, TelegramError) as exc:
        logger.error("Daily digest failed: %s", exc)
        # Retry later in the same hour window
        return last_posted_on


def run() -> int:
    try:
        config = load_config()
        tz = ZoneInfo(load_timezone())
        hour = load_daily_post_hour()
        me = get_me(config.telegram_bot_token)
    except (ValueError, TelegramError) as exc:
        logger.error("%s", exc)
        return 1

    token = config.telegram_bot_token
    destination = config.telegram_channel_id
    min_gain = config.min_gain_pct
    username = me.get("username", "?")

    logger.info("Bot ok: @%s (id=%s)", username, me.get("id"))
    logger.info("Daily digest → %s at %02d:00 %s", destination, hour, tz.key)
    logger.info("Open https://t.me/%s and send /gmp anytime", username)
    logger.info("Listening (Ctrl+C to stop)…")

    offset: int | None = None
    last_posted_on: date | None = None

    try:
        while True:
            last_posted_on = _maybe_daily_post(
                token,
                destination,
                min_gain,
                tz=tz,
                hour=hour,
                last_posted_on=last_posted_on,
            )
            try:
                updates = get_updates(token, offset=offset, timeout=25)
            except TelegramError as exc:
                logger.error("getUpdates failed: %s", exc)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("channel_post")
                if not message:
                    continue
                chat = message.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = message.get("text") or ""
                if not chat_id or not text:
                    continue
                # Ignore channel posts so the bot doesn't reply to its own digest
                if chat.get("type") == "channel":
                    continue
                logger.info("Message from %s: %r", chat_id, text[:80])
                try:
                    _handle_message(token, chat_id, text, min_gain)
                except TelegramError as exc:
                    logger.error("Reply failed: %s", exc)
    except KeyboardInterrupt:
        logger.info("Stopped.")
        return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
