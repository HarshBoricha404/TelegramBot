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
class IpoDetails:
    issue_size: str | None = None
    lot_size: int | None = None
    min_application: float | None = None
    listing_date: date | None = None
    latest_revenue: float | None = None
    previous_revenue: float | None = None
    latest_pat: float | None = None
    previous_pat: float | None = None


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
    warnings: list[str] = field(default_factory=list)


@dataclass
class SignalResult:
    ipo: IpoRecord
    score: float
    label: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
