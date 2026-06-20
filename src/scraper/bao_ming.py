from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

from src.scraper.running_biji import RaceEvent, extract_og_image, find_city

logger = logging.getLogger(__name__)

BASE_URL = "https://bao-ming.com/"
_HOST = "https://bao-ming.com"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_EXECUTOR = ThreadPoolExecutor(max_workers=12)


def fetch_events(url: str = BASE_URL) -> list[RaceEvent]:
    """從報名網（bao-ming.com）收集活動連結後，逐一抓詳情頁解析成 RaceEvent。"""
    resp = requests.get(url, timeout=15, headers=_HEADERS)
    resp.raise_for_status()
    urls = collect_event_urls(resp.text)
    results = _EXECUTOR.map(_safe_fetch_detail, urls)
    return [e for e in results if e is not None]


def collect_event_urls(html: str) -> list[str]:
    """從列表頁取出不重複的活動詳情頁 URL（/eb/content/<id>）。"""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", class_="activity-link", href=True):
        if not isinstance(link, Tag):
            continue
        href = str(link.get("href", "")).split("#")[0]
        if "/eb/content/" not in href:
            continue
        full = href if href.startswith("http") else f"{_HOST}{href}"
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def _safe_fetch_detail(url: str) -> RaceEvent | None:
    try:
        resp = requests.get(url, timeout=10, headers=_HEADERS)
        resp.raise_for_status()
        return parse_detail_html(resp.text, url)
    except Exception:
        logger.warning(f"bao-ming fetch detail failed: {url}")
        return None


def parse_detail_html(html: str, url: str) -> RaceEvent | None:
    """解析報名網活動詳情頁。無法取得比賽日期則回 None。"""
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    race_date = _race_date(soup, full_text)
    if race_date is None:
        return None
    name = _event_name(soup)
    if not name:
        return None
    reg_start, reg_end = _reg_dates(full_text)
    location = _labeled_text(full_text, "活動地點") or ""
    city = find_city(location) or find_city(_labeled_text(full_text, "地點", 40) or "")
    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=url,
        reg_start=reg_start,
        reg_end=reg_end,
        city=city,
        image_url=extract_og_image(html, base_url=url),
        official_url=url,
        organizer=_labeled_value(soup, "主辦單位"),
        source="baoming",
    )


def _event_name(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", property="og:title")
    if isinstance(meta, Tag) and meta.get("content"):
        return str(meta.get("content")).strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if isinstance(h1, Tag) else ""


def _parse_dates(text: str) -> list[date]:
    """依出現順序解析文字中的日期（支援 2026年6月1日 與 2026-06-01）。"""
    found: list[tuple[int, date]] = []
    for regex in (_CN_DATE_RE, _ISO_DATE_RE):
        for m in regex.finditer(text):
            try:
                found.append(
                    (m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                )
            except ValueError:
                continue
    return [d for _, d in sorted(found)]


def _race_date(soup: BeautifulSoup, full_text: str) -> date | None:
    el = soup.find(string=re.compile("活動日期"))
    if el is not None and el.parent is not None:
        sib = el.parent.find_next_sibling()
        if isinstance(sib, Tag):
            dates = _parse_dates(sib.get_text(strip=True))
            if dates:
                return dates[0]
    idx = full_text.find("活動日期")
    if idx >= 0:
        dates = _parse_dates(full_text[idx : idx + 40])
        if dates:
            return dates[0]
    return None


def _reg_dates(full_text: str) -> tuple[date | None, date | None]:
    for label in ("報名日期", "報名起訖", "報名時間"):
        idx = full_text.find(label)
        if idx < 0:
            continue
        dates = _parse_dates(full_text[idx : idx + 90])
        if len(dates) >= 2:
            return dates[0], dates[1]
        if len(dates) == 1:
            return dates[0], None
    return None, None


def _labeled_text(full_text: str, label: str, length: int = 30) -> str | None:
    """從整頁文字中取 label 之後的一段（用於地點等位置不固定的欄位）。"""
    idx = full_text.find(label)
    if idx < 0:
        return None
    seg = full_text[idx + len(label) : idx + len(label) + length]
    return seg.strip(" 　：:") or None


def _labeled_value(soup: BeautifulSoup, label: str) -> str | None:
    """找含 label 的元素，取其後一個兄弟節點的文字（仿詳情頁 label→value 結構）。"""
    el = soup.find(string=re.compile(label))
    if el is None or el.parent is None:
        return None
    sib = el.parent.find_next_sibling()
    if isinstance(sib, Tag):
        text = sib.get_text(" ", strip=True)
        if text and len(text) < 100:
            return text
    return None
