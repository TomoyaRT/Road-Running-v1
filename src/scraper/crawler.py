from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date
from typing import Protocol

from src.scraper import bao_ming, ctrun, irunner, joinnow, sportsnet
from src.scraper.dedup import merge_events
from src.scraper.running_biji import (
    RaceEvent,
    filter_open_events,
    filter_running_events,
    filter_upcoming_events,
)
from src.utils import tw_today

logger = logging.getLogger(__name__)


class _EventStore(Protocol):
    def replace_events(self, events: list[RaceEvent]) -> None: ...


async def crawl_and_store(db: _EventStore, today: date | None = None) -> int:
    """5 個來源並行爬取、過濾路跑/可報名、跨來源去重後存進 DB。回傳儲存數量。

    任一來源失敗不影響其他來源；全部過濾後無活動時不覆寫 DB（保護快取）。
    """
    today = today or tw_today()

    fetched = await asyncio.gather(
        asyncio.to_thread(_safe_fetch, irunner.fetch_events, "irunner"),
        asyncio.to_thread(_safe_fetch, bao_ming.fetch_events, "bao-ming"),
        asyncio.to_thread(_safe_fetch, ctrun.fetch_events, "ctrun"),
        asyncio.to_thread(_safe_fetch, joinnow.fetch_events, "joinnow"),
        asyncio.to_thread(_safe_fetch, sportsnet.fetch_events, "sportsnet"),
    )

    all_events: list[RaceEvent] = []
    for events in fetched:
        all_events.extend(_filter_relevant(events, today))

    raw_total = sum(len(e) for e in fetched)
    logger.info(f"collected: raw={raw_total} relevant={len(all_events)}")

    if not all_events:
        logger.warning("No events collected; skip replace to avoid wiping cache")
        return 0

    merged = merge_events(all_events)
    logger.info(f"after cross-source dedup: {len(merged)} unique events")
    db.replace_events(merged)
    return len(merged)


def _filter_relevant(events: list[RaceEvent], today: date) -> list[RaceEvent]:
    """只留路跑、且目前可報名或 30 天內即將開放的活動。"""
    running = filter_running_events(events)
    return filter_open_events(running, today) + filter_upcoming_events(running, today)


def _safe_fetch(fetch: Callable[[], list[RaceEvent]], name: str) -> list[RaceEvent]:
    try:
        events = fetch()
        logger.info(f"{name} fetch: {len(events)} events")
        return events
    except Exception:
        logger.exception(f"source {name} fetch failed")
        return []
