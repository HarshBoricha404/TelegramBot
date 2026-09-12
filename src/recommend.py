from __future__ import annotations

import math
from datetime import date, datetime

from src.models import GmpCalibration, IpoDetails, IpoRecord, SignalResult, finalize_ipo_record
from src.scraper import CLOSE_WITHIN_DAYS, IST, closes_within_days

CONSIDER_SCORE = 60.0
SME_LEAD = 20.0


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


def _scaled(value: float | None, maximum: float, multiplier: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return min(maximum, math.log10(1 + value) * multiplier)


def _gmp_quality(
    gain: float,
    ipo_type: str,
    calibration: GmpCalibration | None,
) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    risks: list[str] = []
    if gain <= 0:
        return 0.0, reasons, risks
    if 12 <= gain <= 40:
        points = 12 + (gain - 12) / 28 * 8
        reasons.append(f"GMP {gain:.1f}% sits in a useful listing-gain band")
    elif gain < 12:
        points = gain
        reasons.append(f"{gain:.1f}% GMP is a modest premium")
    elif gain <= 60:
        points = 18 - (gain - 40) / 20 * 6
        risks.append("GMP is rich versus a typical listing-gain band")
    else:
        points = 8.0
        risks.append("GMP looks speculative; not a listing forecast")
    if ipo_type == "SME" and gain >= 80:
        points = min(points, 6.0)
        risks.append("extreme SME GMP often fades on listing")
    miss = calibration.miss_for_gain(gain) if calibration is not None else None
    if miss is not None and miss <= -2:
        points *= 0.85
        risks.append("recent IPOs with similar GMP often listed below the grey-market price")
    return points, reasons, risks


def _demand_quality(
    subscription,
    *,
    usable: bool,
    days_to_close: int | None,
) -> tuple[float, list[str], list[str]]:
    if not usable:
        return 0.0, [], []
    if subscription is None:
        return 0.0, [], ["fresh subscription data unavailable"]

    qib = subscription.qib or 0.0
    nii = subscription.nii or 0.0
    retail = subscription.retail or 0.0
    total = subscription.total
    total_value = total or 0.0
    points = (
        _scaled(qib, 16, 9)
        + _scaled(nii, 4, 2)
        + _scaled(retail, 3, 1.5)
        + _scaled(total_value, 4, 2)
    )
    reasons: list[str] = []
    risks: list[str] = []
    last_day = days_to_close == 0

    if total is not None and total < 1:
        if last_day:
            points -= 10
            risks.append("issue is undersubscribed overall")
        else:
            points -= 3
            risks.append("subscription is still thin")
    elif qib < 1:
        if nii >= 2 or retail >= 2 or total_value >= 2:
            points -= 8
            risks.append("book looks retail/HNI-led with weak QIB")
        else:
            points -= 6
            risks.append("institutional demand is weak")
    else:
        reasons.append(f"QIB demand {qib:g}x")
        reasons.append("institutional demand supports the book")

    if total_value >= 50:
        points -= 5
        risks.append("heavy oversubscription; allotment is a lottery")
    return max(0.0, points), reasons, risks


def _financial_quality(details: IpoDetails | None) -> tuple[float, list[str], list[str]]:
    if details is None:
        return 0.0, [], []
    points = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    if details.latest_pat is not None and details.latest_pat <= 0:
        return -15.0, reasons, ["latest annual PAT is non-positive"]

    grew = (
        details.latest_pat is not None
        and details.previous_pat is not None
        and details.previous_pat > 0
        and details.latest_pat > details.previous_pat
    )
    spike = (
        details.latest_pat is not None
        and details.previous_pat is not None
        and details.previous_pat > 0
        and details.latest_pat > details.previous_pat * 2.5
    )
    if spike:
        points -= 6
        risks.append("latest annual PAT jumped too sharply to treat as a trend")
    elif grew:
        points += 6
        reasons.append("annual PAT is growing")
    elif (
        details.latest_pat is not None
        and details.previous_pat is not None
        and details.previous_pat > 0
        and details.latest_pat < details.previous_pat * 0.8
    ):
        points -= 8
        risks.append("latest annual PAT fell more than 20%")

    if (
        details.latest_revenue is not None
        and details.previous_revenue is not None
        and details.previous_revenue > 0
        and details.latest_revenue > details.previous_revenue
    ):
        points += 4
        reasons.append("revenue is growing")
    if details.pat_margin is not None:
        if details.pat_margin >= 10:
            points += 3
            reasons.append("PAT margin is healthy")
        elif details.pat_margin < 3:
            points -= 3
            risks.append("PAT margin is thin")
    if details.debt_to_equity is not None and details.debt_to_equity >= 1.5:
        points -= 4
        risks.append("balance sheet is leveraged")
    if details.roe is not None and details.roe >= 60:
        points -= 3
        risks.append("reported ROE looks unusually high")
    return points, reasons, risks


def _valuation_quality(record: IpoRecord) -> tuple[float, list[str], list[str]]:
    details = record.details
    if details is None:
        return 0.0, [], []
    points = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    implied = details.implied_pe
    peers = details.peer_median_pe
    if implied and peers and peers > 0:
        ratio = implied / peers
        if ratio >= 1.5:
            points -= 10
            risks.append("issue looks expensive versus listed peers")
        elif ratio >= 1.2:
            points -= 5
            risks.append("issue is priced above listed peers")
        elif ratio <= 0.75:
            points += 5
            reasons.append("issue looks cheaper than listed peers")
    if details.pb_ratio is not None and details.pb_ratio >= 8:
        points -= 5
        risks.append("price is high versus book value")
    return points, reasons, risks


def _structure_quality(record: IpoRecord) -> tuple[float, list[str], list[str]]:
    details = record.details
    if details is None:
        return 0.0, [], []
    points = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    if details.issue_mix == "fresh":
        points += 3
        reasons.append("issue is primarily fresh capital")
    elif details.issue_mix == "ofs":
        points -= 6
        risks.append("issue is mostly OFS / existing-shareholder exit")
    elif details.issue_mix == "mixed":
        risks.append("mix of fresh issue and OFS")
    if record.ipo_type == "SME" and (details.min_application or 0) >= 100_000:
        points -= 4
        risks.append("SME lot is expensive for retail")
    if details.issue_size_cr is not None:
        if details.issue_size_cr >= 500:
            points += 3
            reasons.append("issue size is large enough for post-listing liquidity")
        elif details.issue_size_cr < 40 and record.ipo_type == "SME":
            points -= 3
            risks.append("SME issue is small and may be illiquid")
    if details.objects_debt_share is not None and details.objects_debt_share >= 0.5:
        points -= 6
        risks.append("issue proceeds are mainly to repay debt")
    elif "land" in details.objects_flags:
        points -= 4
        risks.append("proceeds include land acquisition")
    elif "capex" in details.objects_flags:
        points += 2
        reasons.append("proceeds include growth capex")
    if details.promoter_pre_pct is not None and details.promoter_post_pct is not None:
        drop = details.promoter_pre_pct - details.promoter_post_pct
        if details.promoter_post_pct < 50:
            points -= 5
            risks.append("promoters will own less than 50% after the IPO")
        elif drop >= 20 and details.promoter_post_pct < 70:
            points -= 4
            risks.append("promoter holding drops sharply after the IPO")
    return points, reasons, risks


def score_ipo(
    record: IpoRecord,
    min_gain_pct: float,
    *,
    now: datetime | None = None,
) -> SignalResult:
    now = now or datetime.now(IST)
    today = now.date()
    finalize_ipo_record(record)
    reasons: list[str] = []
    risk_flags: list[str] = []
    score = 0.0

    gain = record.gain_pct or 0.0
    gmp_points, gmp_reasons, gmp_risks = _gmp_quality(gain, record.ipo_type, record.gmp_calibration)
    score += gmp_points
    reasons.extend(gmp_reasons)
    risk_flags.extend(gmp_risks)

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

    before_opening_bids = record.open_date == today and now.hour < 10
    subscription = record.subscription
    subscription_fresh = bool(subscription and _is_fresh(subscription.updated_at, now))
    days_to_close = (record.close_date - today).days if record.close_date else None
    demand_points, demand_reasons, demand_risks = _demand_quality(
        subscription,
        usable=subscription_fresh and not before_opening_bids,
        days_to_close=days_to_close,
    )
    score += demand_points
    reasons.extend(demand_reasons)
    risk_flags.extend(demand_risks)
    if not before_opening_bids and not subscription_fresh:
        risk_flags.append("fresh subscription data unavailable")

    fin_points, fin_reasons, fin_risks = _financial_quality(record.details)
    score += fin_points
    reasons.extend(fin_reasons)
    risk_flags.extend(fin_risks)

    val_points, val_reasons, val_risks = _valuation_quality(record)
    score += val_points
    reasons.extend(val_reasons)
    risk_flags.extend(val_risks)

    struct_points, struct_reasons, struct_risks = _structure_quality(record)
    score += struct_points
    reasons.extend(struct_reasons)
    risk_flags.extend(struct_risks)

    score = round(max(0.0, min(100.0, score)), 1)
    open_today = _is_open(record, today)
    closing_soon = closes_within_days(record, today)
    critical_risk = any(
        flag in risk_flags
        for flag in (
            "GMP data is stale or undated",
            "latest annual PAT is non-positive",
            "issue looks expensive versus listed peers",
            "issue is undersubscribed overall",
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
        and not any("weak QIB" in flag or "undersubscribed" in flag for flag in risk_flags)
        and not any("expensive versus listed peers" in flag for flag in risk_flags)
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
        selected = sme[0] if sme[0].score >= mainboard[0].score + SME_LEAD else mainboard[0]
    elif mainboard:
        selected = mainboard[0]
    elif sme:
        selected = sme[0]

    ordered: list[SignalResult] = []
    if selected:
        ordered.append(selected)
    ordered.extend(result for result in relevant if result is not selected)
    return ordered[:limit]
