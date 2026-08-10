from __future__ import annotations

from src.scraper import IpoGmpRow

_ACTIVE_STATUSES = frozenset({"upcoming", "open"})


def filter_profitable(
    rows: list[IpoGmpRow],
    min_gain_pct: float = 10.0,
) -> list[IpoGmpRow]:
    """Keep Upcoming/Open IPOs with estimated listing gain >= min_gain_pct."""
    filtered = [
        row
        for row in rows
        if row.status.strip().lower() in _ACTIVE_STATUSES and row.gain_pct >= min_gain_pct
    ]
    return sorted(filtered, key=lambda r: r.gain_pct, reverse=True)
