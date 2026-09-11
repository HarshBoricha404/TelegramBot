from __future__ import annotations

import logging
import sys

from src.config import load_config
from src.digest import build_digest
from src.scraper import ScrapeError
from src.telegram_client import TelegramError, send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def run() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    try:
        message = build_digest(config.min_gain_pct)
        send_message(config.telegram_bot_token, config.telegram_channel_id, message)
    except ScrapeError as exc:
        logger.error("%s", exc)
        try:
            send_message(
                config.telegram_bot_token,
                config.telegram_channel_id,
                "IPO signal update failed: every market-data source was unavailable or invalid. "
                "Check the GitHub Actions run.",
            )
        except TelegramError:
            logger.error("Could not deliver the operational alert to Telegram")
        return 1
    except TelegramError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("Posted digest to %s", config.telegram_channel_id)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
