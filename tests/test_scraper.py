from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from src.scraper import (
    IST,
    ScrapeError,
    normalize_name,
    parse_date_range,
    parse_detail_html,
    parse_ipowatch_gmp_html,
    parse_premium_html,
    parse_subscription_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_new_ipowatch_layout_parses_two_sections_and_normalizes_values() -> None:
    now = datetime(2026, 9, 11, 13, 0, tzinfo=IST)
    records = parse_ipowatch_gmp_html(fixture("gmp_new.html"), now=now)

    assert len(records) == 3
    mainboard, unknown, sme = records
    assert (mainboard.name, mainboard.ipo_type, mainboard.status) == (
        "Rentomojo",
        "Mainboard",
        "Open",
    )
    assert mainboard.url == "https://ipowatch.in/rentomojo-ipo/"
    assert (mainboard.price_low, mainboard.price_high) == (384.0, 404.0)
    assert (mainboard.gmp_rs, mainboard.gain_pct, mainboard.estimated_listing) == (
        138.0,
        34.16,
        542.0,
    )
    assert mainboard.trend == "rising"
    assert unknown.price_high is None
    assert unknown.gmp_rs == 0
    assert sme.ipo_type == "SME"
    assert sme.gmp_rs == -2.5
    assert sme.gain_pct == -2.5
    assert (sme.open_date, sme.close_date) == (date(2026, 8, 31), date(2026, 9, 2))


def test_old_single_table_layout_uses_type_column_and_year_boundary() -> None:
    now = datetime(2027, 1, 1, 10, 0, tzinfo=IST)
    record = parse_ipowatch_gmp_html(fixture("gmp_old.html"), now=now)[0]

    assert record.ipo_type == "SME"
    assert record.status == "Open"
    assert (record.open_date, record.close_date) == (date(2026, 12, 30), date(2027, 1, 2))
    assert record.updated_at == datetime(2027, 1, 1, 9, 0, tzinfo=IST)


def test_date_parser_rejects_invalid_or_ambiguous_ranges() -> None:
    assert parse_date_range("TBA", date(2026, 9, 11)) == (None, None)
    assert parse_date_range("31-31 February", date(2026, 2, 1)) == (None, None)


def test_missing_gmp_table_fails_closed() -> None:
    with pytest.raises(ScrapeError):
        parse_ipowatch_gmp_html("<html><body><table><tr><td>No data</td></tr></table></body></html>")


def test_subscription_parser_uses_page_date_for_time_only_timestamp() -> None:
    now = datetime(2026, 9, 11, 13, 0, tzinfo=IST)
    values = parse_subscription_html(fixture("subscription.html"), now=now)
    item = values[normalize_name("Rentomojo")]

    assert (item.qib, item.nii, item.retail, item.total) == (1.17, 15.95, 10.85, 9.18)
    assert item.updated_at == datetime(2026, 9, 11, 12, 15, tzinfo=IST)


def test_premium_fallback_derives_status_and_gain() -> None:
    now = datetime(2026, 9, 11, 9, 0, tzinfo=IST)
    record = parse_premium_html(fixture("premium.html"), now=now)[0]

    assert record.status == "Open"
    assert record.ipo_type == "Mainboard"
    assert record.price_high == 404
    assert record.gain_pct == 32.92
    assert record.estimated_listing == 537


def test_detail_parser_ignores_unrelated_content_before_matching_heading() -> None:
    details = parse_detail_html(
        fixture("detail_contaminated.html"),
        "Rentomojo",
        date(2026, 9, 11),
    )

    assert details.issue_size == "Approx ₹1,255.57 Crores"
    assert details.issue_size != "₹999 Crores"
    assert details.lot_size == 37
    assert details.min_application == 14948
    assert details.listing_date == date(2026, 9, 17)
    assert (details.previous_pat, details.latest_pat) == (43.11, 104.30)


def test_detail_parser_rejects_identity_mismatch() -> None:
    with pytest.raises(ScrapeError):
        parse_detail_html(fixture("detail_contaminated.html"), "Other Company", date(2026, 9, 11))
