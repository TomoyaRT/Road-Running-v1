from __future__ import annotations

from datetime import date

from src.scraper.bao_ming import collect_event_urls, parse_detail_html

_LIST_HTML = """
<div class="container">
  <article class="index-event-1">
    <a class="activity-link" href="/eb/content/6917" title="A">img</a>
    <a class="activity-link" href="/eb/content/6917#reg" title="A">標題</a>
  </article>
  <div class="card"><a class="activity-link" href="/eb/content/7026" title="B">B</a></div>
  <a class="other-link" href="/eb/content/9999">不是活動連結</a>
</div>
"""

_DETAIL_HTML = """
<html><head>
  <meta property="og:title" content="2026 POCARI SWEAT RUN 寶礦力路跑"/>
  <meta property="og:image" content="https://bao-ming.com/eb/upload/activity/7013/banner.jpg"/>
</head><body>
  <h6 class="text-dark">活動日期：</h6><h5>2026年10月18日(星期日)</h5>
  <div>報名日期：2026年6月1日12:00起至2026年8月14日23:59截止 (額滿為止)</div>
  <strong>活動地點</strong><div>臺北市大佳河濱公園蛋型廣場</div>
  <h3>主辦單位：</h3><div>金車大塚股份有限公司、寶康行銷股份有限公司</div>
</body></html>
"""

_DETAIL_URL = "https://bao-ming.com/eb/content/7013"


def test_collect_event_urls_dedups_and_filters():
    urls = collect_event_urls(_LIST_HTML)
    assert urls == [
        "https://bao-ming.com/eb/content/6917",
        "https://bao-ming.com/eb/content/7026",
    ]


def test_parse_detail_extracts_name():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.name == "2026 POCARI SWEAT RUN 寶礦力路跑"


def test_parse_detail_extracts_race_date():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.race_date == date(2026, 10, 18)


def test_parse_detail_extracts_reg_dates():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.reg_start == date(2026, 6, 1)
    assert event.reg_end == date(2026, 8, 14)


def test_parse_detail_extracts_location_and_city():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert "大佳河濱公園" in event.location
    assert event.city == "台北市"  # 臺→台 正規化


def test_parse_detail_extracts_organizer():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.organizer is not None
    assert "金車大塚" in event.organizer


def test_parse_detail_sets_official_url_image_and_source():
    event = parse_detail_html(_DETAIL_HTML, _DETAIL_URL)
    assert event is not None
    assert event.official_url == _DETAIL_URL
    assert event.image_url == "https://bao-ming.com/eb/upload/activity/7013/banner.jpg"
    assert event.source == "baoming"


def test_parse_detail_returns_none_without_race_date():
    html = "<html><body><p>沒有日期資訊</p></body></html>"
    assert parse_detail_html(html, _DETAIL_URL) is None
