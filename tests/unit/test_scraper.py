from __future__ import annotations

from datetime import date

from src.scraper.running_biji import (
    _parse_reg_dates,
    filter_open_events,
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
