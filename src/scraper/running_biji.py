from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

CATEGORY_KEYWORDS = re.compile(
    r"公里|[Kk][Mm]|\d+[Kk]|馬拉松|全馬|半馬|路跑|接力|全程|半程|越野"
)

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

_BIJI_DEFAULT_IMAGE_FRAGMENT = "competition_470x246.jpg"


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


def _normalize_city(name: str) -> str:
    return name.replace("臺", "台")


def extract_city(location: str) -> str:
    """從地點字串中提取台灣縣市名稱（前綴比對，找不到回原字串）。"""
    location = _normalize_city(location)
    for city in _TW_CITIES:
        if location.startswith(city):
            return city
    return location


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
