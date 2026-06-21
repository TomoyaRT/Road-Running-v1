from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.scraper.joinnow import (
    _parse_categories,
    _parse_detail,
    _parse_event_urls,
    fetch_events,
)
from src.scraper.running_biji import RaceEvent

# ── HTML fixtures ──────────────────────────────────────────────────────────────

_HOME_HTML = """
<html><body>
<a href="run-step1.php?cnt_id=132">路跑A</a>
<a href="run-step1.php?cnt_id=132">路跑A重複</a>
<a href="run-step1.php?cnt_id=137">路跑B</a>
<a href="index.php">首頁</a>
<a href="https://www.facebook.com/">FB</a>
</body></html>
"""

_DETAIL_HTML = """
<html>
<head>
  <meta property="og:image" content="https://www.joinnow.com.tw/manager_admin/upload_file/132/img.jpg"/>
  <meta property="og:title" content="2026浪漫台三線新店老街路跑賽|一起報名!活動報名系統"/>
</head>
<body>
  <h1>2026浪漫台三線新店老街路跑賽</h1>
  <li>
    <span class="liSpan">活動名稱</span>2026浪漫台三線新店老街路跑賽
  </li>
  <li>
    <span class="liSpan">活動地點</span>苗栗縣獅潭鄉五文宮
  </li>
  <li class="run-bLiS">
    <div><span class="liSpan">活動日期</span>2026/09/06(日)</div>
    <div><span class="liSpan">報名期限</span>2026/07/24 截止還剩下34天</div>
  </li>
  <li>
    <span class="liSpan">報名項目</span>
    <table>
      <tr><th>項目</th><th>報名費用</th><th>報名狀態</th></tr>
      <tr><td>全馬組42.8 Km</td><td>1150元</td><td>可以報名</td></tr>
      <tr><td>健跑組10.7 Km</td><td>700元</td><td>可以報名</td></tr>
      <tr><td>親子組5Km</td><td>600元</td><td>可以報名</td></tr>
    </table>
  </li>
</body>
</html>
"""

_DETAIL_URL = "https://www.joinnow.com.tw/run-step1.php?cnt_id=132"


# ── _parse_event_urls ─────────────────────────────────────────────────────────


def test_parse_event_urls_returns_full_urls():
    urls = _parse_event_urls(_HOME_HTML)
    assert "https://www.joinnow.com.tw/run-step1.php?cnt_id=132" in urls
    assert "https://www.joinnow.com.tw/run-step1.php?cnt_id=137" in urls


def test_parse_event_urls_deduplicates():
    urls = _parse_event_urls(_HOME_HTML)
    assert urls.count("https://www.joinnow.com.tw/run-step1.php?cnt_id=132") == 1


def test_parse_event_urls_excludes_non_event_links():
    urls = _parse_event_urls(_HOME_HTML)
    assert not any("index.php" in u for u in urls)
    assert not any("facebook" in u for u in urls)


# ── _parse_detail ─────────────────────────────────────────────────────────────


def test_parse_detail_name():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.name == "2026浪漫台三線新店老街路跑賽"


def test_parse_detail_race_date():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.race_date == date(2026, 9, 6)


def test_parse_detail_location():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.location == "苗栗縣獅潭鄉五文宮"


def test_parse_detail_city():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.city == "苗栗縣"


def test_parse_detail_reg_end():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.reg_end == date(2026, 7, 24)


def test_parse_detail_reg_start_is_none():
    """joinnow 只有報名期限，無報名開始日期。"""
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.reg_start is None


def test_parse_detail_image_url():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert "joinnow.com.tw" in (event.image_url or "")


def test_parse_detail_official_url_is_event_page():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.official_url == _DETAIL_URL


def test_parse_detail_source():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.source == "joinnow"


def test_parse_detail_categories():
    event = _parse_detail(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert "全馬組42.8 Km" in event.categories
    assert "健跑組10.7 Km" in event.categories


def test_parse_detail_missing_h1_returns_none():
    html = "<html><body><p>無標題</p></body></html>"
    assert _parse_detail(html, _DETAIL_URL) is None


def test_parse_detail_missing_race_date_returns_none():
    html = "<html><body><h1>有名稱但無日期</h1></body></html>"
    assert _parse_detail(html, _DETAIL_URL) is None


# ── _parse_categories ─────────────────────────────────────────────────────────


def test_parse_categories_extracts_first_column():
    from bs4 import BeautifulSoup

    html = """<table>
      <tr><th>項目</th><th>報名費用</th></tr>
      <tr><td>全馬</td><td>1000元</td></tr>
      <tr><td>半馬</td><td>800元</td></tr>
    </table>"""
    soup = BeautifulSoup(html, "html.parser")
    cats = _parse_categories(soup)
    assert cats == ["全馬", "半馬"]


def test_parse_categories_returns_empty_when_no_table():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<p>無組別</p>", "html.parser")
    assert _parse_categories(soup) == []


def test_parse_categories_filters_non_distance_text():
    """非距離型項目（親子同樂VIP等）不應出現在結果裡。"""
    from bs4 import BeautifulSoup

    html = """<table>
      <tr><th>項目</th><th>費用</th></tr>
      <tr><td>半馬組21Km</td><td>800</td></tr>
      <tr><td>親子同樂VIP體驗</td><td>500</td></tr>
    </table>"""
    soup = BeautifulSoup(html, "html.parser")
    cats = _parse_categories(soup)
    assert "半馬組21Km" in cats
    assert "親子同樂VIP體驗" not in cats


# ── fetch_events ──────────────────────────────────────────────────────────────


def test_fetch_events_returns_events():
    def mock_get(url, **kwargs):
        r = MagicMock()
        r.raise_for_status.return_value = None
        if url == "https://www.joinnow.com.tw/":
            r.text = _HOME_HTML
        else:
            r.text = _DETAIL_HTML
        return r

    with patch("src.scraper.joinnow.requests.get", side_effect=mock_get):
        events = fetch_events()

    assert len(events) == 2
    assert all(isinstance(e, RaceEvent) for e in events)


def test_fetch_events_returns_empty_on_failure():
    with patch("src.scraper.joinnow.requests.get", side_effect=Exception("err")):
        assert fetch_events() == []
