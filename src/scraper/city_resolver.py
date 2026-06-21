from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "city_county.json"

# 簡→繁字元對照（封閉集合：僅台灣縣市區名中出現的字元）
# 常見路跑場館地標→縣市（不含縣市名、無法靠 donma 資料解析的地標）
_VENUE_TO_CITY: dict[str, str] = {
    "大佳河濱公園": "台北市",
    "國父紀念館": "台北市",
    "台北田徑場": "台北市",
    "陽明山": "台北市",
    "烏來": "新北市",
    "石門水庫": "桃園市",
    "日月潭": "南投縣",
    "溪頭": "南投縣",
    "合歡山": "南投縣",
    "墾丁": "屏東縣",
    "太魯閣": "花蓮縣",
    "阿里山": "嘉義縣",
    "宜蘭運動公園": "宜蘭縣",
    "左營國家": "高雄市",
    "高雄國家": "高雄市",
}

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

    for venue, city in _VENUE_TO_CITY.items():
        if venue in normalized:
            return city

    cities, area_to_city = _load_data()

    for city in cities:
        if city in normalized:
            return city

    for area_name in sorted(area_to_city, key=len, reverse=True):
        if area_name in normalized:
            return area_to_city[area_name]

    return ""
