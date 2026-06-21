from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

from src.scraper.city_resolver import resolve_city
from src.scraper.running_biji import CATEGORY_KEYWORDS, RaceEvent

logger = logging.getLogger(__name__)

_BASE_URL = "https://irunner.biji.co/list"
_ACTIVITY_BASE = "https://irunner.biji.co/"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_REG_TIME_RE = re.compile(r"起(\d{4}-\d{2}-\d{2}).*?迄(\d{4}-\d{2}-\d{2})")


def fetch_events() -> list[RaceEvent]:
    """從 irunner.biji.co/list 抓取路跑活動，official_url = 活動頁本身。"""
    try:
        resp = requests.get(_BASE_URL, timeout=15, headers={"User-Agent": _UA})
        resp.raise_for_status()
    except Exception:
        logger.exception("irunner list fetch failed")
        return []

    events = []
    for url in _parse_list(resp.text):
        event = _fetch_event_detail(url)
        if event is not None:
            events.append(event)
    return events


def _parse_list(html: str) -> list[str]:
    """從列表頁解析所有活動頁 URL（去重）。"""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []
    for row in soup.find_all("div", class_="competition-list-row"):
        if not isinstance(row, Tag):
            continue
        name_div = row.find("div", class_="competition-name")
        if not isinstance(name_div, Tag):
            continue
        a = name_div.find("a")
        if not isinstance(a, Tag):
            continue
        href = str(a.get("href", ""))
        if not href or href.startswith(("/", "http", "javascript")):
            continue
        url = f"{_ACTIVITY_BASE}{href}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _fetch_event_detail(url: str) -> RaceEvent | None:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": _UA})
        resp.raise_for_status()
        return _parse_detail(resp.text, url)
    except Exception:
        logger.warning("irunner detail fetch failed: %s", url)
        return None


def _parse_detail(html: str, url: str) -> RaceEvent | None:
    soup = BeautifulSoup(html, "html.parser")

    name_tag = soup.find("h1", class_="comp-title")
    if not isinstance(name_tag, Tag):
        return None
    name = name_tag.get_text(strip=True)
    if not name:
        return None

    race_date, location = _extract_detail_items(soup)
    if race_date is None:
        return None

    reg_start, reg_end = _parse_reg_times(soup)

    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=url,
        reg_start=reg_start,
        reg_end=reg_end,
        city=resolve_city(location),
        image_url=_extract_image_url(soup),
        official_url=url,
        categories=_parse_categories(soup),
        source="biji",
    )


def _extract_image_url(soup: BeautifulSoup) -> str | None:
    og_img = soup.find("meta", property="og:image")
    if isinstance(og_img, Tag) and og_img.get("content"):
        return str(og_img["content"])
    return None


def _extract_detail_items(soup: BeautifulSoup) -> tuple[date | None, str]:
    items = soup.find_all("div", class_="detail-item")
    date_text = (
        items[0].get_text(strip=True) if items and isinstance(items[0], Tag) else ""
    )
    location = (
        items[1].get_text(strip=True)
        if len(items) > 1 and isinstance(items[1], Tag)
        else ""
    )
    return _parse_date(date_text), location


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def _parse_reg_times(soup: BeautifulSoup) -> tuple[date | None, date | None]:
    for li in soup.find_all("li"):
        if not isinstance(li, Tag):
            continue
        text = li.get_text(strip=True)
        if "報名時間" in text:
            m = _REG_TIME_RE.search(text)
            if m:
                try:
                    return date.fromisoformat(m.group(1)), date.fromisoformat(
                        m.group(2)
                    )
                except ValueError:
                    pass
    return None, None


def _parse_categories(soup: BeautifulSoup) -> list[str]:
    """從 strong/h3 元素取出含距離關鍵字的報名組別。"""
    seen: set[str] = set()
    results: list[str] = []
    for tag in soup.find_all(["strong", "h3"]):
        if not isinstance(tag, Tag):
            continue
        text = tag.get_text(strip=True)
        if len(text) < 2 or len(text) > 40:
            continue
        if CATEGORY_KEYWORDS.search(text) and text not in seen:
            seen.add(text)
            results.append(text)
    return results
