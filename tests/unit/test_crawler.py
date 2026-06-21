from __future__ import annotations

from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.scraper.crawler import crawl_and_store
from src.scraper.running_biji import RaceEvent

TODAY = date(2026, 6, 19)


def _ev(name: str, reg_start: date, reg_end: date, url: str = "") -> RaceEvent:
    return RaceEvent(
        name=name,
        race_date=date(2026, 11, 15),
        location="台北市",
        url=url or f"https://example.com/{name}",
        reg_start=reg_start,
        reg_end=reg_end,
        city="台北市",
    )


_OPEN = _ev("開放中路跑", date(2026, 6, 1), date(2026, 8, 31))
_UPCOMING = _ev("即將開放路跑", date(2026, 6, 25), date(2026, 9, 30))
_CLOSED = _ev("已截止路跑", date(2026, 1, 1), date(2026, 3, 31))
_CYCLING = _ev("台北單車逍遙遊", date(2026, 6, 1), date(2026, 8, 31))


def _patch_sources(
    irunner_evs: list[RaceEvent] | None = None,
    baoming: list[RaceEvent] | None = None,
    ctrun_evs: list[RaceEvent] | None = None,
    joinnow_evs: list[RaceEvent] | None = None,
    sportsnet_evs: list[RaceEvent] | None = None,
) -> tuple:
    """5 個來源全部 mock；預設各回 []。"""
    return (
        patch(
            "src.scraper.crawler.irunner.fetch_events",
            return_value=irunner_evs or [],
        ),
        patch(
            "src.scraper.crawler.bao_ming.fetch_events",
            return_value=baoming or [],
        ),
        patch(
            "src.scraper.crawler.ctrun.fetch_events",
            return_value=ctrun_evs or [],
        ),
        patch(
            "src.scraper.crawler.joinnow.fetch_events",
            return_value=joinnow_evs or [],
        ),
        patch(
            "src.scraper.crawler.sportsnet.fetch_events",
            return_value=sportsnet_evs or [],
        ),
    )


@pytest.mark.asyncio
async def test_crawl_and_store_filters_running_and_relevant():
    db = MagicMock()
    patches = _patch_sources(irunner_evs=[_OPEN, _UPCOMING, _CLOSED, _CYCLING])
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        count = await crawl_and_store(db, today=TODAY)

    stored = db.replace_events.call_args[0][0]
    stored_names = {e.name for e in stored}
    assert "開放中路跑" in stored_names
    assert "即將開放路跑" in stored_names
    assert "已截止路跑" not in stored_names
    assert "台北單車逍遙遊" not in stored_names
    assert count == 2


@pytest.mark.asyncio
async def test_crawl_and_store_merges_all_five_sources():
    """5 個來源各出一筆不同活動 → 全部存入。"""
    db = MagicMock()
    ev_ir = _ev(
        "irunner路跑", date(2026, 6, 1), date(2026, 8, 31), "https://irunner.biji.co/1"
    )
    ev_bm = _ev(
        "報名網路跑", date(2026, 6, 1), date(2026, 8, 31), "https://bao-ming.com/eb/1"
    )
    ev_ct = _ev(
        "全統路跑", date(2026, 6, 1), date(2026, 8, 31), "https://www.ctrun.com.tw/1"
    )
    ev_jn = _ev(
        "joinnow路跑",
        date(2026, 6, 1),
        date(2026, 8, 31),
        "https://www.joinnow.com.tw/1",
    )
    ev_sn = _ev(
        "sportsnet路跑",
        date(2026, 6, 1),
        date(2026, 8, 31),
        "https://www.sportsnet.org.tw/1",
    )

    patches = _patch_sources(
        irunner_evs=[ev_ir],
        baoming=[ev_bm],
        ctrun_evs=[ev_ct],
        joinnow_evs=[ev_jn],
        sportsnet_evs=[ev_sn],
    )
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        count = await crawl_and_store(db, today=TODAY)

    assert count == 5


@pytest.mark.asyncio
async def test_crawl_and_store_dedups_same_event_across_sources():
    """irunner 的 official_url 指向 bao-ming 同一頁 → 去重後只剩一筆。"""
    db = MagicMock()
    ir = _ev("台北馬", date(2026, 6, 1), date(2026, 8, 31))
    ir.url = "https://irunner.biji.co/9"
    ir.official_url = "https://bao-ming.com/eb/content/9"
    bm = _ev("台北馬拉松", date(2026, 6, 1), date(2026, 8, 31))
    bm.url = "https://bao-ming.com/eb/content/9"
    bm.official_url = "https://bao-ming.com/eb/content/9"

    patches = _patch_sources(irunner_evs=[ir], baoming=[bm])
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        count = await crawl_and_store(db, today=TODAY)

    assert count == 1


@pytest.mark.asyncio
async def test_crawl_and_store_skips_when_all_sources_empty():
    """所有來源皆空時不可覆寫 DB（避免清空快取）。"""
    db = MagicMock()
    patches = _patch_sources()
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        count = await crawl_and_store(db, today=TODAY)

    assert count == 0
    db.replace_events.assert_not_called()


@pytest.mark.asyncio
async def test_crawl_and_store_skips_when_relevant_empty():
    """fetch 有資料但 filter 後無相關活動時，不可覆寫 DB（避免清空快取）。"""
    db = MagicMock()
    patches = _patch_sources(irunner_evs=[_CLOSED])
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        count = await crawl_and_store(db, today=TODAY)

    assert count == 0
    db.replace_events.assert_not_called()


@pytest.mark.asyncio
async def test_crawl_and_store_one_source_failure_does_not_block_others():
    """一個來源拋例外時，其他來源的活動仍正常儲存。"""
    db = MagicMock()
    patches = _patch_sources(
        irunner_evs=[_OPEN],
        baoming=None,  # 正常回 []
    )
    # 讓 ctrun 拋例外
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch(
                "src.scraper.crawler.ctrun.fetch_events",
                side_effect=Exception("ctrun down"),
            )
        )
        count = await crawl_and_store(db, today=TODAY)

    assert count == 1
    stored_names = {e.name for e in db.replace_events.call_args[0][0]}
    assert "開放中路跑" in stored_names
