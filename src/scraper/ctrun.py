from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests
from bs4 import BeautifulSoup, Tag

from src.scraper.city_resolver import resolve_city
from src.scraper.running_biji import CATEGORY_KEYWORDS, RaceEvent, extract_og_image

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ctrun.com.tw/"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_ID_RE = re.compile(r"EventMain_ID=(\d+)")
_CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_SLASH_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_INFO_ANCHOR = "活動資訊"
# 詳情頁「活動資訊」區塊的欄位標籤，用來界定每個欄位值的邊界
_FIELD_LABELS = (
    "活動名稱",
    "活動日期",
    "報名時間",
    "報名日期",
    "活動地點",
    "主辦單位",
    "承辦單位",
    "協辦單位",
    "贊助單位",
    "活動網站",
    "聯絡",
)
_EXECUTOR = ThreadPoolExecutor(max_workers=12)
_CATEGORY_HEADERS = {"報名組別", "組別"}


def fetch_events(url: str = BASE_URL) -> list[RaceEvent]:
    """從全統運動報名網（ctrun）收集活動連結後，逐一抓詳情頁解析。"""
    resp = requests.get(url, timeout=15, headers=_HEADERS)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    urls = collect_event_urls(resp.text)
    results = _EXECUTOR.map(_safe_fetch_detail, urls)
    return [e for e in results if e is not None]


def collect_event_urls(html: str) -> list[str]:
    """取出不重複的活動 ID，正規化成標準詳情頁 URL。"""
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue
        m = _ID_RE.search(str(link.get("href", "")))
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            ids.append(m.group(1))
    return [f"https://www.ctrun.com.tw/Activity?EventMain_ID={i}" for i in ids]


def _safe_fetch_detail(url: str) -> RaceEvent | None:
    try:
        resp = requests.get(url, timeout=10, headers=_HEADERS)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        return parse_detail_html(resp.text, url)
    except Exception:
        logger.warning("ctrun fetch detail failed: %s", url)
        return None


def parse_detail_html(html: str, url: str) -> RaceEvent | None:
    """解析 ctrun 活動詳情頁的「活動資訊」區塊。無比賽日期則回 None。"""
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    idx = full_text.find(_INFO_ANCHOR)
    info = full_text[idx:] if idx >= 0 else full_text

    race_date = _date_after(info, "活動日期")
    name = _field(info, "活動名稱") or _og_title(soup)
    if race_date is None or not name:
        return None
    reg_start, reg_end = _reg_dates(_window_after(info, "報名時間", 60))
    location = _field(info, "活動地點") or ""
    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=url,
        reg_start=reg_start,
        reg_end=reg_end,
        city=resolve_city(location),
        image_url=extract_og_image(html, base_url=url),
        official_url=url,
        organizer=_field(info, "主辦單位"),
        categories=_extract_categories(soup),
        source="ctrun",
    )


def _extract_categories(soup: BeautifulSoup) -> list[str]:
    """從「報名組別」或「組別」表頭行取出含距離關鍵字的報名組別名稱。"""
    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue
        for row in table.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = [
                c.get_text(strip=True)
                for c in row.find_all(["td", "th"])
                if isinstance(c, Tag)
            ]
            if cells and cells[0] in _CATEGORY_HEADERS:
                return [c for c in cells[1:] if c and CATEGORY_KEYWORDS.search(c)]
    return []


def _field(info: str, label: str) -> str | None:
    """取 label 之後、到下一個已知標籤之前的欄位值。"""
    start = info.find(label)
    if start < 0:
        return None
    start += len(label)
    end = len(info)
    for other in _FIELD_LABELS:
        pos = info.find(other, start)
        if 0 <= pos < end:
            end = pos
    return info[start:end].strip(" 　：:") or None


def _window_after(info: str, label: str, length: int) -> str:
    """label 之後固定長度的文字視窗（不受後續標籤截斷影響）。"""
    idx = info.find(label)
    if idx < 0:
        return ""
    start = idx + len(label)
    return info[start : start + length]


def _date_after(info: str, label: str) -> date | None:
    return _first_date(_window_after(info, label, 30))


def _all_dates(text: str) -> list[date]:
    found: list[tuple[int, date]] = []
    for regex in (_CN_DATE_RE, _SLASH_DATE_RE):
        for m in regex.finditer(text):
            try:
                found.append(
                    (m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                )
            except ValueError:
                continue
    return [d for _, d in sorted(found)]


def _first_date(text: str) -> date | None:
    dates = _all_dates(text)
    return dates[0] if dates else None


def _reg_dates(text: str) -> tuple[date | None, date | None]:
    dates = _all_dates(text)
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return dates[0], None
    return None, None


def _og_title(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", property="og:title")
    if isinstance(meta, Tag) and meta.get("content"):
        return str(meta.get("content")).split(" - ")[0].strip()
    return ""
