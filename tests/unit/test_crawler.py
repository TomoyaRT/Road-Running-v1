from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scraper.crawler import crawl_and_store
from src.scraper.running_biji import RaceEvent

TODAY = date(2026, 6, 19)


def _ev(name: str, reg_start: date, reg_end: date) -> RaceEvent:
    return RaceEvent(
        name=name,
        race_date=date(2026, 11, 15),
        location="台北市",
        url=f"https://running.biji.co/{name}",
        reg_start=reg_start,
        reg_end=reg_end,
        city="台北市",
    )


_OPEN = _ev("開放中路跑", date(2026, 6, 1), date(2026, 8, 31))
_UPCOMING = _ev("即將開放路跑", date(2026, 6, 25), date(2026, 9, 30))
_CLOSED = _ev("已截止路跑", date(2026, 1, 1), date(2026, 3, 31))
_CYCLING = _ev("台北單車逍遙遊", date(2026, 6, 1), date(2026, 8, 31))


def _patch_sources(biji, baoming=None, ctrun_evs=None):
    """統一 patch 三個來源 + enrich（enrich 原樣回傳）。"""
    return (
        patch("src.scraper.crawler.fetch_events", return_value=biji),
        patch("src.scraper.crawler.bao_ming.fetch_events", return_value=baoming or []),
        patch("src.scraper.crawler.ctrun.fetch_events", return_value=ctrun_evs or []),
        patch(
            "src.scraper.crawler.enrich_events",
            new=AsyncMock(side_effect=lambda evs: evs),
        ),
    )


@pytest.mark.asyncio
async def test_crawl_and_store_filters_running_and_relevant():
    db = MagicMock()
    p1, p2, p3, p4 = _patch_sources([_OPEN, _UPCOMING, _CLOSED, _CYCLING])
    with p1, p2, p3, p4:
        count = await crawl_and_store(db, today=TODAY)

    stored = db.replace_events.call_args[0][0]
    stored_names = {e.name for e in stored}
    assert "開放中路跑" in stored_names
    assert "即將開放路跑" in stored_names
    assert "已截止路跑" not in stored_names  # 已截止不存
    assert "台北單車逍遙遊" not in stored_names  # 非路跑不存
    assert count == 2


@pytest.mark.asyncio
async def test_crawl_and_store_enriches_biji_before_storing():
    db = MagicMock()
    enrich_mock = AsyncMock(side_effect=lambda evs: evs)

    with (
        patch("src.scraper.crawler.fetch_events", return_value=[_OPEN]),
        patch("src.scraper.crawler.bao_ming.fetch_events", return_value=[]),
        patch("src.scraper.crawler.ctrun.fetch_events", return_value=[]),
        patch("src.scraper.crawler.enrich_events", new=enrich_mock),
    ):
        await crawl_and_store(db, today=TODAY)

    enrich_mock.assert_awaited_once()
    db.replace_events.assert_called_once()


@pytest.mark.asyncio
async def test_crawl_and_store_merges_all_sources():
    """三來源各出一筆不同活動 → 全部存入。"""
    db = MagicMock()
    bm = _ev("報名網路跑", date(2026, 6, 1), date(2026, 8, 31))
    bm.url = "https://bao-ming.com/eb/content/1"
    ct = _ev("全統路跑", date(2026, 6, 1), date(2026, 8, 31))
    ct.url = "https://www.ctrun.com.tw/Activity?EventMain_ID=1"

    p1, p2, p3, p4 = _patch_sources([_OPEN], baoming=[bm], ctrun_evs=[ct])
    with p1, p2, p3, p4:
        count = await crawl_and_store(db, today=TODAY)

    assert count == 3


@pytest.mark.asyncio
async def test_crawl_and_store_dedups_same_event_across_sources():
    """biji 的 official_url 指向 bao-ming 同一頁 → 去重後只剩一筆。"""
    db = MagicMock()
    biji = _ev("台北馬", date(2026, 6, 1), date(2026, 8, 31))
    biji.url = "https://running.biji.co/comp/9"
    biji.official_url = "https://bao-ming.com/eb/content/9"
    bm = _ev("台北馬拉松", date(2026, 6, 1), date(2026, 8, 31))
    bm.url = "https://bao-ming.com/eb/content/9"
    bm.official_url = "https://bao-ming.com/eb/content/9"

    p1, p2, p3, p4 = _patch_sources([biji], baoming=[bm])
    with p1, p2, p3, p4:
        count = await crawl_and_store(db, today=TODAY)

    assert count == 1


@pytest.mark.asyncio
async def test_crawl_and_store_skips_when_all_sources_empty():
    """所有來源皆空時不可覆寫 DB（避免清空快取）。"""
    db = MagicMock()
    p1, p2, p3, p4 = _patch_sources([])
    with p1, p2, p3, p4:
        count = await crawl_and_store(db, today=TODAY)

    assert count == 0
    db.replace_events.assert_not_called()


@pytest.mark.asyncio
async def test_crawl_and_store_skips_when_relevant_empty():
    """fetch 有資料但 filter 後無相關活動時，不可覆寫 DB（避免清空快取）。"""
    db = MagicMock()
    p1, p2, p3, p4 = _patch_sources([_CLOSED])
    with p1, p2, p3, p4:
        count = await crawl_and_store(db, today=TODAY)

    assert count == 0
    db.replace_events.assert_not_called()
