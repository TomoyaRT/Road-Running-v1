from __future__ import annotations

from datetime import date

from src.scraper.ctrun import _extract_categories, collect_event_urls, parse_detail_html

_LIST_HTML = """
<div class="pri_table_list">
  <a href="Activity?EventMain_ID=334">活動照片</a>
  <a href="Activity/?EventMain_ID=334&Article_ID=5">2026 嘉義雙潭星光路跑</a>
  <a href="https://www.ctrun.com.tw/Activity?EventMain_ID=291">越野賽</a>
</div>
"""

_DETAIL_HTML = """
<html><head>
  <meta property="og:title" content="2026 嘉義雙潭 - 星光路跑 - 全統運動報名網"/>
  <meta property="og:image" content="https://ctrunstorage.blob.core.windows.net/images/BannerImage/x.jpg"/>
</head><body>
  <p>注意事項：一切以主辦單位公告為準。</p>
  <div>活動資訊 活動名稱 2026 嘉義雙潭星光路跑 活動日期 2026年08月08日（星期六）
  報名時間 2026/06/11(四)~2026/07/15(三) 活動地點 嘉義市立蘭潭國民中學(嘉義市東區民權東路32號)
  主辦單位 嘉義市政府 承辦單位 嘉義市西區公所</div>
  <table>
    <tr><td>報名組別</td><td>13K挑戰組</td><td>6.5K樂跑組</td><td>3.5K體驗組</td></tr>
    <tr><td>報名費用</td><td>NT$1080</td><td>NT$980</td><td>NT$880</td></tr>
  </table>
</body></html>
"""

_DETAIL_URL = "https://www.ctrun.com.tw/Activity?EventMain_ID=334"


def test_collect_event_urls_canonicalizes_and_dedups():
    urls = collect_event_urls(_LIST_HTML)
    assert urls == [
        "https://www.ctrun.com.tw/Activity?EventMain_ID=334",
        "https://www.ctrun.com.tw/Activity?EventMain_ID=291",
    ]


def test_parse_detail_extracts_name_without_site_suffix():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.name == "2026 嘉義雙潭星光路跑"


def test_parse_detail_extracts_race_date():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.race_date == date(2026, 8, 8)


def test_parse_detail_extracts_slash_reg_dates():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.reg_start == date(2026, 6, 11)
    assert event.reg_end == date(2026, 7, 15)


def test_parse_detail_extracts_city_from_address():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.city == "嘉義市"


def test_parse_detail_city_uses_resolver_for_disambiguation():
    """新竹縣竹北市 → 新竹縣（不是新竹市）。"""
    html = _DETAIL_HTML.replace(
        "嘉義市立蘭潭國民中學(嘉義市東區民權東路32號)", "新竹縣竹北市光明路123號"
    )
    event = parse_detail_html(html, _DETAIL_URL)
    assert event is not None
    assert event.city == "新竹縣"


def test_parse_detail_organizer_ignores_disclaimer_noise():
    """頁面前段有『以主辦單位公告為準』的雜訊，須取活動資訊區塊內的真正主辦。"""
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.organizer == "嘉義市政府"


def test_parse_detail_sets_official_url_image_and_source():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.official_url == _DETAIL_URL
    assert event.image_url is not None and event.image_url.endswith("BannerImage/x.jpg")
    assert event.source == "ctrun"


def test_parse_detail_returns_none_without_race_date():
    assert parse_detail_html("<html><body>無資訊</body></html>", _DETAIL_URL) is None


def test_parse_detail_date_robust_when_name_contains_label_substring():
    """活動名稱若含『活動日期』等標籤字串，日期仍須正確解析（不被截斷而漏掉活動）。"""
    html = """
    <html><body>
      <div>活動資訊 活動名稱 2026 活動日期主題紀念路跑
      活動日期 2026年09月20日（星期日）
      報名時間 2026/06/01(一)~2026/07/31(五)
      活動地點 台中市政府 主辦單位 台中市政府</div>
    </body></html>
    """
    event = parse_detail_html(html, _DETAIL_URL)
    assert event is not None
    assert event.race_date == date(2026, 9, 20)
    assert event.reg_start == date(2026, 6, 1)


def test_parse_detail_extracts_categories():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert "13K挑戰組" in event.categories
    assert "6.5K樂跑組" in event.categories
    assert "3.5K體驗組" in event.categories


def test_extract_categories_matches_報名組別_header():
    from bs4 import BeautifulSoup

    html = "<table><tr><td>報名組別</td><td>全馬</td><td>半馬</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    cats = _extract_categories(soup)
    assert cats == ["全馬", "半馬"]


def test_extract_categories_matches_組別_header():
    from bs4 import BeautifulSoup

    html = "<table><tr><td>組別</td><td>10K組</td><td>5K組</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    cats = _extract_categories(soup)
    assert cats == ["10K組", "5K組"]


def test_extract_categories_returns_empty_when_no_table():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html><body><p>無組別</p></body></html>", "html.parser")
    assert _extract_categories(soup) == []


def test_extract_categories_filters_non_distance_text():
    """年齡分組、行銷文案等非距離型組別不應出現在結果裡。"""
    from bs4 import BeautifulSoup

    html = "<table><tr><td>組別</td><td>21公里半馬</td><td>未滿18歲組</td><td>VIP紀念組</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    cats = _extract_categories(soup)
    assert "21公里半馬" in cats
    assert "未滿18歲組" not in cats
    assert "VIP紀念組" not in cats
