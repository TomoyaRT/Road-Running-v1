from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "city_county.json"

# 簡→繁字元對照（封閉集合：僅台灣縣市區名中出現的字元）
_S2T: dict[str, str] = {
    "义": "義",  # 嘉義
    "云": "雲",  # 雲林
    "园": "園",  # 桃園
    "连": "連",  # 連江
    "县": "縣",
    "区": "區",
    "镇": "鎮",
    "乡": "鄉",
    "东": "東",
    "湾": "灣",
}


def _normalize(text: str) -> str:
    """臺→台、簡體字元→繁體（封閉集合）、去首尾空白。"""
    text = text.replace("臺", "台")
    for s, t in _S2T.items():
        text = text.replace(s, t)
    return text.strip()


@lru_cache(maxsize=1)
def _load_data() -> tuple[list[str], dict[str, str]]:
    """回傳 (正規城市名列表由長至短, 區域名→城市名 反查表)。"""
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    cities: list[str] = []
    area_to_city: dict[str, str] = {}
    for entry in raw:
        city = _normalize(entry["CityName"])
        cities.append(city)
        for area in entry["AreaList"]:
            area_to_city[_normalize(area["AreaName"])] = city
    cities.sort(key=len, reverse=True)
    return cities, area_to_city


def resolve_city(location: str) -> str:
    """從地點字串解析正規縣市名（台字版）。找不到回空字串。"""
    if not location:
        return ""
    normalized = _normalize(location)
    cities, area_to_city = _load_data()

    for city in cities:
        if city in normalized:
            return city

    for area_name in sorted(area_to_city, key=len, reverse=True):
        if area_name in normalized:
            return area_to_city[area_name]

    return ""
