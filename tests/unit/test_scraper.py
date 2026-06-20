from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.scraper.running_biji import (
    RaceEvent,
    _BijiEventDetail,
    _do_fetch_biji_detail,
    _extract_categories,
    _extract_organizer,
    _extract_reg_url,
    _normalize_city,
    _parse_reg_dates,
    enrich_event,
    enrich_events,
    extract_city,
    extract_og_image,
    filter_events_by_city,
    filter_open_events,
    filter_running_events,
    filter_upcoming_events,
    parse_events_html,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

OPEN_CAL_HREF = (
    "https://www.google.com/calendar/event?action=TEMPLATE"
    "&text=Open+Event"
    "&dates=20261115/20261116"
    "&location=台北市"
    "&details=【Open Event】%0A報名日期:2026-06-01 00:00:00~2026-08-31 23:59:00%0A"
    "<a href='https://running.biji.co/'>詳情</a>"
)

UPCOMING_CAL_HREF = (
    "https://www.google.com/calendar/event?action=TEMPLATE"
    "&text=Upcoming+Event"
    "&dates=20261201/20261202"
    "&location=台中市"
    "&details=【Upcoming Event】%0A報名日期:2026-07-10 00:00:00~2026-09-30 23:59:00%0A"
    "<a href='https://running.biji.co/'>詳情</a>"
)

CLOSED_CAL_HREF = (
    "https://www.google.com/calendar/event?action=TEMPLATE"
    "&text=Closed+Event"
    "&dates=20260613/20260614"
    "&location=高雄市"
    "&details=【Closed Event】%0A報名日期:2026-01-01 00:00:00~2026-03-31 23:59:00%0A"
    "<a href='https://running.biji.co/'>詳情</a>"
)

SAMPLE_HTML = f"""
<html><body>
<div id="competition-inner">
  <div class="competition-list-row list-title competition_list_title">
    <div class="competition-name">賽事/活動</div>
  </div>
  <div class="competition-list-row" data-year="2026" data-month="202611" id="cp_part_11111">
    <div class="competition-date competition-note flex items-center">
      <div class="competition-date-title">11-15 (週 日)</div>
      <a class="competition-date-calendar note-item" href="{OPEN_CAL_HREF}">
        <img src="/static/images/calendar.png"/>
      </a>
    </div>
    <div class="competition-place"><span>台北市</span></div>
    <div class="competition-name">
      <a href="/index.php?q=competition&amp;act=info&amp;cid=11111">Open Event 台北馬</a>
    </div>
    <div class="competition-status"><span>報名中</span></div>
  </div>
  <div class="competition-list-row" data-year="2026" data-month="202612" id="cp_part_22222">
    <div class="competition-date competition-note flex items-center">
      <div class="competition-date-title">12-01 (週 二)</div>
      <a class="competition-date-calendar note-item" href="{UPCOMING_CAL_HREF}">
        <img src="/static/images/calendar.png"/>
      </a>
    </div>
    <div class="competition-place"><span>台中市</span></div>
    <div class="competition-name">
      <a href="/index.php?q=competition&amp;act=info&amp;cid=22222">Upcoming Event 台中賽</a>
    </div>
    <div class="competition-status"><span>即將開報</span></div>
  </div>
  <div class="competition-list-row" data-year="2026" data-month="202606" id="cp_part_33333">
    <div class="competition-date competition-note flex items-center">
      <div class="competition-date-title">06-13 (週 六)</div>
      <a class="competition-date-calendar note-item" href="{CLOSED_CAL_HREF}">
        <img src="/static/images/calendar.png"/>
      </a>
    </div>
    <div class="competition-place"><span>高雄市</span></div>
    <div class="competition-name">
      <a href="/index.php?q=competition&amp;act=info&amp;cid=33333">Closed Event 高雄賽</a>
    </div>
    <div class="competition-status"><span>已截止報名</span></div>
  </div>
  <div class="competition-list-row" data-year="2026" data-month="202609" id="cp_part_44444">
    <div class="competition-date competition-note flex items-center">
      <div class="competition-date-title">09-20 (週 日)</div>
    </div>
    <div class="competition-place"><span>新北市</span></div>
    <div class="competition-name">
      <a href="/index.php?q=competition&amp;act=info&amp;cid=44444">No Calendar Event</a>
    </div>
    <div class="competition-status"><span>報名中</span></div>
  </div>
</div>
</body></html>
"""

TODAY = date(2026, 6, 19)


# ── _parse_reg_dates ──────────────────────────────────────────────────────────


def test_parse_reg_dates_returns_start_and_end():
    start, end = _parse_reg_dates(OPEN_CAL_HREF)
    assert start == date(2026, 6, 1)
    assert end == date(2026, 8, 31)


def test_parse_reg_dates_returns_none_when_missing():
    href = "https://www.google.com/calendar/event?text=No+Dates&dates=20260613/20260614"
    start, end = _parse_reg_dates(href)
    assert start is None
    assert end is None


# ── parse_events_html ─────────────────────────────────────────────────────────


def test_parse_events_html_skips_header_row():
    events = parse_events_html(SAMPLE_HTML)
    names = [e.name for e in events]
    assert "賽事/活動" not in names


def test_parse_events_html_parses_all_data_rows():
    events = parse_events_html(SAMPLE_HTML)
    assert len(events) == 4


def test_parse_events_html_event_fields():
    events = parse_events_html(SAMPLE_HTML)
    open_event = next(e for e in events if "Open" in e.name)
    assert open_event.location == "台北市"
    assert open_event.race_date == date(2026, 11, 15)
    assert open_event.reg_start == date(2026, 6, 1)
    assert open_event.reg_end == date(2026, 8, 31)
    assert "cid=11111" in open_event.url


def test_parse_events_html_event_without_calendar_href():
    events = parse_events_html(SAMPLE_HTML)
    no_cal = next(e for e in events if "No Calendar" in e.name)
    assert no_cal.reg_start is None
    assert no_cal.reg_end is None


# ── filter_open_events ────────────────────────────────────────────────────────


def test_filter_open_events_returns_events_in_registration_period():
    events = parse_events_html(SAMPLE_HTML)
    open_events = filter_open_events(events, TODAY)
    names = [e.name for e in open_events]
    assert any("Open" in n for n in names)
    assert not any("Closed" in n for n in names)
    assert not any("Upcoming" in n for n in names)


def test_filter_open_events_excludes_no_reg_date():
    events = parse_events_html(SAMPLE_HTML)
    open_events = filter_open_events(events, TODAY)
    assert not any("No Calendar" in e.name for e in open_events)


# ── filter_upcoming_events ────────────────────────────────────────────────────


def test_filter_upcoming_events_returns_events_opening_within_30_days():
    events = parse_events_html(SAMPLE_HTML)
    upcoming = filter_upcoming_events(events, TODAY, days=30)
    names = [e.name for e in upcoming]
    # 2026-07-10 開報，距 TODAY=2026-06-19 為 21 天，應在 30 天內
    assert any("Upcoming" in n for n in names)
    assert not any("Open" in n for n in names)
    assert not any("Closed" in n for n in names)


def test_filter_upcoming_events_excludes_beyond_days():
    events = parse_events_html(SAMPLE_HTML)
    # 縮短到 10 天，2026-07-10 開報距今 21 天，應排除
    upcoming = filter_upcoming_events(events, TODAY, days=10)
    assert not any("Upcoming" in n for n in upcoming)


# ── extract_city ──────────────────────────────────────────────────────────────


def test_extract_city_recognizes_taipei():
    assert extract_city("台北市中山區") == "台北市"


def test_extract_city_recognizes_exact_city():
    assert extract_city("高雄市") == "高雄市"


def test_extract_city_recognizes_county():
    assert extract_city("花蓮縣壽豐鄉") == "花蓮縣"


def test_extract_city_returns_full_string_when_unknown():
    assert extract_city("某未知地點") == "某未知地點"


def test_parse_row_sets_city_from_location():
    events = parse_events_html(SAMPLE_HTML)
    open_event = next(e for e in events if "Open" in e.name)
    assert open_event.city == "台北市"


# ── filter_events_by_city ─────────────────────────────────────────────────────


def test_filter_events_by_city_returns_matching_events():
    events = parse_events_html(SAMPLE_HTML)
    taipei_events = filter_events_by_city(events, "台北市")
    assert all(e.city == "台北市" for e in taipei_events)
    assert len(taipei_events) >= 1


def test_filter_events_by_city_all_returns_all():
    events = parse_events_html(SAMPLE_HTML)
    result = filter_events_by_city(events, "all")
    assert result == events


def test_filter_events_by_city_excludes_other_cities():
    events = parse_events_html(SAMPLE_HTML)
    taipei_only = filter_events_by_city(events, "台北市")
    assert not any(e.city != "台北市" for e in taipei_only)


# ── _normalize_city ───────────────────────────────────────────────────────────


def test_normalize_city_replaces_trad_with_simplified():
    assert _normalize_city("臺北市") == "台北市"
    assert _normalize_city("臺中市") == "台中市"
    assert _normalize_city("臺南市") == "台南市"
    assert _normalize_city("臺東縣") == "台東縣"


def test_normalize_city_leaves_simplified_unchanged():
    assert _normalize_city("台北市") == "台北市"
    assert _normalize_city("高雄市") == "高雄市"


# ── extract_city with 臺 ──────────────────────────────────────────────────────


def test_extract_city_normalizes_trad_taipei():
    assert extract_city("臺北市大安區") == "台北市"


def test_extract_city_normalizes_trad_taichung():
    assert extract_city("臺中市") == "台中市"


def test_extract_city_normalizes_trad_tainan():
    assert extract_city("臺南市") == "台南市"


def test_extract_city_normalizes_trad_taitung():
    assert extract_city("臺東縣") == "台東縣"


# ── filter_events_by_city 臺/台 cross-normalization ──────────────────────────


def test_filter_events_by_city_matches_trad_city_with_simplified_preference():
    """DB 中 city='臺北市' 應能被 preferred_city='台北市' 命中。"""
    events = [
        RaceEvent(
            name="臺北馬拉松",
            race_date=date(2026, 11, 15),
            location="臺北市大安區",
            url="https://running.biji.co/x",
            reg_start=date(2026, 6, 1),
            reg_end=date(2026, 8, 31),
            city="臺北市",
        )
    ]
    result = filter_events_by_city(events, "台北市")
    assert len(result) == 1


def test_filter_events_by_city_matches_simplified_city_with_trad_preference():
    """反向：event.city='台北市' 可被 preferred_city='臺北市' 命中。"""
    events = [
        RaceEvent(
            name="台北馬拉松",
            race_date=date(2026, 11, 15),
            location="台北市",
            url="https://running.biji.co/x",
            reg_start=date(2026, 6, 1),
            reg_end=date(2026, 8, 31),
            city="台北市",
        )
    ]
    result = filter_events_by_city(events, "臺北市")
    assert len(result) == 1


# ── filter_running_events ─────────────────────────────────────────────────────


def _ev(name: str) -> RaceEvent:
    return RaceEvent(
        name=name,
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/x",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
    )


def test_filter_running_keeps_marathon_and_road_run():
    events = [_ev("2026台北馬拉松"), _ev("城市路跑賽"), _ev("陽明山越野跑")]
    result = filter_running_events(events)
    assert len(result) == 3


def test_filter_running_excludes_cycling():
    events = [_ev("2026台北馬拉松"), _ev("第十一屆龍井單車逍遙遊")]
    result = filter_running_events(events)
    names = [e.name for e in result]
    assert "2026台北馬拉松" in names
    assert all("單車" not in n for n in names)


def test_filter_running_excludes_triathlon_and_swimming():
    events = [
        _ev("城市路跑"),
        _ev("2026 Challenge Taiwan 鐵人三項"),
        _ev("日月潭泳渡"),
    ]
    result = filter_running_events(events)
    assert [e.name for e in result] == ["城市路跑"]


# ── extract_og_image ──────────────────────────────────────────────────────────


def test_extract_og_image_from_meta_property():
    html = '<html><head><meta property="og:image" content="https://x.com/a.jpg"></head></html>'
    assert extract_og_image(html) == "https://x.com/a.jpg"


def test_extract_og_image_falls_back_to_twitter_image():
    html = '<html><head><meta name="twitter:image" content="https://x.com/t.jpg"></head></html>'
    assert extract_og_image(html) == "https://x.com/t.jpg"


def test_extract_og_image_returns_none_when_absent():
    html = "<html><head><title>no image</title></head></html>"
    assert extract_og_image(html) is None


# ── _extract_organizer ────────────────────────────────────────────────────────


def test_extract_organizer_from_table_row():
    html = "<table><tr><td>主辦單位</td><td>台灣路跑協會</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_organizer(soup) == "台灣路跑協會"


def test_extract_organizer_from_th_label():
    html = "<table><tr><th>主辦</th><td>新北市政府體育局</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_organizer(soup) == "新北市政府體育局"


def test_extract_organizer_returns_none_when_absent():
    html = "<html><body><p>沒有主辦單位資訊</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_organizer(soup) is None


# ── _extract_categories ───────────────────────────────────────────────────────


def test_extract_categories_from_biji_select_multiple_options():
    """biji <select><option> 結構可正確取出全部組別（placeholder 排除）。"""
    html = """
    <html><body>
      <select>
        <option>請選擇參賽組別</option>
        <option>全程馬拉松 42K</option>
        <option>半程馬拉松 21K</option>
        <option>10K 10K</option>
      </select>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_categories(soup)
    assert "全程馬拉松 42K" in result
    assert "半程馬拉松 21K" in result
    assert "10K" in result  # "10K 10K" deduplicated
    assert not any("請選擇" in c for c in result)


def test_extract_categories_filters_placeholder_and_returns_correct_count():
    """placeholder 被過濾，回傳數量與實際組別一致。"""
    html = """
    <html><body>
      <select>
        <option>請選擇參賽組別</option>
        <option>挑戰組 3K</option>
        <option>熱跑組 6.5K</option>
      </select>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_categories(soup)
    assert len(result) == 2
    assert "挑戰組 3K" in result
    assert "熱跑組 6.5K" in result


def test_extract_categories_deduplicates_repeated_tokens():
    """biji 的「10K 10K」選項應收斂為「10K」。"""
    html = """
    <html><body>
      <select>
        <option>請選擇參賽組別</option>
        <option>10K 10K</option>
        <option>5K 5K</option>
      </select>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_categories(soup)
    assert "10K" in result
    assert "5K" in result
    assert "10K 10K" not in result


def test_extract_categories_returns_empty_when_absent():
    html = "<html><body><p>沒有組別資訊</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_categories(soup) == []


# ── enrich_events ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_event_sets_official_url_image_organizer_categories():

    event = _ev("台北馬拉松")
    detail = _BijiEventDetail(
        official_url="https://ctrun.com.tw/Activity?EventMain_ID=1",
        image_url="https://running.biji.co/event-banner.jpg",
        organizer="台灣路跑協會",
        categories=["全程馬拉松 42K", "半程馬拉松 21K"],
    )
    with patch(
        "src.scraper.running_biji._fetch_biji_detail_async",
        new=AsyncMock(return_value=detail),
    ):
        result = await enrich_event(event)

    assert result.official_url == "https://ctrun.com.tw/Activity?EventMain_ID=1"
    assert result.image_url == "https://running.biji.co/event-banner.jpg"
    assert result.organizer == "台灣路跑協會"
    assert result.categories == ["全程馬拉松 42K", "半程馬拉松 21K"]


@pytest.mark.asyncio
async def test_enrich_event_gets_image_even_without_official_url():

    event = _ev("台北馬拉松")
    detail = _BijiEventDetail(
        official_url=None,
        image_url="https://running.biji.co/event.jpg",
        organizer=None,
        categories=[],
    )
    with patch(
        "src.scraper.running_biji._fetch_biji_detail_async",
        new=AsyncMock(return_value=detail),
    ):
        result = await enrich_event(event)

    assert result.official_url is None
    assert result.image_url == "https://running.biji.co/event.jpg"


@pytest.mark.asyncio
async def test_enrich_event_clears_image_when_detail_has_no_image():
    """當 detail.image_url 為 None，event.image_url 應被設為 None（不保留列表縮圖）。"""
    event = _ev("台北馬拉松")
    event.image_url = "https://running.biji.co/thumbnail.jpg"
    detail = _BijiEventDetail(
        official_url=None,
        image_url=None,
        organizer=None,
        categories=[],
    )
    with patch(
        "src.scraper.running_biji._fetch_biji_detail_async",
        new=AsyncMock(return_value=detail),
    ):
        result = await enrich_event(event)

    assert result.image_url is None


@pytest.mark.asyncio
async def test_enrich_events_processes_all():

    events = [_ev("活動A"), _ev("活動B")]
    detail = _BijiEventDetail(
        official_url="https://reg.example.com/1",
        image_url="https://biji.co/img.jpg",
        organizer=None,
        categories=[],
    )
    with patch(
        "src.scraper.running_biji._fetch_biji_detail_async",
        new=AsyncMock(return_value=detail),
    ):
        result = await enrich_events(events)

    assert len(result) == 2
    assert all(e.image_url == "https://biji.co/img.jpg" for e in result)


# ── clear_enrich_cache ────────────────────────────────────────────────────────


def test_clear_enrich_cache_empties_cache():
    from src.scraper.running_biji import _biji_detail_cache, clear_enrich_cache
    from src.scraper.running_biji import _BijiEventDetail as _D

    _biji_detail_cache["https://example.com/ev1"] = _D(
        official_url=None, image_url=None, organizer=None, categories=[]
    )
    clear_enrich_cache()
    assert "https://example.com/ev1" not in _biji_detail_cache


# ── extract_og_image 強化（任務二）────────────────────────────────────────────


def test_extract_og_image_accepts_meta_name_og_image():
    html = '<html><head><meta name="og:image" content="https://focusline.com/img.jpg"></head></html>'
    assert extract_og_image(html) == "https://focusline.com/img.jpg"


def test_extract_og_image_rejects_ico():
    html = '<html><head><meta property="og:image" content="https://site.com/favicon76.ico"></head></html>'
    assert extract_og_image(html) is None


def test_extract_og_image_rejects_biji_default_image():
    html = (
        '<html><head><meta property="og:image" content="'
        "https://running.biji.co/static/default_jpg/competition_470x246.jpg"
        '"></head></html>'
    )
    assert extract_og_image(html) is None


def test_extract_og_image_resolves_relative_url():
    html = '<html><head><meta property="og:image" content="/images/event.jpg"></head></html>'
    result = extract_og_image(html, base_url="https://lohasnet.tw/event/123")
    assert result == "https://lohasnet.tw/images/event.jpg"


def test_extract_og_image_returns_none_for_relative_without_base_url():
    html = '<html><head><meta property="og:image" content="/images/event.jpg"></head></html>'
    assert extract_og_image(html) is None


# ── _extract_reg_url 放行 irunner.biji.co（任務二）──────────────────────────


def test_extract_reg_url_allows_irunner_biji_co():
    html = """
    <html><body>
      <a href="https://irunner.biji.co/2026SpongeBob-KHH">線上報名</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_reg_url(soup)
    assert result == "https://irunner.biji.co/2026SpongeBob-KHH"


def test_extract_reg_url_still_skips_running_biji_co():
    html = """
    <html><body>
      <a href="https://running.biji.co/event/123">線上報名</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_reg_url(soup)
    assert result is None


def test_extract_reg_url_skips_irunner_homepage_promo():
    """biji 自家推廣的 irunner 裸首頁（含「報名」字樣）必須略過，不可遮蔽真正官方連結。"""
    html = """
    <html><body>
      <a href="https://irunner.biji.co/">筆記報名</a>
      <a href="https://www.focusline.com.tw/260621KF/personal">線上報名</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_reg_url(soup)
    assert result == "https://www.focusline.com.tw/260621KF/personal"


def test_extract_reg_url_matches_official_website_keyword():
    """只有「官方網站／活動官方網站」、沒有報名連結的活動也要抽得到。"""
    html = """
    <html><body>
      <a href="https://www.natgeomedia.com/event/2026/tw_wodrun2026">活動官方網站</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_reg_url(soup)
    assert result == "https://www.natgeomedia.com/event/2026/tw_wodrun2026"


# ── _do_fetch_biji_detail 改抓 official_url og:image（任務二）──────────────


def test_do_fetch_biji_detail_fetches_og_image_from_official_url():
    biji_html = (
        "<html><body>"
        '<a href="https://ctrun.com.tw/activity/123">線上報名</a>'
        "</body></html>"
    )
    official_html = (
        '<html><head><meta property="og:image" content="https://ctrun.com.tw/banner.jpg">'
        "</head></html>"
    )

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.text = official_html if "ctrun" in url else biji_html
        return resp

    with patch("src.scraper.running_biji.requests.get", side_effect=mock_get):
        result = _do_fetch_biji_detail("https://running.biji.co/event/1")

    assert result.official_url == "https://ctrun.com.tw/activity/123"
    assert result.image_url == "https://ctrun.com.tw/banner.jpg"


def test_do_fetch_biji_detail_returns_none_image_when_no_official_url():
    biji_html = "<html><body><p>沒有報名連結</p></body></html>"

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.text = biji_html
        return resp

    with patch("src.scraper.running_biji.requests.get", side_effect=mock_get):
        result = _do_fetch_biji_detail("https://running.biji.co/event/1")

    assert result.official_url is None
    assert result.image_url is None
