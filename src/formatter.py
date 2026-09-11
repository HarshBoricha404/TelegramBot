from __future__ import annotations

from datetime import date, datetime
from html import escape

from src.models import IpoRecord, SignalResult
from src.scraper import IST


def _format_day(day: date) -> str:
    try:
        return day.strftime("%-d %b %Y")
    except ValueError:
        return day.strftime("%d %b %Y").lstrip("0")


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    numeric = float(value)
    if numeric.is_integer():
        return f"₹{numeric:,.0f}"
    return f"₹{numeric:,.2f}".rstrip("0").rstrip(".")


def _date(value: date | None) -> str:
    return _format_day(value) if value else "—"


def _name(record: IpoRecord) -> str:
    display = record.name if len(record.name) <= 180 else record.name[:177].rstrip() + "…"
    name = escape(display)
    if record.url and len(record.url) <= 500 and record.url.startswith(("https://", "http://")):
        return f'<a href="{escape(record.url, quote=True)}">{name}</a>'
    return name


def _full_signal(result: SignalResult) -> str:
    ipo = result.ipo
    lines = [
        f"<b>{escape(result.label)} · {_name(ipo)} — {escape(ipo.ipo_type)} · {escape(ipo.status)}</b>",
        f"Signal <b>{result.score:.0f}/100</b> · Confidence: {escape(result.confidence)}",
        "",
        f"GMP <b>{_money(ipo.gmp_rs)} ({(ipo.gain_pct or 0):.2f}%)</b> · {escape(ipo.trend.title())}",
        f"Est. listing {_money(ipo.estimated_listing)} · Band {_money(ipo.price_low)}–{_money(ipo.price_high)}",
    ]
    if ipo.subscription:
        sub = ipo.subscription
        values = (
            f"Subscription {(sub.total or 0):g}x · "
            f"QIB {(sub.qib or 0):g}x · Retail {(sub.retail or 0):g}x"
        )
        lines.append(escape(values))
        if sub.updated_at:
            lines.append(f"Subscription updated {escape(sub.updated_at.strftime('%d %b, %H:%M IST'))}")
    if ipo.details:
        detail_parts: list[str] = []
        if ipo.details.issue_size:
            detail_parts.append(f"Total issue {escape(ipo.details.issue_size)}")
        if ipo.details.min_application is not None:
            detail_parts.append(f"Min. application {_money(ipo.details.min_application)}")
        if detail_parts:
            lines.append(" · ".join(detail_parts))
    lines.append(
        f"Open {_date(ipo.open_date)} → Close {_date(ipo.close_date)}"
        + (f" · List {_date(ipo.details.listing_date)}" if ipo.details and ipo.details.listing_date else "")
    )
    if ipo.updated_at:
        lines.append(f"GMP updated {escape(ipo.updated_at.strftime('%d %b, %H:%M IST'))}")

    if result.reasons:
        lines.extend(["", f"<b>Why:</b> {escape('; '.join(result.reasons[:4]))}."])
    if result.risk_flags:
        lines.append(f"<b>Caution:</b> {escape('; '.join(result.risk_flags[:3]))}.")
    if ipo.alternate_gmp_rs is not None and ipo.gmp_rs is not None:
        difference = abs(ipo.gmp_rs - ipo.alternate_gmp_rs)
        lines.append(f"Cross-check: alternate source differs by {_money(difference)}.")
    return "\n".join(lines)


def _compact_signal(index: int, result: SignalResult) -> str:
    ipo = result.ipo
    return (
        f"{index}. <b>{escape(result.label)}</b> · {_name(ipo)} — {escape(ipo.ipo_type)}\n"
        f"   Signal {result.score:.0f}/100 · GMP {_money(ipo.gmp_rs)} "
        f"({(ipo.gain_pct or 0):.1f}%) · {escape(ipo.status)}"
    )


def format_digest(
    signals: list[SignalResult],
    min_gain_pct: float,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(IST)
    actionable = bool(signals and signals[0].label == "CONSIDER")
    title = "Strongest IPO signal" if actionable else "No strong apply signal today"
    header = f"<b>{title} — {_format_day(now.date())}</b>"
    disclaimer = (
        "\n\n<i>GMP is unofficial, unregulated by SEBI, and not investment advice. "
        "Verify the RHP and exchange data before applying.</i>"
    )

    if not signals:
        return (
            f"{header}\n\nNo open or upcoming IPO has a positive parseable GMP today."
            f"\nThreshold: {min_gain_pct:g}%{disclaimer}"
        )

    sections = [header, _full_signal(signals[0])]
    alternatives = [_compact_signal(i, result) for i, result in enumerate(signals[1:], start=2)]
    if alternatives:
        sections.append("<b>Also watch</b>\n" + "\n\n".join(alternatives))
    sources = sorted({result.ipo.source for result in signals})
    footer = f"\nSources: {escape(', '.join(sources))}"
    message = "\n\n".join(sections) + footer + disclaimer

    # Leave headroom because Telegram counts some Unicode characters as two UTF-16 units.
    while len(message) > 3800 and alternatives:
        alternatives.pop()
        sections = [header, _full_signal(signals[0])]
        if alternatives:
            sections.append("<b>Also watch</b>\n" + "\n\n".join(alternatives))
        message = "\n\n".join(sections) + footer + disclaimer
    if len(message) > 3800:
        message = (
            f"{header}\n\n{_compact_signal(1, signals[0])}"
            f"\n\nThreshold: {min_gain_pct:g}%{footer}{disclaimer}"
        )
    return message
