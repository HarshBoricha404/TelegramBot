from __future__ import annotations

import re
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from src.models import IpoDetails, IpoRecord, SubscriptionData

GMP_URL = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
SUBSCRIPTION_URL = "https://ipowatch.in/ipo-subscription-status-today/"
PREMIUM_URL = "https://www.ipopremium.in/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
IST = ZoneInfo("Asia/Kolkata")

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


class ScrapeError(RuntimeError):
    """Raised when an IPO source cannot be fetched or safely parsed."""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _cell_text(cell: Tag) -> str:
    return _clean(cell.get_text(" ", strip=True))


def _number(text: str, *, dash_is_zero: bool = False) -> float | None:
    cleaned = _clean(text).replace(",", "").replace("*", "")
    if not cleaned or re.fullmatch(r"(?:₹|rs\.?)?\s*[-—–]", cleaned, re.I):
        return 0.0 if dash_is_zero else None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def parse_gain_pct(est_listing: str) -> float:
    match = re.search(r"\((-?\d+(?:\.\d+)?)\s*%\)", _clean(est_listing))
    return float(match.group(1)) if match else 0.0


def parse_gmp_amount(gmp_text: str) -> float:
    return _number(gmp_text, dash_is_zero=True) or 0.0


def _canonical_header(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if value in {"ipo", "ipo name", "company", "company name"}:
        return "name"
    if "gmp" in value and "percent" not in value:
        return "gmp"
    if value.startswith("trend"):
        return "trend"
    if "price band" in value or value == "price":
        return "price"
    if "est" in value and "listing" in value:
        return "estimated"
    if value in {"date", "ipo date"}:
        return "date"
    if value == "type":
        return "type"
    if value == "status":
        return "status"
    if "last updated" in value or value == "updated":
        return "updated"
    if value == "open":
        return "open"
    if value == "close" or "closing date" in value:
        return "close"
    if value.startswith("qib"):
        return "qib"
    if value.startswith("nii") or value.startswith("hni"):
        return "nii"
    if value.startswith("retail"):
        return "retail"
    if value.startswith("total"):
        return "total"
    if "listing date" in value:
        return "listing_date"
    return value


def _table_headers(table: Tag) -> tuple[dict[str, int], Tag | None]:
    row = table.find("tr")
    if not row:
        return {}, None
    headers = {
        _canonical_header(_cell_text(cell)): index
        for index, cell in enumerate(row.find_all(["th", "td"], recursive=False))
    }
    return headers, row


def _value(cells: list[Tag], headers: dict[str, int], key: str) -> str:
    index = headers.get(key)
    return _cell_text(cells[index]) if index is not None and index < len(cells) else ""


def normalize_name(name: str) -> str:
    value = name.lower().replace("&", " and ")
    value = re.sub(
        r"\b(?:limited|ltd|private|pvt|ipo|india|mainboard|sme|nse|bse|eq)\b",
        " ",
        value,
    )
    return re.sub(r"[^a-z0-9]+", "", value)


def _match_by_name(name: str, candidates: dict[str, object]) -> object | None:
    key = normalize_name(name)
    if key in candidates:
        return candidates[key]
    scored = sorted(
        ((SequenceMatcher(None, key, other).ratio(), value) for other, value in candidates.items()),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < 0.92:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.03:
        return None
    return scored[0][1]


def _safe_url(raw_url: str | None, base: str = "https://ipowatch.in") -> str | None:
    if not raw_url:
        return None
    if raw_url.startswith("/"):
        raw_url = base + raw_url
    parts = urlsplit(raw_url)
    path = re.sub(r"/{2,}", "/", parts.path)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _month(value: str) -> int | None:
    return _MONTHS.get(value.lower().rstrip("."))


def _near_reference(day: int, month: int, reference: date) -> date | None:
    for year in (reference.year, reference.year + 1, reference.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if -200 <= (candidate - reference).days <= 300:
            return candidate
    return None


def parse_date_range(text: str, reference: date) -> tuple[date | None, date | None]:
    cleaned = _clean(text).replace("–", "-").replace("—", "-")
    match = re.search(
        r"(?P<start>\d{1,2})\s*(?P<start_month>[A-Za-z]+)?\s*-\s*"
        r"(?P<end>\d{1,2})\s*(?P<end_month>[A-Za-z]+)(?:\s+(?P<year>\d{4}))?",
        cleaned,
    )
    if match:
        end_month = _month(match.group("end_month"))
        if not end_month:
            return None, None
        start_day = int(match.group("start"))
        end_day = int(match.group("end"))
        start_month = _month(match.group("start_month") or "") or end_month
        if not match.group("start_month") and start_day > end_day:
            start_month = 12 if end_month == 1 else end_month - 1
        year = int(match.group("year")) if match.group("year") else reference.year
        end_date = _near_reference(end_day, end_month, reference) if not match.group("year") else None
        if match.group("year"):
            try:
                end_date = date(year, end_month, end_day)
            except ValueError:
                return None, None
        if not end_date:
            return None, None
        start_year = end_date.year - (1 if start_month > end_month else 0)
        try:
            return date(start_year, start_month, start_day), end_date
        except ValueError:
            return None, None

    match = re.search(
        r"(?P<month>[A-Za-z]+)\s+(?P<start>\d{1,2})\s*-\s*"
        r"(?P<end>\d{1,2})(?:,\s*(?P<year>\d{4}))?",
        cleaned,
    )
    if match and (month := _month(match.group("month"))):
        end = _near_reference(int(match.group("end")), month, reference)
        if match.group("year"):
            try:
                end = date(int(match.group("year")), month, int(match.group("end")))
            except ValueError:
                return None, None
        if end:
            try:
                return date(end.year, month, int(match.group("start"))), end
            except ValueError:
                pass
    return None, None


def _parse_full_date(text: str, reference: date) -> date | None:
    matches = re.finditer(
        r"(?:(?P<day>\d{1,2})\s+(?P<month1>[A-Za-z]+)|"
        r"(?P<month2>[A-Za-z]+)\s+(?P<day2>\d{1,2}))(?:,?\s+(?P<year>\d{4}))?",
        _clean(text),
    )
    for match in matches:
        month = _month(match.group("month1") or match.group("month2"))
        if not month:
            continue
        day = int(match.group("day") or match.group("day2"))
        if match.group("year"):
            try:
                return date(int(match.group("year")), month, day)
            except ValueError:
                continue
        candidate = _near_reference(day, month, reference)
        if candidate:
            return candidate
    return None


def parse_updated_at(text: str, now: datetime, page_date: date | None = None) -> datetime | None:
    cleaned = _clean(text)
    time_match = re.search(r"(\d{1,2}):(\d{2})", cleaned)
    if not time_match:
        return None
    row_date = _parse_full_date(cleaned, now.date()) or page_date
    if not row_date:
        return None
    try:
        return datetime(
            row_date.year,
            row_date.month,
            row_date.day,
            int(time_match.group(1)),
            int(time_match.group(2)),
            tzinfo=IST,
        )
    except ValueError:
        return None


def _trend(text: str) -> str:
    value = text.lower()
    if "🟢" in text or "green" in value or "up" in value:
        return "rising"
    if "🔴" in text or "red" in value or "down" in value:
        return "falling"
    if "🟡" in text or "yellow" in value or "stable" in value:
        return "stable"
    return "unknown"


def _status_from_dates(open_date: date | None, close_date: date | None, today: date) -> str:
    if open_date and today < open_date:
        return "Upcoming"
    if open_date and close_date and open_date <= today <= close_date:
        return "Open"
    if close_date and today > close_date:
        return "Closed"
    return "Unknown"


def parse_ipowatch_gmp_html(
    html: str,
    *,
    now: datetime | None = None,
    source_url: str = GMP_URL,
) -> list[IpoRecord]:
    now = now or datetime.now(IST)
    soup = BeautifulSoup(html, "lxml")
    records: list[IpoRecord] = []

    for table in soup.find_all("table"):
        headers, header_row = _table_headers(table)
        if not header_row or not {"name", "gmp", "status"}.issubset(headers):
            continue
        heading = table.find_previous(["h2", "h3", "h4"])
        heading_text = _clean(heading.get_text(" ", strip=True) if heading else "")
        section_type = "SME" if "sme" in heading_text.lower() else (
            "Mainboard" if "mainboard" in heading_text.lower() else ""
        )

        for row in table.find_all("tr"):
            if row is header_row:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            name = _value(cells, headers, "name")
            if not name:
                continue
            name_cell = cells[headers["name"]]
            link = name_cell.find("a", href=True)
            price_text = _value(cells, headers, "price")
            prices = [
                float(value.replace(",", ""))
                for value in re.findall(r"\d[\d,]*(?:\.\d+)?", price_text)
            ]
            estimated_text = _value(cells, headers, "estimated")
            estimated = _number(estimated_text)
            gain_pct = parse_gain_pct(estimated_text)
            gmp = parse_gmp_amount(_value(cells, headers, "gmp"))
            if not gain_pct and prices and prices[-1]:
                gain_pct = round(gmp / prices[-1] * 100, 2)
            date_text = _value(cells, headers, "date")
            open_date, close_date = parse_date_range(date_text, now.date())
            raw_status = _value(cells, headers, "status").title()
            derived_status = _status_from_dates(open_date, close_date, now.date())
            status = raw_status if raw_status in {"Open", "Upcoming", "Closed"} else derived_status
            warnings: list[str] = []
            if derived_status != "Unknown" and status != derived_status:
                warnings.append("status/date mismatch")
            ipo_type = section_type or _value(cells, headers, "type") or "Unknown"
            ipo_type = "SME" if "sme" in ipo_type.lower() else (
                "Mainboard" if ipo_type else "Unknown"
            )
            record = IpoRecord(
                name=name,
                ipo_type=ipo_type,
                status=status,
                source="IPO Watch",
                source_url=source_url,
                gmp_rs=gmp,
                gain_pct=gain_pct,
                trend=_trend(_value(cells, headers, "trend")),
                price_low=prices[0] if prices else None,
                price_high=prices[-1] if prices else None,
                estimated_listing=estimated,
                open_date=open_date,
                close_date=close_date,
                date_text=date_text,
                updated_at=parse_updated_at(_value(cells, headers, "updated"), now),
                fetched_at=now,
                url=_safe_url(link.get("href") if link else None),
                warnings=warnings,
            )
            records.append(record)

    if not records:
        raise ScrapeError("IPO Watch GMP tables were missing or contained no parseable rows")
    unique = {normalize_name(record.name): record for record in records}
    if len(unique) < len(records):
        records = list(unique.values())
    return records


# Backward-compatible public parser name used by local callers/tests.
parse_gmp_html = parse_ipowatch_gmp_html


def parse_subscription_html(
    html: str,
    *,
    now: datetime | None = None,
) -> dict[str, SubscriptionData]:
    now = now or datetime.now(IST)
    soup = BeautifulSoup(html, "lxml")
    page_text = _clean(soup.get_text(" ", strip=True))
    page_date = _parse_full_date(page_text, now.date())

    for table in soup.find_all("table"):
        headers, header_row = _table_headers(table)
        required = {"name", "qib", "nii", "retail", "total"}
        if not header_row or not required.issubset(headers):
            continue
        result: dict[str, SubscriptionData] = {}
        for row in table.find_all("tr"):
            if row is header_row:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            name = _value(cells, headers, "name")
            if not name:
                continue
            closing = _parse_full_date(_value(cells, headers, "close"), now.date())
            timestamp_date = page_date
            if closing and closing < now.date():
                timestamp_date = closing
            result[normalize_name(name)] = SubscriptionData(
                qib=_number(_value(cells, headers, "qib")),
                nii=_number(_value(cells, headers, "nii")),
                retail=_number(_value(cells, headers, "retail")),
                total=_number(_value(cells, headers, "total")),
                updated_at=parse_updated_at(
                    _value(cells, headers, "updated"),
                    now,
                    timestamp_date,
                ),
            )
        if result:
            return result
    raise ScrapeError("IPO Watch subscription table was missing or empty")


def parse_premium_html(
    html: str,
    *,
    now: datetime | None = None,
    source_url: str = PREMIUM_URL,
) -> list[IpoRecord]:
    now = now or datetime.now(IST)
    soup = BeautifulSoup(html, "lxml")
    records: list[IpoRecord] = []
    for table in soup.find_all("table"):
        headers, header_row = _table_headers(table)
        if not header_row or not {"name", "gmp", "open", "close", "price"}.issubset(headers):
            continue
        for row in table.find_all("tr"):
            if row is header_row:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            name = _value(cells, headers, "name")
            if not name:
                continue
            open_date = _parse_full_date(_value(cells, headers, "open"), now.date())
            close_date = _parse_full_date(_value(cells, headers, "close"), now.date())
            prices = [
                float(value.replace(",", ""))
                for value in re.findall(r"\d[\d,]*(?:\.\d+)?", _value(cells, headers, "price"))
            ]
            gmp = parse_gmp_amount(_value(cells, headers, "gmp"))
            high = prices[-1] if prices else None
            raw_type = _value(cells, headers, "type")
            records.append(
                IpoRecord(
                    name=name,
                    ipo_type="SME" if "sme" in raw_type.lower() else "Mainboard",
                    status=_status_from_dates(open_date, close_date, now.date()),
                    source="IPO Premium",
                    source_url=source_url,
                    gmp_rs=gmp,
                    gain_pct=round(gmp / high * 100, 2) if high else None,
                    price_low=prices[0] if prices else None,
                    price_high=high,
                    estimated_listing=high + gmp if high is not None else None,
                    open_date=open_date,
                    close_date=close_date,
                    date_text=f"{_value(cells, headers, 'open')} – {_value(cells, headers, 'close')}",
                    fetched_at=now,
                    warnings=["source row timestamp unavailable"],
                )
            )
    if not records:
        raise ScrapeError("IPO Premium table was missing or empty")
    return records


def _money_from_cell(text: str) -> float | None:
    return _number(text)


def parse_detail_html(html: str, expected_name: str, reference: date) -> IpoDetails:
    soup = BeautifulSoup(html, "lxml")
    expected = normalize_name(expected_name)
    start: Tag | None = None
    for heading in soup.find_all(["h1", "h2"]):
        raw_heading = _cell_text(heading)
        heading_name = normalize_name(raw_heading)
        if expected and expected in heading_name and "ipo" in raw_heading.lower():
            start = heading
            break
    if not start:
        raise ScrapeError(f"Detail page identity did not match {expected_name!r}")

    tables: list[Tag] = []
    for element in start.find_all_next(["h1", "table"]):
        if element.name == "h1" and element is not start:
            break
        if element.name == "table":
            tables.append(element)

    details = IpoDetails()
    annual_financials: list[tuple[int, float | None, float | None]] = []
    for table in tables:
        rows = table.find_all("tr")
        headers, header_row = _table_headers(table)
        if {"period ended", "revenue", "pat"}.issubset(headers):
            for row in rows:
                if row is header_row:
                    continue
                cells = row.find_all(["td", "th"], recursive=False)
                period = _value(cells, headers, "period ended")
                if re.fullmatch(r"\d{4}", period):
                    annual_financials.append(
                        (
                            int(period),
                            _money_from_cell(_value(cells, headers, "revenue")),
                            _money_from_cell(_value(cells, headers, "pat")),
                        )
                    )
        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 2:
                continue
            key = _canonical_header(_cell_text(cells[0]))
            value = _cell_text(cells[-1])
            if key == "issue size" and not details.issue_size:
                details.issue_size = value
            elif key == "listing_date" and not details.listing_date:
                details.listing_date = _parse_full_date(value, reference)
            elif _cell_text(cells[0]).lower() == "retail minimum" and len(cells) >= 4:
                details.lot_size = int(_number(_cell_text(cells[2])) or 0) or None
                details.min_application = _money_from_cell(_cell_text(cells[-1]))

    annual_financials.sort()
    if annual_financials:
        _, details.latest_revenue, details.latest_pat = annual_financials[-1]
    if len(annual_financials) > 1:
        _, details.previous_revenue, details.previous_pat = annual_financials[-2]
    return details


def _validate_html(response: httpx.Response, url: str) -> str:
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type:
        raise ScrapeError(f"Unexpected content type from {url}: {content_type}")
    text = response.text
    if len(text) < 500:
        raise ScrapeError(f"Implausibly short HTML response from {url}")
    lowered = text.lower()
    if "captcha" in lowered or "cf-chl-" in lowered:
        raise ScrapeError(f"Challenge page returned by {url}")
    return text


def fetch_html(url: str, *, attempts: int = 3) -> str:
    last_error: Exception | None = None
    timeout = httpx.Timeout(20.0, connect=10.0)
    for attempt in range(attempts):
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                timeout=timeout,
                follow_redirects=True,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"transient HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            return _validate_html(response, url)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(0.5 * (2**attempt))
        except ScrapeError:
            raise
    raise ScrapeError(f"Failed to fetch {url}: {last_error}") from last_error


def _attach_subscription(
    records: list[IpoRecord],
    subscriptions: dict[str, SubscriptionData],
) -> None:
    for record in records:
        match = _match_by_name(record.name, subscriptions)
        if isinstance(match, SubscriptionData):
            record.subscription = match


def _attach_crosscheck(records: list[IpoRecord], alternates: list[IpoRecord]) -> None:
    alternate_map: dict[str, object] = {
        normalize_name(record.name): record for record in alternates
    }
    for record in records:
        match = _match_by_name(record.name, alternate_map)
        if isinstance(match, IpoRecord):
            record.alternate_gmp_rs = match.gmp_rs


def _preliminary_candidates(records: list[IpoRecord], today: date) -> list[IpoRecord]:
    eligible = [
        record
        for record in records
        if record.status == "Open"
        and record.open_date is not None
        and record.close_date is not None
        and record.open_date <= today <= record.close_date
        and (record.gain_pct or 0) > 0
    ]
    return sorted(
        eligible,
        key=lambda record: ((15 if record.ipo_type == "Mainboard" else 0) + (record.gain_pct or 0)),
        reverse=True,
    )[:3]


def scrape_market_data(*, now: datetime | None = None) -> list[IpoRecord]:
    now = now or datetime.now(IST)
    primary_error: Exception | None = None
    premium_error: Exception | None = None
    primary: list[IpoRecord] = []
    premium: list[IpoRecord] = []

    try:
        primary = parse_ipowatch_gmp_html(fetch_html(GMP_URL), now=now)
        if not any(record.status in {"Open", "Upcoming"} for record in primary):
            raise ScrapeError("IPO Watch returned no active or upcoming IPO rows")
    except (ScrapeError, httpx.HTTPError) as exc:
        primary_error = exc
        primary = []

    try:
        premium = parse_premium_html(fetch_html(PREMIUM_URL), now=now)
        if not any(record.status in {"Open", "Upcoming"} for record in premium):
            raise ScrapeError("IPO Premium returned no active or upcoming IPO rows")
    except (ScrapeError, httpx.HTTPError) as exc:
        premium_error = exc
        premium = []

    if not primary and not premium:
        raise ScrapeError(
            f"All GMP sources failed; IPO Watch: {primary_error}; IPO Premium: {premium_error}"
        )
    records = primary or premium

    try:
        subscriptions = parse_subscription_html(fetch_html(SUBSCRIPTION_URL), now=now)
        _attach_subscription(records, subscriptions)
    except (ScrapeError, httpx.HTTPError):
        for record in records:
            record.warnings.append("subscription data unavailable")

    if primary and premium:
        _attach_crosscheck(records, premium)

    for record in _preliminary_candidates(records, now.date()):
        if not record.url:
            continue
        try:
            record.details = parse_detail_html(fetch_html(record.url), record.name, now.date())
        except (ScrapeError, httpx.HTTPError):
            record.warnings.append("verified detail metadata unavailable")
    return records


def scrape_ipo_gmp(url: str = GMP_URL) -> list[IpoRecord]:
    """Compatibility wrapper for callers that only need IPO Watch GMP rows."""
    return parse_ipowatch_gmp_html(fetch_html(url), source_url=url)
