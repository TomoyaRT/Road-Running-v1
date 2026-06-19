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


@pytest.mark.asyncio
async def test_crawl_and_store_filters_running_and_relevant():
    db = MagicMock()
    all_events = [_OPEN, _UPCOMING, _CLOSED, _CYCLING]

    with (
        patch("src.scraper.crawler.fetch_events", return_value=all_events),
        patch(
            "src.scraper.crawler.enrich_events",
            new=AsyncMock(side_effect=lambda evs: evs),
        ),
    ):
        count = await crawl_and_store(db, today=TODAY)

    stored = db.replace_events.call_args[0][0]
    stored_names = {e.name for e in stored}
    assert "開放中路跑" in stored_names
    assert "即將開放路跑" in stored_names
    assert "已截止路跑" not in stored_names  # 已截止不存
    assert "台北單車逍遙遊" not in stored_names  # 非路跑不存
    assert count == 2


@pytest.mark.asyncio
async def test_crawl_and_store_enriches_before_storing():
    db = MagicMock()
    enrich_mock = AsyncMock(side_effect=lambda evs: evs)

    with (
        patch("src.scraper.crawler.fetch_events", return_value=[_OPEN]),
        patch("src.scraper.crawler.enrich_events", new=enrich_mock),
    ):
        await crawl_and_store(db, today=TODAY)

    enrich_mock.assert_awaited_once()
    db.replace_events.assert_called_once()


@pytest.mark.asyncio
async def test_crawl_and_store_skips_when_fetch_empty():
    """爬蟲回傳空清單時不可覆寫 DB（避免清空快取）。"""
    db = MagicMock()

    with (
        patch("src.scraper.crawler.fetch_events", return_value=[]),
        patch(
            "src.scraper.crawler.enrich_events",
            new=AsyncMock(side_effect=lambda evs: evs),
        ),
    ):
        count = await crawl_and_store(db, today=TODAY)

    assert count == 0
    db.replace_events.assert_not_called()
