from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_channel_id: str
    min_gain_pct: float
    gmp_url: str = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"


def load_min_gain_pct() -> float:
    min_gain_raw = os.getenv("MIN_GAIN_PCT", "10").strip()
    try:
        return float(min_gain_raw)
    except ValueError as exc:
        raise ValueError(f"MIN_GAIN_PCT must be a number, got {min_gain_raw!r}") from exc


def load_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required (set it in .env)")
    return token


def load_timezone() -> str:
    return os.getenv("TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"


def load_daily_post_hour() -> int:
    raw = os.getenv("DAILY_POST_HOUR", "9").strip()
    try:
        hour = int(raw)
    except ValueError as exc:
        raise ValueError(f"DAILY_POST_HOUR must be 0-23, got {raw!r}") from exc
    if hour < 0 or hour > 23:
        raise ValueError(f"DAILY_POST_HOUR must be 0-23, got {hour}")
    return hour


def load_config() -> Config:
    token = load_bot_token()
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel or channel.startswith("@your_channel"):
        raise ValueError(
            "TELEGRAM_CHANNEL_ID is required (set a real @channel or -100... id in .env)"
        )

    return Config(
        telegram_bot_token=token,
        telegram_channel_id=channel,
        min_gain_pct=load_min_gain_pct(),
    )
