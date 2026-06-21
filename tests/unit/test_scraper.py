from __future__ import annotations

from datetime import date

from src.scraper.running_biji import (
    RaceEvent,
    _normalize_city,
    extract_city,
    extract_og_image,
    filter_events_by_city,
    filter_open_events,
    filter_running_events,
    filter_upcoming_events,
)

# ── Sample events ─────────────────────────────────────────────────────────────

TODAY = date(2026, 6, 19)

_OPEN_EV = RaceEvent(
    name="Open Event",
    race_date=date(2026, 11, 15),
    location="台北市",
    url="https://irunner.biji.co/open-event",
    reg_start=date(2026, 6, 1),
    reg_end=date(2026, 8, 31),
    city="台北市",
)
_UPCOMING_EV = RaceEvent(
    name="Upcoming Event",
    race_date=date(2026, 12, 1),
    location="台中市",
    url="https://irunner.biji.co/upcoming-event",
    reg_start=date(2026, 7, 10),
    reg_end=date(2026, 9, 30),
    city="台中市",
)
_CLOSED_EV = RaceEvent(
    name="Closed Event",
    race_date=date(2026, 6, 13),
    location="高雄市",
    url="https://irunner.biji.co/closed-event",
    reg_start=date(2026, 1, 1),
    reg_end=date(2026, 3, 31),
    city="高雄市",
)
_NOCALENDAR_EV = RaceEvent(
    name="No Calendar Event",
    race_date=date(2026, 9, 20),
    location="新北市",
    url="https://irunner.biji.co/no-calendar",
    reg_start=None,
    reg_end=None,
    city="新北市",
)

_SAMPLE_EVENTS = [_OPEN_EV, _UPCOMING_EV, _CLOSED_EV, _NOCALENDAR_EV]


# ── filter_open_events ────────────────────────────────────────────────────────


def test_filter_open_events_returns_events_in_registration_period():
    open_events = filter_open_events(_SAMPLE_EVENTS, TODAY)
    names = [e.name for e in open_events]
    assert any("Open" in n for n in names)
    assert not any("Closed" in n for n in names)
    assert not any("Upcoming" in n for n in names)


def test_filter_open_events_excludes_no_reg_date():
    open_events = filter_open_events(_SAMPLE_EVENTS, TODAY)
    assert not any("No Calendar" in e.name for e in open_events)


# ── filter_upcoming_events ────────────────────────────────────────────────────


def test_filter_upcoming_events_returns_events_opening_within_30_days():
    upcoming = filter_upcoming_events(_SAMPLE_EVENTS, TODAY, days=30)
    names = [e.name for e in upcoming]
    # 2026-07-10 開報，距 TODAY=2026-06-19 為 21 天，應在 30 天內
    assert any("Upcoming" in n for n in names)
    assert not any("Open" in n for n in names)
    assert not any("Closed" in n for n in names)


def test_filter_upcoming_events_excludes_beyond_days():
    # 縮短到 10 天，2026-07-10 開報距今 21 天，應排除
    upcoming = filter_upcoming_events(_SAMPLE_EVENTS, TODAY, days=10)
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


# ── filter_events_by_city ─────────────────────────────────────────────────────


def test_filter_events_by_city_returns_matching_events():
    taipei_events = filter_events_by_city(_SAMPLE_EVENTS, "台北市")
    assert all(e.city == "台北市" for e in taipei_events)
    assert len(taipei_events) >= 1


def test_filter_events_by_city_all_returns_all():
    result = filter_events_by_city(_SAMPLE_EVENTS, "all")
    assert result == _SAMPLE_EVENTS


def test_filter_events_by_city_excludes_other_cities():
    taipei_only = filter_events_by_city(_SAMPLE_EVENTS, "台北市")
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
            url="https://irunner.biji.co/x",
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
            url="https://irunner.biji.co/x",
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
        url="https://irunner.biji.co/x",
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
