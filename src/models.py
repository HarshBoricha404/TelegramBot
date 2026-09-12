from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class SubscriptionData:
    qib: float | None = None
    nii: float | None = None
    retail: float | None = None
    total: float | None = None
    updated_at: datetime | None = None


@dataclass
class GmpCalibration:
    """How recent IPOs actually listed versus their last GMP."""

    sample_size: int = 0
    median_miss_pp: float | None = None
    band_miss: dict[str, float] = field(default_factory=dict)
    band_n: dict[str, int] = field(default_factory=dict)

    def miss_for_gain(self, gain: float) -> float | None:
        key = _gmp_band(gain)
        if self.band_n.get(key, 0) >= 20:
            return self.band_miss.get(key)
        if self.sample_size >= 30:
            return self.median_miss_pp
        return None


@dataclass
class IpoDetails:
    issue_size: str | None = None
    issue_size_cr: float | None = None
    lot_size: int | None = None
    min_application: float | None = None
    listing_date: date | None = None
    listing_venue: str | None = None
    latest_revenue: float | None = None
    previous_revenue: float | None = None
    latest_pat: float | None = None
    previous_pat: float | None = None
    fresh_issue: str | None = None
    fresh_issue_cr: float | None = None
    ofs: str | None = None
    ofs_shares: float | None = None
    ofs_cr: float | None = None
    issue_mix: str | None = None
    eps: float | None = None
    nav: float | None = None
    pe_ratio: float | None = None
    implied_pe: float | None = None
    pb_ratio: float | None = None
    pat_margin: float | None = None
    ebitda_margin: float | None = None
    roe: float | None = None
    roce: float | None = None
    debt_to_equity: float | None = None
    peer_median_pe: float | None = None
    peer_count: int = 0
    promoter_pre_pct: float | None = None
    promoter_post_pct: float | None = None
    objects_flags: list[str] = field(default_factory=list)
    objects_debt_share: float | None = None


@dataclass
class IpoRecord:
    name: str
    ipo_type: str
    status: str
    source: str
    source_url: str
    gmp_rs: float | None = None
    gain_pct: float | None = None
    trend: str = "unknown"
    price_low: float | None = None
    price_high: float | None = None
    estimated_listing: float | None = None
    open_date: date | None = None
    close_date: date | None = None
    date_text: str = ""
    updated_at: datetime | None = None
    fetched_at: datetime | None = None
    url: str | None = None
    subscription: SubscriptionData | None = None
    details: IpoDetails | None = None
    alternate_gmp_rs: float | None = None
    gmp_calibration: GmpCalibration | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SignalResult:
    ipo: IpoRecord
    score: float
    label: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


def _gmp_band(gain: float) -> str:
    if gain <= 0:
        return "<=0"
    if gain < 12:
        return "0-12"
    if gain <= 40:
        return "12-40"
    if gain <= 60:
        return "40-60"
    if gain < 80:
        return "60-80"
    return ">=80"


def finalize_ipo_record(record: IpoRecord) -> None:
    """Fill derived valuation and issue-mix fields once price is known."""
    details = record.details
    if details is None:
        return
    if details.ofs_cr is None and details.ofs_shares and record.price_high:
        details.ofs_cr = details.ofs_shares * record.price_high / 10_000_000
    if details.implied_pe is None and details.eps and record.price_high and details.eps > 0:
        details.implied_pe = round(record.price_high / details.eps, 2)
    elif details.implied_pe is None and details.pe_ratio:
        details.implied_pe = details.pe_ratio
    if details.pb_ratio is None and details.nav and record.price_high and details.nav > 0:
        details.pb_ratio = round(record.price_high / details.nav, 2)
    refined = _refine_issue_mix(details)
    if refined:
        details.issue_mix = refined


def _refine_issue_mix(details: IpoDetails) -> str | None:
    fresh = details.fresh_issue_cr
    ofs = details.ofs_cr
    if fresh is not None and ofs is not None and (fresh + ofs) > 0:
        weight = ofs / (fresh + ofs)
        if weight >= 0.6:
            return "ofs"
        if weight <= 0.3:
            return "fresh"
        return "mixed"
    if fresh is not None and fresh > 0 and not ofs:
        return "fresh"
    if ofs is not None and ofs > 0 and not fresh:
        return "ofs"
    return details.issue_mix
