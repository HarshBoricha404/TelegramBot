from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup, Tag

GMP_URL = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_ALLOWED_STATUSES = frozenset({"upcoming", "open", "closed"})


@dataclass(frozen=True)
class IpoGmpRow:
    name: str
    url: str | None
    gmp: str
    trend: str
    price_band: str
    est_listing: str
    gain_pct: float
    date: str
    ipo_type: str
    status: str
    last_updated: str


class ScrapeError(RuntimeError):
    """Raised when the GMP page cannot be fetched or parsed."""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_gain_pct(est_listing: str) -> float:
    """Parse estimated listing gain percent from strings like '₹328 (15.09%)'."""
    cleaned = _clean(est_listing)
    match = re.search(r"\((-?\d+(?:\.\d+)?)\s*%\)", cleaned)
    if match:
        return float(match.group(1))
    if re.search(r"₹\s*-", cleaned) or cleaned in {"-", "—", "N/A", ""}:
        return 0.0
    raise ScrapeError(f"Could not parse estimated listing gain from {est_listing!r}")


def parse_gmp_amount(gmp_text: str) -> str:
    """Normalize GMP display text, keeping the ₹ prefix when present."""
    cleaned = _clean(gmp_text).replace("*", "")
    if not cleaned or cleaned in {"-", "—"}:
        return "₹0"
    if cleaned.startswith("₹"):
        return cleaned
    if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return f"₹{cleaned}"
    return cleaned


def _cell_text(cell: Tag) -> str:
    return _clean(cell.get_text(" ", strip=True))


def _parse_row(tr: Tag) -> IpoGmpRow | None:
    cells = tr.find_all(["td", "th"])
    if len(cells) < 8:
        return None

    # Skip header rows
    first = _cell_text(cells[0]).lower()
    if "ipo name" in first:
        return None

    name_cell = cells[0]
    link = name_cell.find("a", href=True)
    name = _clean(link.get_text(" ", strip=True) if link else name_cell.get_text(" ", strip=True))
    if not name:
        return None

    url = link["href"].strip() if link else None
    if url and url.startswith("/"):
        url = f"https://ipowatch.in{url}"

    gmp = parse_gmp_amount(_cell_text(cells[1]))
    trend = _cell_text(cells[2])
    price_band = _cell_text(cells[3])
    est_listing = _cell_text(cells[4])
    date = _cell_text(cells[5])
    ipo_type = _cell_text(cells[6])
    status = _cell_text(cells[7])
    last_updated = _cell_text(cells[8]) if len(cells) > 8 else ""

    status_norm = status.lower()
    if status_norm not in _ALLOWED_STATUSES:
        # Some rows may use slightly different casing/spacing; keep raw if unknown
        pass

    gain_pct = parse_gain_pct(est_listing)

    return IpoGmpRow(
        name=name,
        url=url,
        gmp=gmp,
        trend=trend,
        price_band=price_band,
        est_listing=est_listing,
        gain_pct=gain_pct,
        date=date,
        ipo_type=ipo_type,
        status=status,
        last_updated=last_updated,
    )


def _find_live_gmp_table(soup: BeautifulSoup) -> Tag:
    """Locate the live IPO GMP table (first table with expected headers)."""
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [_cell_text(c).lower() for c in header_row.find_all(["th", "td"])]
        header_blob = " ".join(headers)
        if "ipo name" in header_blob and "gmp" in header_blob and "status" in header_blob:
            return table

    raise ScrapeError(
        "Could not find the live IPO GMP table on the page "
        "(expected columns: IPO Name, GMP, Status). Site HTML may have changed."
    )


def parse_gmp_html(html: str) -> list[IpoGmpRow]:
    soup = BeautifulSoup(html, "lxml")
    table = _find_live_gmp_table(soup)
    rows: list[IpoGmpRow] = []
    for tr in table.find_all("tr"):
        parsed = _parse_row(tr)
        if parsed:
            rows.append(parsed)

    if not rows:
        raise ScrapeError(
            "GMP table found but no IPO rows could be parsed. Site HTML may have changed."
        )
    return rows


def fetch_gmp_page(url: str = GMP_URL, timeout: float = 30.0) -> str:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ScrapeError(f"Failed to fetch GMP page: {exc}") from exc
    return response.text


def scrape_ipo_gmp(url: str = GMP_URL) -> list[IpoGmpRow]:
    html = fetch_gmp_page(url)
    return parse_gmp_html(html)
