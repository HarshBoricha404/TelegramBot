from __future__ import annotations

from datetime import datetime

from src.formatter import format_digest
from src.recommend import recommend_ipos
from src.scraper import IST, scrape_market_data


def build_digest(min_gain_pct: float, *, now: datetime | None = None) -> str:
    now = now or datetime.now(IST)
    records = scrape_market_data(now=now)
    signals = recommend_ipos(records, min_gain_pct=min_gain_pct, now=now)
    return format_digest(signals, min_gain_pct=min_gain_pct, now=now)
