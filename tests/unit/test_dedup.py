from __future__ import annotations

from datetime import date

from src.scraper.dedup import merge_events
from src.scraper.running_biji import RaceEvent


def _event(**kw) -> RaceEvent:
    base = dict(
        name="某路跑",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://example.com/unique",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
    )
    base.update(kw)
    return RaceEvent(**base)  # type: ignore[arg-type]


def test_merge_keeps_single_event_unchanged():
    assert len(merge_events([_event()])) == 1


# ── 主鍵：報名連結 URL ──────────────────────────────────────────────────────


def test_merge_dedups_by_registration_url_even_when_organizer_differs():
    """biji official_url 指向 bao-ming 同一頁 → 精確比對合併，無視主辦字串差異。"""
    biji = _event(
        url="https://running.biji.co/comp/123",
        official_url="https://bao-ming.com/eb/content/6945",
        organizer="主辦寫法A",
    )
    baoming = _event(
        url="https://bao-ming.com/eb/content/6945",
        official_url="https://bao-ming.com/eb/content/6945",
        organizer="主辦寫法B",
    )
    assert len(merge_events([biji, baoming])) == 1


def test_merge_url_key_ignores_fragment_and_trailing_slash():
    a = _event(url="u1", official_url="https://bao-ming.com/eb/content/6945#reg")
    b = _event(url="u2", official_url="https://bao-ming.com/eb/content/6945/")
    assert len(merge_events([a, b])) == 1


# ── 輔鍵：主辦 + 城市 + 日期（URL 不互通時）──────────────────────────────────


def test_merge_dedups_by_triple_when_urls_differ():
    """名稱不同、URL 不同，但主辦/城市/日期相同 → 合併。"""
    a = _event(
        url="https://running.biji.co/x", name="2026 台北馬", organizer="台北市政府"
    )
    b = _event(
        url="https://other.com/y", name="台北馬拉松 2026", organizer="台北市政府"
    )
    assert len(merge_events([a, b])) == 1


def test_merge_triple_location_compared_at_city_level():
    a = _event(url="u1", location="台北市", organizer="某會")
    b = _event(url="u2", location="台北市大佳河濱公園", organizer="某會", city="")
    assert len(merge_events([a, b])) == 1


def test_merge_triple_normalizes_traditional_tai():
    a = _event(url="u1", organizer="某會", city="臺中市")
    b = _event(url="u2", organizer="某會", city="台中市")
    assert len(merge_events([a, b])) == 1


def test_merge_triple_skipped_when_city_missing():
    """城市缺漏時不做模糊合併，避免把無城市的不同活動誤併。"""
    a = _event(url="u1", organizer="某會", location="動物園廣場", city="")
    b = _event(url="u2", organizer="某會", location="某地標", city="")
    assert len(merge_events([a, b])) == 2


# ── 區辨與保留規則 ─────────────────────────────────────────────────────────


def test_merge_keeps_distinct_events():
    a = _event(url="u1", organizer="A會", race_date=date(2026, 11, 15))
    b = _event(url="u2", organizer="B會", race_date=date(2026, 11, 15))
    c = _event(url="u3", organizer="A會", race_date=date(2026, 12, 20))
    assert len(merge_events([a, b, c])) == 3


def test_merge_prefers_more_complete_event():
    sparse = _event(url="u1", organizer="某會")
    rich = _event(
        url="u2",
        organizer="某會",
        image_url="https://img/x.jpg",
        official_url="https://official/x",
        categories=["10K", "半馬"],
    )
    merged = merge_events([sparse, rich])
    assert len(merged) == 1
    assert merged[0].image_url == "https://img/x.jpg"
    assert merged[0].categories == ["10K", "半馬"]


def test_merge_preserves_first_seen_order():
    a = _event(url="u1", organizer="A會", race_date=date(2026, 11, 1))
    b = _event(url="u2", organizer="B會", race_date=date(2026, 11, 2))
    merged = merge_events([a, b])
    assert [e.organizer for e in merged] == ["A會", "B會"]
