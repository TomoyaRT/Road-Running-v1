from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

from src.scraper.city_resolver import resolve_city
from src.scraper.running_biji import RaceEvent

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.sportsnet.org.tw/schedule.php"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def fetch_events() -> list[RaceEvent]:
    try:
        resp = requests.get(_BASE_URL, timeout=15, headers=_HEADERS)
        resp.raise_for_status()
    except Exception:
        logger.exception("sportsnet fetch failed")
        return []
    return _parse_events(resp.text)


def _parse_events(html: str) -> list[RaceEvent]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        return []
    sched_table = tables[1]
    if not isinstance(sched_table, Tag):
        return []
    events: list[RaceEvent] = []
    for row in sched_table.find_all("tr")[1:]:
        if not isinstance(row, Tag):
            continue
        event = _parse_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_row(row: Tag) -> RaceEvent | None:
    cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]
    if len(cells) < 6:
        return None
    name = cells[3].get_text(strip=True)
    if not name:
        return None
    race_date = _parse_date(cells[2].get_text(strip=True), name)
    if race_date is None:
        return None
    location = cells[4].get_text(strip=True)
    cats_text = cells[5].get_text(strip=True)
    categories = [c.strip() for c in re.split(r"/(?![^(]*\))", cats_text) if c.strip()]
    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=_BASE_URL,
        reg_start=None,
        reg_end=None,
        city=resolve_city(location),
        image_url=None,
        official_url=_cell_link(cells[3]),
        categories=categories,
        source="sportsnet",
    )


def _cell_link(cell: Tag) -> str:
    link = cell.find("a", href=True)
    return str(link["href"]) if isinstance(link, Tag) else ""


def _parse_date(date_text: str, event_name: str) -> date | None:
    m = _DATE_RE.search(date_text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        return date(_infer_year(event_name), month, day)
    except ValueError:
        return None


def _infer_year(event_name: str) -> int:
    m = _YEAR_RE.search(event_name)
    return int(m.group(1)) if m else date.today().year
