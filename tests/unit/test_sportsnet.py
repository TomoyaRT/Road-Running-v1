from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.scraper.sportsnet import _parse_events, fetch_events

from src.scraper.running_biji import RaceEvent

# ── HTML fixtures ──────────────────────────────────────────────────────────────

# sportsnet: 第二張 table 為賽程表，第一張為導覽用 table
_TABLE_HTML = """
<html><body>
<table><tr><td>Nav</td></tr></table>
<table>
  <tr><th>　</th><th>序</th><th>日期</th><th>活動名稱</th><th>地點</th><th>組別</th></tr>
  <tr>
    <td></td><td>1</td><td>01/11(日)</td>
    <td><a href="http://scbmarathon.com/">2026渣打臺北公益馬拉松</a></td>
    <td>台北市信義區信義路</td>
    <td>42KM / 21KM / 11KM / 3KM</td>
  </tr>
  <tr>
    <td></td><td>2</td><td>01/24~25(六~日)</td>
    <td><a href="https://www.kinmarathon.org.tw/">2026金門馬拉松 KINMEN MARATHON</a></td>
    <td>金門縣金城鎮</td>
    <td>42KM/21KM/10KM/4KM</td>
  </tr>
  <tr>
    <td></td><td>3</td><td>02/01(日)</td>
    <td><a href="http://asicsrun.com.tw/">ASICS RUN 2026 亞瑟士接力路跑賽</a></td>
    <td>南投縣鹿谷鄉溪頭</td>
    <td>四人接力賽 (一般組/女子組)</td>
  </tr>
  <tr>
    <td></td><td>4</td><td>無日期</td>
    <td><a href="http://example.com/">有連結但無有效日期活動</a></td>
    <td>台中市</td>
    <td>5KM</td>
  </tr>
</table>
</body></html>
"""

_NO_TABLE_HTML = "<html><body><p>無賽程</p></body></html>"


# ── _parse_events ─────────────────────────────────────────────────────────────


def test_parse_events_returns_events():
    events = _parse_events(_TABLE_HTML)
    assert len(events) == 3


def test_parse_events_skips_header_row():
    """第一列（表頭）不應被解析成活動。"""
    events = _parse_events(_TABLE_HTML)
    assert all(isinstance(e, RaceEvent) for e in events)
    assert not any(e.name in ("活動名稱", "日期", "地點") for e in events)


def test_parse_events_skips_row_without_valid_date():
    """無有效日期的列（如「無日期」文字）應被略過。"""
    events = _parse_events(_TABLE_HTML)
    assert not any(e.name == "有連結但無有效日期活動" for e in events)


def test_parse_events_returns_empty_when_no_table():
    assert _parse_events(_NO_TABLE_HTML) == []


# ── name ─────────────────────────────────────────────────────────────────────


def test_parse_event_name():
    events = _parse_events(_TABLE_HTML)
    assert events[0].name == "2026渣打臺北公益馬拉松"


# ── race_date ─────────────────────────────────────────────────────────────────


def test_parse_event_race_date_simple_format():
    """'01/11(日)' → date(2026, 1, 11)（年份從活動名稱取得）。"""
    events = _parse_events(_TABLE_HTML)
    assert events[0].race_date == date(2026, 1, 11)


def test_parse_event_race_date_range_uses_first_date():
    """'01/24~25(六~日)' 取第一個日期 → date(2026, 1, 24)。"""
    events = _parse_events(_TABLE_HTML)
    assert events[1].race_date == date(2026, 1, 24)


def test_parse_event_race_date_year_from_name():
    """活動名稱中含 '2026' 時，年份應從名稱中提取。"""
    events = _parse_events(_TABLE_HTML)
    assert events[0].race_date.year == 2026
    assert events[2].race_date.year == 2026  # ASICS RUN 2026


# ── official_url ───────────────────────────────────────────────────────────────


def test_parse_event_official_url():
    events = _parse_events(_TABLE_HTML)
    assert events[0].official_url == "http://scbmarathon.com/"


def test_parse_event_official_url_second_event():
    events = _parse_events(_TABLE_HTML)
    assert events[1].official_url == "https://www.kinmarathon.org.tw/"


# ── location & city ───────────────────────────────────────────────────────────


def test_parse_event_location():
    events = _parse_events(_TABLE_HTML)
    assert events[0].location == "台北市信義區信義路"


def test_parse_event_city():
    events = _parse_events(_TABLE_HTML)
    assert events[0].city == "台北市"
    assert events[1].city == "金門縣"


# ── reg dates & image ─────────────────────────────────────────────────────────


def test_parse_event_reg_start_is_none():
    events = _parse_events(_TABLE_HTML)
    assert events[0].reg_start is None


def test_parse_event_reg_end_is_none():
    events = _parse_events(_TABLE_HTML)
    assert events[0].reg_end is None


def test_parse_event_image_url_is_none():
    events = _parse_events(_TABLE_HTML)
    assert events[0].image_url is None


def test_parse_event_source():
    events = _parse_events(_TABLE_HTML)
    assert all(e.source == "sportsnet" for e in events)


# ── categories ───────────────────────────────────────────────────────────────


def test_parse_event_categories_with_spaces():
    """'42KM / 21KM / 11KM / 3KM' 應解析成 4 個組別。"""
    events = _parse_events(_TABLE_HTML)
    assert events[0].categories == ["42KM", "21KM", "11KM", "3KM"]


def test_parse_event_categories_without_spaces():
    """'42KM/21KM/10KM/4KM'（無空格）同樣解析成 4 個組別。"""
    events = _parse_events(_TABLE_HTML)
    assert events[1].categories == ["42KM", "21KM", "10KM", "4KM"]


def test_parse_event_categories_parens_not_split():
    """'四人接力賽 (一般組/女子組)' 括號內的 '/' 不應被當作分隔符。"""
    events = _parse_events(_TABLE_HTML)
    assert events[2].categories == ["四人接力賽 (一般組/女子組)"]


# ── fetch_events ──────────────────────────────────────────────────────────────


def test_fetch_events_returns_events():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = _TABLE_HTML

    with patch("src.scraper.sportsnet.requests.get", return_value=mock_resp):
        events = fetch_events()

    assert len(events) == 3
    assert all(isinstance(e, RaceEvent) for e in events)


def test_fetch_events_returns_empty_on_failure():
    with patch("src.scraper.sportsnet.requests.get", side_effect=Exception("err")):
        assert fetch_events() == []
