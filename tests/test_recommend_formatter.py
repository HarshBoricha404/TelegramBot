from __future__ import annotations

from datetime import date, datetime, timedelta

from src.formatter import format_digest
from src.models import IpoDetails, IpoRecord, SubscriptionData
from src.recommend import recommend_ipos, score_ipo
from src.scraper import IST

NOW = datetime(2026, 9, 11, 9, 0, tzinfo=IST)


def record(
    name: str,
    *,
    ipo_type: str = "Mainboard",
    status: str = "Open",
    gain: float = 25,
    trend: str = "rising",
    updated_at: datetime | None = NOW - timedelta(hours=1),
    open_date: date = date(2026, 9, 9),
    close_date: date = date(2026, 9, 11),
) -> IpoRecord:
    return IpoRecord(
        name=name,
        ipo_type=ipo_type,
        status=status,
        source="IPO Watch",
        source_url="https://ipowatch.in/gmp/",
        gmp_rs=gain,
        gain_pct=gain,
        trend=trend,
        price_low=95,
        price_high=100,
        estimated_listing=100 + gain,
        open_date=open_date,
        close_date=close_date,
        updated_at=updated_at,
        fetched_at=NOW,
        url="https://ipowatch.in/example/",
        alternate_gmp_rs=gain,
        subscription=SubscriptionData(
            qib=5,
            nii=10,
            retail=8,
            total=7,
            updated_at=NOW - timedelta(hours=1),
        ),
        details=IpoDetails(latest_pat=20, previous_pat=15),
    )


def test_fresh_open_mainboard_with_demand_is_consider() -> None:
    result = score_ipo(record("Strong Mainboard"), 10, now=NOW)

    assert result.label == "CONSIDER"
    assert result.confidence == "High"
    assert result.score >= 60


def test_upcoming_and_stale_rows_are_never_actionable() -> None:
    upcoming = score_ipo(
        record(
            "Upcoming",
            status="Upcoming",
            open_date=date(2026, 9, 15),
            close_date=date(2026, 9, 17),
        ),
        10,
        now=NOW,
    )
    stale = score_ipo(
        record("Stale", updated_at=NOW - timedelta(hours=25)),
        10,
        now=NOW,
    )

    assert upcoming.label == "WATCH"
    assert stale.label == "WATCH"
    assert stale.confidence == "Low"


def test_opening_day_before_bidding_does_not_add_subscription_bonus() -> None:
    opening = record(
        "Opening",
        open_date=NOW.date(),
        close_date=date(2026, 9, 15),
    )
    without_subscription = record(
        "Opening without subscription",
        open_date=NOW.date(),
        close_date=date(2026, 9, 15),
    )
    without_subscription.subscription = None

    with_score = score_ipo(opening, 10, now=NOW).score
    without_score = score_ipo(without_subscription, 10, now=NOW).score
    assert with_score == without_score


def test_recent_loss_prevents_consider_label() -> None:
    loss = record("Loss Making")
    loss.details = IpoDetails(latest_pat=-2, previous_pat=10)
    result = score_ipo(loss, 10, now=NOW)

    assert result.label == "WATCH"
    assert "latest annual PAT is non-positive" in result.risk_flags


def test_mainboard_preference_beats_sme_unless_sme_is_clearly_stronger() -> None:
    mainboard = record("Mainboard", gain=25)
    close_sme = record("Close SME", ipo_type="SME", gain=35)
    weak_mainboard = record("Weak Mainboard", gain=15, trend="falling")
    weak_mainboard.subscription = SubscriptionData(
        qib=0.1,
        nii=0.2,
        retail=0.2,
        total=0.2,
        updated_at=NOW - timedelta(hours=1),
    )
    strong_sme = record("Strong SME", ipo_type="SME", gain=70)

    first = recommend_ipos([mainboard, close_sme], 10, now=NOW)[0]
    second = recommend_ipos([weak_mainboard, strong_sme], 10, now=NOW)[0]

    assert first.ipo.name == "Mainboard"
    assert second.ipo.name == "Strong SME"


def test_nonpositive_gmp_is_low_signal() -> None:
    weak = record("Weak", gain=0, trend="stable")
    weak.gmp_rs = 0
    assert score_ipo(weak, 10, now=NOW).label == "LOW SIGNAL"


def test_formatter_escapes_html_and_stays_under_telegram_limit() -> None:
    unsafe = record("<script>alert(1)</script>" + "x" * 5000)
    unsafe.url = "javascript:alert(1)"
    signal = score_ipo(unsafe, 10, now=NOW)
    message = format_digest([signal], 10, now=NOW)

    assert "<script>" not in message
    assert "&lt;script&gt;" in message
    assert "javascript:" not in message
    assert len(message) < 4096


def test_empty_result_formats_explicit_no_signal_message() -> None:
    message = format_digest([], 10, now=NOW)
    assert "No strong apply signal today" in message
    assert "not investment advice" in message
