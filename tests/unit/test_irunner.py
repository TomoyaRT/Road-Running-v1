from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.scraper.irunner import (
    _parse_detail,
    _parse_list,
    _parse_reg_times,
    fetch_events,
)

from src.scraper.running_biji import RaceEvent

# ── HTML fixtures ──────────────────────────────────────────────────────────────

_LIST_HTML = """
<html><body>
<div class="competition-list-row" data-year="2026">
  <div class="competition-date">12-19 (週六)</div>
  <div class="competition-place"><span>臺中市</span></div>
  <div class="competition-name"><a href="2026Foodsafetymarathon">2026第二屆食安盃馬拉松</a></div>
  <div class="competition-status"><span>09-19 截止</span></div>
</div>
<div class="competition-list-row" data-year="2026">
  <div class="competition-date">12-12 (週六)</div>
  <div class="competition-place"><span>宜蘭縣</span></div>
  <div class="competition-name"><a href="2026jiaoxihotspring">2026礁溪溫泉馬拉松</a></div>
</div>
<!-- nav 連結不應被解析為活動 -->
<a href="/list">找報名</a>
<a href="https://running.biji.co/">運動筆記</a>
<a href="javascript:;">語言</a>
</body></html>
"""

_DETAIL_HTML = """
<html>
<head>
  <meta property="og:image" content="https://cdntwirunner.biji.co/reg/795/banner.webp"/>
</head>
<body>
<h1 class="comp-title">2026第二屆食安盃馬拉松</h1>
<div class="detail-item">2026-12-19</div>
<div class="detail-item">臺中市中央公園-中央球場</div>
<ul>
  <li>報名時間起2026-06-11 12:00:00迄2026-09-19 23:59:59或額滿為止</li>
</ul>
<strong>全程馬拉松組（42公里）</strong>
<strong>半程馬拉松組（21公里）</strong>
<strong>一般路跑組（10公里）</strong>
<strong>健康趣味組（5公里）</strong>
</body></html>
"""

_DETAIL_NO_CATEGORIES_HTML = """
<html>
<head>
  <meta property="og:image" content="https://cdntwirunner.biji.co/reg/781/img.webp"/>
</head>
<body>
<h1 class="comp-title">2026礁溪溫泉馬拉松</h1>
<div class="detail-item">2026-12-12</div>
<div class="detail-item">宜蘭縣礁溪國小</div>
<ul>
  <li>報名時間起2026-06-02 12:00:00迄2026-08-31 23:59:00或額滿為止</li>
</ul>
</body></html>
"""


# ── _parse_list ────────────────────────────────────────────────────────────────


def test_parse_list_returns_full_urls():
    urls = _parse_list(_LIST_HTML)
    assert "https://irunner.biji.co/2026Foodsafetymarathon" in urls
    assert "https://irunner.biji.co/2026jiaoxihotspring" in urls


def test_parse_list_excludes_nav_links():
    urls = _parse_list(_LIST_HTML)
    assert not any("/list" in u for u in urls)
    assert not any("running.biji.co" in u for u in urls)
    assert not any("javascript" in u for u in urls)


def test_parse_list_deduplicates():
    doubled = _LIST_HTML + _LIST_HTML
    urls = _parse_list(doubled)
    assert urls.count("https://irunner.biji.co/2026Foodsafetymarathon") == 1


# ── _parse_detail ──────────────────────────────────────────────────────────────


def test_parse_detail_name():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.name == "2026第二屆食安盃馬拉松"


def test_parse_detail_race_date():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.race_date == date(2026, 12, 19)


def test_parse_detail_location():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.location == "臺中市中央公園-中央球場"


def test_parse_detail_city_resolved():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.city == "台中市"


def test_parse_detail_image_url():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.image_url == "https://cdntwirunner.biji.co/reg/795/banner.webp"


def test_parse_detail_official_url_is_event_page():
    """立刻報名連結 = 活動頁本身，不跳轉外部。"""
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.official_url == url


def test_parse_detail_source_is_biji():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.source == "biji"


def test_parse_detail_reg_dates():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert event.reg_start == date(2026, 6, 11)
    assert event.reg_end == date(2026, 9, 19)


def test_parse_detail_categories():
    url = "https://irunner.biji.co/2026Foodsafetymarathon"
    event = _parse_detail(_DETAIL_HTML, url)
    assert event is not None
    assert len(event.categories) == 4
    assert "全程馬拉松組（42公里）" in event.categories


def test_parse_detail_no_categories_returns_empty_list():
    url = "https://irunner.biji.co/2026jiaoxihotspring"
    event = _parse_detail(_DETAIL_NO_CATEGORIES_HTML, url)
    assert event is not None
    assert event.categories == []


def test_parse_detail_missing_h1_returns_none():
    html = "<html><body><div class='detail-item'>2026-12-12</div></body></html>"
    assert _parse_detail(html, "https://irunner.biji.co/x") is None


# ── _parse_reg_times ──────────────────────────────────────────────────────────


def test_parse_reg_times_extracts_dates():
    from bs4 import BeautifulSoup

    html = (
        "<ul><li>報名時間起2026-06-11 12:00:00迄2026-09-19 23:59:59或額滿為止</li></ul>"
    )
    soup = BeautifulSoup(html, "html.parser")
    start, end = _parse_reg_times(soup)
    assert start == date(2026, 6, 11)
    assert end == date(2026, 9, 19)


def test_parse_reg_times_no_li_returns_none():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<ul></ul>", "html.parser")
    assert _parse_reg_times(soup) == (None, None)


# ── fetch_events ──────────────────────────────────────────────────────────────


def test_fetch_events_returns_race_events():
    def mock_get(url, **kwargs):
        r = MagicMock()
        r.raise_for_status.return_value = None
        if url == "https://irunner.biji.co/list":
            r.text = _LIST_HTML
        elif "2026Foodsafetymarathon" in url:
            r.text = _DETAIL_HTML
        elif "2026jiaoxihotspring" in url:
            r.text = _DETAIL_NO_CATEGORIES_HTML
        else:
            r.text = ""
        return r

    with patch("src.scraper.irunner.requests.get", side_effect=mock_get):
        events = fetch_events()

    assert len(events) == 2
    assert all(isinstance(e, RaceEvent) for e in events)
    names = [e.name for e in events]
    assert "2026第二屆食安盃馬拉松" in names


def test_fetch_events_returns_empty_on_list_failure():
    with patch("src.scraper.irunner.requests.get", side_effect=Exception("网路錯誤")):
        events = fetch_events()
    assert events == []


def test_fetch_events_skips_failed_detail_page():
    call_count = 0

    def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        r.raise_for_status.return_value = None
        if url == "https://irunner.biji.co/list":
            r.text = _LIST_HTML
        else:
            raise Exception("detail 頁抓取失敗")
        return r

    with patch("src.scraper.irunner.requests.get", side_effect=mock_get):
        events = fetch_events()

    assert events == []
