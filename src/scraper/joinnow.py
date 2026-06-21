from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

from src.scraper.city_resolver import resolve_city
from src.scraper.running_biji import RaceEvent

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.joinnow.com.tw/"
_UA = "Mozilla/5.0"
_SLASH_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def fetch_events() -> list[RaceEvent]:
    """從 joinnow.com.tw 首頁收集活動連結，逐一解析成 RaceEvent。"""
    try:
        resp = requests.get(_BASE_URL, timeout=15, headers={"User-Agent": _UA})
        resp.raise_for_status()
    except Exception:
        logger.exception("joinnow list fetch failed")
        return []

    events = []
    for url in _parse_event_urls(resp.text):
        event = _fetch_detail(url)
        if event is not None:
            events.append(event)
    return events


def _parse_event_urls(html: str) -> list[str]:
    """從首頁取出不重複的活動詳情頁 URL（run-step1.php?cnt_id=XXX）。"""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = str(a.get("href", ""))
        if "run-step1.php" not in href or "cnt_id=" not in href:
            continue
        url = href if href.startswith("http") else f"{_BASE_URL.rstrip('/')}/{href}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _fetch_detail(url: str) -> RaceEvent | None:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": _UA})
        resp.raise_for_status()
        return _parse_detail(resp.text, url)
    except Exception:
        logger.warning("joinnow detail fetch failed: %s", url)
        return None


def _parse_detail(html: str, url: str) -> RaceEvent | None:
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if not isinstance(h1, Tag):
        return None
    name = h1.get_text(strip=True)
    if not name:
        return None

    race_date = _parse_first_date(_span_value(soup, "活動日期"))
    if race_date is None:
        return None

    location = _span_value(soup, "活動地點")
    reg_end = _parse_first_date(_span_value(soup, "報名期限"))

    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=url,
        reg_start=None,
        reg_end=reg_end,
        city=resolve_city(location),
        image_url=_extract_og_image(soup),
        official_url=url,
        categories=_parse_categories(soup),
        source="joinnow",
    )


def _extract_og_image(soup: BeautifulSoup) -> str | None:
    og_img = soup.find("meta", property="og:image")
    if isinstance(og_img, Tag) and og_img.get("content"):
        return str(og_img["content"])
    return None


def _span_value(soup: BeautifulSoup, label: str) -> str:
    """找 span.liSpan 含 label 的父元素，回傳去掉 label 後的文字。"""
    for span in soup.find_all("span", class_="liSpan"):
        if not isinstance(span, Tag) or span.get_text(strip=True) != label:
            continue
        parent_text = span.parent.get_text(strip=True) if span.parent else ""
        return (
            parent_text[len(label) :].strip() if parent_text.startswith(label) else ""
        )
    return ""


def _parse_first_date(text: str) -> date | None:
    for regex in (_SLASH_DATE_RE, _ISO_DATE_RE):
        m = regex.search(text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def _parse_categories(soup: BeautifulSoup) -> list[str]:
    """從「項目」表頭行取出報名組別（第一欄，跳過標題行）。"""
    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue
        rows = [r for r in table.find_all("tr") if isinstance(r, Tag)]
        if not rows:
            continue
        headers = [
            c.get_text(strip=True)
            for c in rows[0].find_all(["td", "th"])
            if isinstance(c, Tag)
        ]
        if not headers or headers[0] != "項目":
            continue
        results: list[str] = []
        for row in rows[1:]:
            cell = row.find(["td", "th"])
            if isinstance(cell, Tag):
                text = cell.get_text(strip=True)
                if text:
                    results.append(text)
        return results
    return []
