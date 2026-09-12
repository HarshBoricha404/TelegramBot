from __future__ import annotations

import math
from datetime import date, datetime

from src.models import IpoRecord, SignalResult
from src.scraper import IST, CLOSE_WITHIN_DAYS, closes_within_days

CONSIDER_SCORE = 60.0


def _age_hours(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    return (now - value.astimezone(IST)).total_seconds() / 3600


def _is_fresh(value: datetime | None, now: datetime) -> bool:
    age = _age_hours(value, now)
    return age is not None and -2 <= age <= 24


def _is_open(record: IpoRecord, today: date) -> bool:
    return (
        record.status == "Open"
        and record.open_date is not None
        and record.close_date is not None
        and record.open_date <= today <= record.close_date
        and "status/date mismatch" not in record.warnings
    )


def _scaled_demand(value: float | None, maximum: float, multiplier: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return min(maximum, math.log10(1 + value) * multiplier)


def score_ipo(
    record: IpoRecord,
    min_gain_pct: float,
    *,
    now: datetime | None = None,
) -> SignalResult:
    now = now or datetime.now(IST)
    today = now.date()
    reasons: list[str] = []
    risk_flags: list[str] = []

    gain = record.gain_pct or 0.0
    score = min(40.0, max(0.0, gain))
    if gain >= 20:
        reasons.append(f"strong {gain:.1f}% GMP signal")
    elif gain >= min_gain_pct:
        reasons.append(f"{gain:.1f}% GMP clears the threshold")

    gmp_fresh = _is_fresh(record.updated_at, now)
    if gmp_fresh:
        score += 8
        reasons.append("fresh IPO Watch update")
    elif record.source == "IPO Premium" and record.fetched_at:
        score += 4
        risk_flags.append("source has no row-level update timestamp")
    else:
        risk_flags.append("GMP data is stale or undated")

    if record.alternate_gmp_rs is not None and record.price_high:
        delta_pct = abs((record.gmp_rs or 0) - record.alternate_gmp_rs) / record.price_high * 100
        if delta_pct <= 3:
            score += 4
            reasons.append("alternate source broadly agrees")
        elif delta_pct > 5:
            score -= 4
            risk_flags.append(f"sources differ by {delta_pct:.1f} percentage points")

    if record.trend == "rising":
        score += 8
        reasons.append("GMP trend is rising")
    elif record.trend == "falling":
        score -= 8
        risk_flags.append("GMP trend is falling")

    if record.ipo_type == "Mainboard":
        score += 15
        reasons.append("mainboard liquidity preference")

    subscription = record.subscription
    subscription_fresh = bool(subscription and _is_fresh(subscription.updated_at, now))
    before_opening_bids = record.open_date == today and now.hour < 10
    if subscription and subscription_fresh and not before_opening_bids:
        demand_score = (
            _scaled_demand(subscription.qib, 10, 5)
            + _scaled_demand(subscription.total, 10, 5)
            + _scaled_demand(subscription.retail, 5, 3)
        )
        score += demand_score
        if demand_score >= 8:
            reasons.append("healthy subscription demand")
    elif not before_opening_bids:
        risk_flags.append("fresh subscription data unavailable")

    details = record.details
    if details:
        if details.latest_pat is not None and details.latest_pat <= 0:
            score -= 15
            risk_flags.append("latest annual PAT is non-positive")
        elif (
            details.latest_pat is not None
            and details.previous_pat is not None
            and details.previous_pat > 0
            and details.latest_pat < details.previous_pat * 0.8
        ):
            score -= 8
            risk_flags.append("latest annual PAT fell more than 20%")

    score = round(max(0.0, min(100.0, score)), 1)
    open_today = _is_open(record, today)
    closing_soon = closes_within_days(record, today)
    critical_risk = any(
        flag in risk_flags
        for flag in (
            "GMP data is stale or undated",
            "latest annual PAT is non-positive",
        )
    )
    actionable = (
        open_today
        and closing_soon
        and gmp_fresh
        and record.price_high is not None
        and (record.gmp_rs or 0) > 0
        and gain >= min_gain_pct
        and not critical_risk
    )

    if actionable and score >= CONSIDER_SCORE:
        label = "CONSIDER"
    elif gain <= 0:
        label = "LOW SIGNAL"
    else:
        label = "WATCH"

    disagreement = any("sources differ" in flag for flag in risk_flags)
    if (
        gmp_fresh
        and subscription_fresh
        and record.alternate_gmp_rs is not None
        and not disagreement
        and not record.warnings
    ):
        confidence = "High"
    elif gmp_fresh and not disagreement:
        confidence = "Medium"
    else:
        confidence = "Low"

    if open_today and closing_soon and record.close_date is not None:
        remaining = (record.close_date - today).days
        if remaining == 0:
            reasons.append("closes today")
        else:
            reasons.append(f"closes in {remaining} day(s)")
    elif open_today and not closing_soon:
        reasons.append(f"open, but close is more than {CLOSE_WITHIN_DAYS} days away")
    elif record.status == "Upcoming":
        reasons.append("upcoming; not open for applications")

    return SignalResult(
        ipo=record,
        score=score,
        label=label,
        confidence=confidence,
        reasons=reasons,
        risk_flags=risk_flags + record.warnings,
    )


def recommend_ipos(
    records: list[IpoRecord],
    min_gain_pct: float,
    *,
    now: datetime | None = None,
    limit: int = 3,
) -> list[SignalResult]:
    now = now or datetime.now(IST)
    results = [score_ipo(record, min_gain_pct, now=now) for record in records]
    relevant = [
        result
        for result in results
        if result.ipo.status == "Open"
        and _is_open(result.ipo, now.date())
        and closes_within_days(result.ipo, now.date())
        and (result.ipo.gain_pct or 0) > 0
    ]
    relevant.sort(key=lambda result: result.score, reverse=True)

    consider = [result for result in relevant if result.label == "CONSIDER"]
    mainboard = [result for result in consider if result.ipo.ipo_type == "Mainboard"]
    sme = [result for result in consider if result.ipo.ipo_type == "SME"]
    selected: SignalResult | None = None
    if mainboard and sme:
        selected = sme[0] if sme[0].score >= mainboard[0].score + 15 else mainboard[0]
    elif mainboard:
        selected = mainboard[0]
    elif sme:
        selected = sme[0]

    ordered: list[SignalResult] = []
    if selected:
        ordered.append(selected)
    ordered.extend(result for result in relevant if result is not selected)
    return ordered[:limit]
