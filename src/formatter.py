from __future__ import annotations

from datetime import date

from src.scraper import IpoGmpRow


def _format_day(day: date) -> str:
    try:
        return day.strftime("%-d %b %Y")
    except ValueError:
        return day.strftime("%d %b %Y").lstrip("0")


def format_digest(
    ipos: list[IpoGmpRow],
    min_gain_pct: float,
    today: date | None = None,
) -> str:
    day = today or date.today()
    lines = [
        f"IPO alerts — {_format_day(day)}",
        f"Profitable Upcoming/Open (≥{min_gain_pct:g}% est. gain)",
        "",
    ]

    if not ipos:
        lines.append("No profitable IPOs today.")
        lines.append("")
        lines.append("GMP is unofficial and not investment advice.")
        return "\n".join(lines)

    for i, ipo in enumerate(ipos, start=1):
        lines.append(f"{i}. {ipo.name} — {ipo.ipo_type} — {ipo.status}")
        lines.append(
            f"   GMP {ipo.gmp} | Band {ipo.price_band} | Est. {ipo.est_listing}"
        )
        lines.append(f"   Dates: {ipo.date}")
        if ipo.url:
            lines.append(f"   {ipo.url}")
        lines.append("")

    lines.append("GMP is unofficial and not investment advice.")
    return "\n".join(lines)
