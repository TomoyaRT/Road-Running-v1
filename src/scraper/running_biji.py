from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TypeVar
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from src.utils import tw_today

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

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
    "running.biji.co",
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
_OFFICIAL_KEYWORDS = {"官方網站", "活動官方網站"}
_BROCHURE_KEYWORDS = {"活動簡章", "簡章", "賽事簡章"}

# 專用 thread pool，避免 1-CPU Cloud Run 上 asyncio 預設 pool 只有 ~5 條而拖慢爬蟲
_ENRICH_EXECUTOR = ThreadPoolExecutor(max_workers=16)


async def _run_in_pool(fn: Callable[..., _T], *args: object) -> _T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_ENRICH_EXECUTOR, fn, *args)


# 非路跑活動關鍵字（自行車、鐵人、游泳等），用於過濾掉非路跑賽事
_NON_RUNNING_KEYWORDS = (
    "自行車",
    "單車",
    "鐵人",
    "三鐵",
    "三項",
    "游泳",
    "泳渡",
    "登山",
)


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
    organizer: str | None = None
    categories: list[str] = field(default_factory=list)
    source: str = "biji"


@dataclass
class _BijiEventDetail:
    official_url: str | None
    image_url: str | None
    organizer: str | None
    categories: list[str]


_biji_detail_cache: dict[str, _BijiEventDetail] = {}


def clear_enrich_cache() -> None:
    """清除 biji 活動詳情快取（每次 crawl 前呼叫，避免同一 instance 服務過期資料）。"""
    _biji_detail_cache.clear()


def _normalize_city(name: str) -> str:
    return name.replace("臺", "台")


def extract_city(location: str) -> str:
    """從地點字串中提取台灣縣市名稱（前綴比對，找不到回原字串）。"""
    location = _normalize_city(location)
    for city in _TW_CITIES:
        if location.startswith(city):
            return city
    return location


def find_city(text: str) -> str:
    """在任意文字中尋找最先出現的台灣縣市名稱（找不到回空字串）。

    用於地址/場地等城市名非開頭的文字（例：「國立高雄科技大學…高雄市…」）。
    """
    text = _normalize_city(text)
    best_pos = len(text)
    best = ""
    for city in _TW_CITIES:
        pos = text.find(city)
        if 0 <= pos < best_pos:
            best_pos = pos
            best = city
    return best


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
        if "list-title" in (row.get("class") or []):
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
    year = int(str(row.get("data-year") or "2026"))
    date_title = row.find("div", class_="competition-date-title")
    date_str = (
        date_title.get_text(strip=True)[:5] if isinstance(date_title, Tag) else ""
    )
    try:
        return date.fromisoformat(f"{year}-{date_str}")
    except ValueError:
        return tw_today()


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
    return [e for e in events if _normalize_city(e.city) == _normalize_city(city)]


def filter_running_events(events: list[RaceEvent]) -> list[RaceEvent]:
    """只保留路跑活動，排除自行車、鐵人三項、游泳等非路跑賽事。"""
    return [e for e in events if not any(kw in e.name for kw in _NON_RUNNING_KEYWORDS)]


_BIJI_DEFAULT_IMAGE_FRAGMENT = "competition_470x246.jpg"


def extract_og_image(html: str, base_url: str = "") -> str | None:
    """從 HTML 取出活動封面圖（og:image property > og:image name > twitter:image）。
    排除 biji 預設圖與 favicon；相對路徑需提供 base_url 才能補全。
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for meta in (
        soup.find("meta", property="og:image"),
        soup.find("meta", attrs={"name": "og:image"}),
        soup.find("meta", attrs={"name": "twitter:image"}),
    ):
        if isinstance(meta, Tag):
            content = meta.get("content")
            if content:
                candidates.append(str(content))
    for raw in candidates:
        if raw.endswith(".ico") or "favicon" in raw:
            continue
        if _BIJI_DEFAULT_IMAGE_FRAGMENT in raw:
            continue
        if not raw.startswith("http"):
            if base_url:
                return urljoin(base_url, raw)
            continue
        return raw
    return None


def _is_skipped_url(href: str) -> bool:
    """判斷連結是否該略過：社群/搜尋等雜訊網域，或 biji 自家推廣的裸首頁。

    biji 詳情頁有個含「報名」字樣、指向 irunner 首頁（path 為空）的推廣連結，
    會遮蔽真正的官方連結；但 irunner.biji.co/<活動slug> 這類個別活動頁要保留。
    """
    if any(d in href for d in _SKIP_DOMAINS):
        return True
    parsed = urlparse(href)
    if parsed.netloc.endswith(".biji.co") and parsed.path.strip("/") == "":
        return True
    return False


def _extract_reg_url(soup: BeautifulSoup) -> str | None:
    """從活動詳情頁找出外部官方報名、官網或簡章連結（報名 > 官網 > 簡章）。"""
    for keyword_set in (_REG_KEYWORDS, _OFFICIAL_KEYWORDS, _BROCHURE_KEYWORDS):
        for link in soup.find_all("a", href=True):
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href", ""))
            if not href.startswith("http"):
                continue
            if _is_skipped_url(href):
                continue
            if any(kw in link.get_text(strip=True) for kw in keyword_set):
                return href
    return None


_ORGANIZER_LABELS = {"主辦單位", "主辦"}


def _extract_organizer(soup: BeautifulSoup) -> str | None:
    """從活動詳情頁 HTML 提取主辦單位。"""
    for cell in soup.find_all(["td", "th", "dt", "span"]):
        if cell.get_text(strip=True) in _ORGANIZER_LABELS:
            nxt = cell.find_next_sibling()
            if nxt:
                text = nxt.get_text(strip=True)
                if text and len(text) < 100:
                    return text
    return None


_CATEGORY_PLACEHOLDERS = {"請選擇", "參賽組別", "請選擇組別"}


def _extract_categories(soup: BeautifulSoup) -> list[str]:
    """從 biji 活動詳情頁的 <select><option> 取出完整路跑組別。"""
    select: Tag | None = None
    for sel in soup.find_all("select"):
        if not isinstance(sel, Tag):
            continue
        for opt in sel.find_all("option"):
            if isinstance(opt, Tag) and "參賽組別" in opt.get_text(strip=True):
                select = sel
                break
        if select:
            break

    if select is None:
        all_selects = [s for s in soup.find_all("select") if isinstance(s, Tag)]
        if len(all_selects) == 1:
            select = all_selects[0]

    if select is None:
        return []

    result = []
    for opt in select.find_all("option"):
        if not isinstance(opt, Tag):
            continue
        text = opt.get_text(strip=True)
        if not text or len(text) >= 30:
            continue
        if any(p in text for p in _CATEGORY_PLACEHOLDERS):
            continue
        tokens = text.split()
        deduped = [t for i, t in enumerate(tokens) if i == 0 or tokens[i - 1] != t]
        result.append(" ".join(deduped))
    return result


def _fetch_biji_detail_sync(event_url: str) -> _BijiEventDetail:
    if event_url in _biji_detail_cache:
        return _biji_detail_cache[event_url]
    result = _do_fetch_biji_detail(event_url)
    _biji_detail_cache[event_url] = result
    return result


async def _fetch_biji_detail_async(event_url: str) -> _BijiEventDetail:
    return await _run_in_pool(_fetch_biji_detail_sync, event_url)


def _do_fetch_biji_detail(event_url: str) -> _BijiEventDetail:
    """從 biji 活動詳情頁取得：官方報名連結、主辦單位、組別；再從報名站抓 og:image。"""
    try:
        resp = requests.get(
            event_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        official_url = _extract_reg_url(soup)

        image_url: str | None = None
        if official_url:
            try:
                reg_resp = requests.get(
                    official_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
                )
                reg_resp.raise_for_status()
                image_url = extract_og_image(reg_resp.text, base_url=official_url)
            except Exception:
                logger.warning(f"fetch og:image from {official_url} failed")

        return _BijiEventDetail(
            official_url=official_url,
            image_url=image_url,
            organizer=_extract_organizer(soup),
            categories=_extract_categories(soup),
        )
    except Exception:
        logger.warning(f"fetch_biji_detail failed for {event_url}")
        return _BijiEventDetail(
            official_url=None, image_url=None, organizer=None, categories=[]
        )


async def enrich_event(event: RaceEvent) -> RaceEvent:
    """從 biji 活動詳情頁補齊報名連結、封面圖、主辦單位、組別（就地更新 event）。"""
    detail = await _fetch_biji_detail_async(event.url)
    event.official_url = detail.official_url
    event.image_url = detail.image_url
    if detail.organizer:
        event.organizer = detail.organizer
    if detail.categories:
        event.categories = detail.categories
    return event


async def enrich_events(events: list[RaceEvent]) -> list[RaceEvent]:
    """並行補齊所有活動的報名連結、封面圖、主辦單位、組別。"""
    await asyncio.gather(*(enrich_event(e) for e in events))
    return events
