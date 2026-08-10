from __future__ import annotations

from src.filter import filter_profitable
from src.formatter import format_digest
from src.scraper import scrape_ipo_gmp


def build_digest(min_gain_pct: float) -> str:
    rows = scrape_ipo_gmp()
    profitable = filter_profitable(rows, min_gain_pct=min_gain_pct)
    message = format_digest(profitable, min_gain_pct=min_gain_pct)
    if len(message) > 4000:
        message = message[:3950].rstrip() + "\n\n… truncated."
    return message
