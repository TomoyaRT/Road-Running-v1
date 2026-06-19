from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

BASE_URL = "https://running.biji.co/?q=competition"
_REG_DATE_RE = re.compile(r"報名日期:(\d{4}-\d{2}-\d{2}).*?~(\d{4}-\d{2}-\d{2})")
_CAL_DATES_RE = re.compile(r"dates=(\d{4})(\d{2})(\d{2})/")

_TW_CITIES = [
    "台北市",
    "新北市",
    "桃園市",
    "台中市",
    "台南市",
    "高雄市",
    "基隆市",
    "新竹市",
    "嘉義市",
    "宜蘭縣",
    "新竹縣",
    "苗栗縣",
    "彰化縣",
    "南投縣",
    "雲林縣",
    "嘉義縣",
    "屏東縣",
    "花蓮縣",
    "台東縣",
    "澎湖縣",
    "金門縣",
    "連江縣",
]

_SKIP_DOMAINS = {
    "biji.co",
    "google.com",
    "google.com.tw",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "line.me",
    "edh.tw",
}
_REG_KEYWORDS = {"報名", "線上報名", "立刻報名", "我要報名", "Register"}

_official_url_cache: dict[str, str | None] = {}


@dataclass
class RaceEvent:
    name: str
    race_date: date
    location: str
    url: str
    reg_start: date | None
    reg_end: date | None
    city: str = ""
    image_url: str | None = None
    official_url: str | None = None
    categories: list[str] = field(default_factory=list)


def extract_city(location: str) -> str:
    """從地點字串中提取台灣縣市名稱。"""
    for city in _TW_CITIES:
        if location.startswith(city):
            return city
    return location


def fetch_events(url: str = BASE_URL) -> list[RaceEvent]:
    """從運動筆記抓取路跑活動列表。"""
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return parse_events_html(resp.text)


def parse_events_html(html: str) -> list[RaceEvent]:
    """解析運動筆記活動列表 HTML，回傳活動清單。"""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("div", class_="competition-list-row")
    events: list[RaceEvent] = []
    for row in rows:
        if not isinstance(row, Tag):
            continue
        if "list-title" in row.get("class", []):
            continue
        event = _parse_row(row)
        if event is not None:
            events.append(event)
    return events


def _parse_row(row: Tag) -> RaceEvent | None:
    name_url = _extract_name_and_url(row)
    if name_url is None:
        return None
    name, url = name_url

    cal_link = row.find("a", class_="competition-date-calendar")
    cal_href = str(cal_link.get("href", "")) if isinstance(cal_link, Tag) else ""

    race_date = _parse_race_date(cal_href) or _fallback_race_date(row)
    reg_start, reg_end = _parse_reg_dates(cal_href)
    location = _extract_location(row)

    return RaceEvent(
        name=name,
        race_date=race_date,
        location=location,
        url=url,
        reg_start=reg_start,
        reg_end=reg_end,
        city=extract_city(location),
        image_url=_extract_image_url(row),
    )


def _extract_name_and_url(row: Tag) -> tuple[str, str] | None:
    name_tag = row.find("div", class_="competition-name")
    if not isinstance(name_tag, Tag):
        return None
    link = name_tag.find("a")
    if not isinstance(link, Tag):
        return None
    name = link.get_text(strip=True)
    href = str(link.get("href", ""))
    url = href if href.startswith("http") else f"https://running.biji.co{href}"
    return name, url


def _extract_image_url(row: Tag) -> str | None:
    """嘗試從活動列表行中取得活動縮圖 URL（非日曆圖示）。"""
    for img in row.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = str(img.get("src", ""))
        if src and "calendar" not in src:
            return src if src.startswith("http") else f"https://running.biji.co{src}"
    return None


def _extract_location(row: Tag) -> str:
    place_tag = row.find("div", class_="competition-place")
    if not isinstance(place_tag, Tag):
        return ""
    span = place_tag.find("span")
    return span.get_text(strip=True) if isinstance(span, Tag) else ""


def _fallback_race_date(row: Tag) -> date:
    year = int(row.get("data-year", "2026"))
    date_title = row.find("div", class_="competition-date-title")
    date_str = (
        date_title.get_text(strip=True)[:5] if isinstance(date_title, Tag) else ""
    )
    try:
        return date.fromisoformat(f"{year}-{date_str}")
    except ValueError:
        return date.today()


def _parse_race_date(cal_href: str) -> date | None:
    """從 Google Calendar href 解析比賽日期。"""
    m = _CAL_DATES_RE.search(cal_href)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_reg_dates(cal_href: str) -> tuple[date | None, date | None]:
    """從 Google Calendar href 解析報名開始與結束日期。"""
    m = _REG_DATE_RE.search(cal_href)
    if not m:
        return None, None
    try:
        start = date.fromisoformat(m.group(1))
        end = date.fromisoformat(m.group(2))
        return start, end
    except ValueError:
        return None, None


def filter_open_events(events: list[RaceEvent], today: date) -> list[RaceEvent]:
    """篩選目前可報名的活動（today 在報名期間內）。"""
    return [
        e
        for e in events
        if e.reg_start is not None
        and e.reg_end is not None
        and e.reg_start <= today <= e.reg_end
    ]


def filter_upcoming_events(
    events: list[RaceEvent], today: date, days: int = 30
) -> list[RaceEvent]:
    """篩選即將開放報名的活動（報名開始在 days 天內，但尚未開始）。"""
    deadline = today + timedelta(days=days)
    return [
        e for e in events if e.reg_start is not None and today < e.reg_start <= deadline
    ]


def filter_events_by_city(events: list[RaceEvent], city: str) -> list[RaceEvent]:
    """依城市篩選活動。city='all' 不篩選。"""
    if city == "all":
        return events
    return [e for e in events if e.city == city]


def fetch_official_url(event_url: str) -> str | None:
    """爬取官方報名連結（帶 in-memory cache 避免重複抓取）。"""
    if event_url in _official_url_cache:
        return _official_url_cache[event_url]
    result = _do_fetch_official_url(event_url)
    _official_url_cache[event_url] = result
    return result


async def fetch_official_url_async(event_url: str) -> str | None:
    """非阻塞版本，使用 asyncio.to_thread 在 thread pool 執行。"""
    return await asyncio.to_thread(fetch_official_url, event_url)


def _do_fetch_official_url(event_url: str) -> str | None:
    """從活動詳情頁找出外部官方報名連結。"""
    try:
        resp = requests.get(
            event_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href", ""))
            if not href.startswith("http"):
                continue
            if any(d in href for d in _SKIP_DOMAINS):
                continue
            text = link.get_text(strip=True)
            if any(kw in text for kw in _REG_KEYWORDS):
                return href
        return None
    except Exception:
        logger.warning(f"fetch_official_url failed for {event_url}")
        return None
