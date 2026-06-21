from __future__ import annotations

from src.scraper.city_resolver import resolve_city


def test_trad_taipei_normalized():
    assert resolve_city("臺北市") == "台北市"


def test_tai_taipei_unchanged():
    assert resolve_city("台北市") == "台北市"


def test_trad_tainan_with_area():
    assert resolve_city("臺南市安平區") == "台南市"


def test_taoyuan_direct():
    assert resolve_city("桃園市") == "桃園市"


def test_hsinchu_city_by_district():
    """東區屬新竹市"""
    assert resolve_city("新竹市東區") == "新竹市"


def test_hsinchu_county_by_area():
    """竹北市是新竹縣鄉鎮市區，不是新竹市"""
    assert resolve_city("新竹縣竹北市光明六路") == "新竹縣"


def test_chiayi_city():
    assert resolve_city("嘉義市東區") == "嘉義市"


def test_chiayi_county_by_area():
    """太保市屬嘉義縣"""
    assert resolve_city("嘉義縣太保市") == "嘉義縣"


def test_kaohsiung_with_district():
    assert resolve_city("高雄市鼓山區") == "高雄市"


def test_unknown_returns_empty():
    assert resolve_city("未知地點") == ""


def test_empty_returns_empty():
    assert resolve_city("") == ""


def test_simplified_chiayi():
    """嘉义市（簡體）→ 嘉義市"""
    assert resolve_city("嘉义市") == "嘉義市"


def test_simplified_yunlin():
    """云林县（簡體）→ 雲林縣"""
    assert resolve_city("云林县") == "雲林縣"


def test_area_only_resolves_to_city():
    """只給鄉鎮市區名，能反查到所屬縣市"""
    assert resolve_city("竹北市") == "新竹縣"


def test_tainan_area_resolves():
    assert resolve_city("台南市安平區") == "台南市"


# ── T2: 場館靜態字典 ──────────────────────────────────────────────────────────


def test_venue_大佳河濱公園():
    """大佳河濱公園（台北市常見路跑場地）不含縣市名，應解析為台北市。"""
    assert resolve_city("大佳河濱公園蛋型廣場") == "台北市"


def test_venue_日月潭():
    assert resolve_city("日月潭風景區") == "南投縣"


def test_venue_墾丁():
    assert resolve_city("墾丁大街入口") == "屏東縣"


def test_venue_太魯閣():
    assert resolve_city("太魯閣國家公園") == "花蓮縣"


def test_venue_still_falls_back_to_city_prefix():
    """場館字典不影響現有縣市名前綴邏輯。"""
    assert resolve_city("台北市信義區") == "台北市"


def test_venue_still_falls_back_to_area_lookup():
    """場館字典不影響現有鄉鎮反查邏輯。"""
    assert resolve_city("竹北市光明路") == "新竹縣"
