from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.scraper.running_biji import (
    RaceEvent,
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


# ── enrich_events ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_event_populates_reg_url_and_image():
    event = _ev("台北馬拉松")
    with (
        patch(
            "src.scraper.running_biji.fetch_official_url_async",
            new=AsyncMock(return_value="https://ctrun.com.tw/Activity?EventMain_ID=1"),
        ),
        patch(
            "src.scraper.running_biji.fetch_og_image",
            return_value="https://ctrun.com.tw/banner.jpg",
        ),
    ):
        result = await enrich_event(event)

    assert result.official_url == "https://ctrun.com.tw/Activity?EventMain_ID=1"
    assert result.image_url == "https://ctrun.com.tw/banner.jpg"


@pytest.mark.asyncio
async def test_enrich_event_no_image_when_no_reg_url():
    event = _ev("台北馬拉松")
    with patch(
        "src.scraper.running_biji.fetch_official_url_async",
        new=AsyncMock(return_value=None),
    ):
        result = await enrich_event(event)

    assert result.official_url is None
    assert result.image_url is None


@pytest.mark.asyncio
async def test_enrich_events_processes_all():
    events = [_ev("活動A"), _ev("活動B")]
    with (
        patch(
            "src.scraper.running_biji.fetch_official_url_async",
            new=AsyncMock(return_value="https://reg.example.com/1"),
        ),
        patch(
            "src.scraper.running_biji.fetch_og_image",
            return_value="https://reg.example.com/img.jpg",
        ),
    ):
        result = await enrich_events(events)

    assert len(result) == 2
    assert all(e.image_url == "https://reg.example.com/img.jpg" for e in result)
