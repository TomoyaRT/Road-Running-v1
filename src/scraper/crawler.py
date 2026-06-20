from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from src.scraper.running_biji import (
    RaceEvent,
    clear_enrich_cache,
    enrich_events,
    fetch_events,
    filter_open_events,
    filter_running_events,
    filter_upcoming_events,
)
from src.utils import tw_today

logger = logging.getLogger(__name__)


class _EventStore(Protocol):
    def replace_events(self, events: list[RaceEvent]) -> None: ...


async def crawl_and_store(db: _EventStore, today: date | None = None) -> int:
    """爬取運動筆記、過濾路跑、補齊圖片與報名連結後存進 DB。

    只保留目前可報名或 30 天內即將開放的活動（已截止的不存）。
    回傳實際儲存的活動數量。
    """
    today = today or tw_today()
    clear_enrich_cache()
    raw = fetch_events()
    logger.info(f"fetch_events: {len(raw)} total events")
    if not raw:
        logger.warning(
            "fetch_events returned empty; skip replace to avoid wiping cache"
        )
        return 0
    events = filter_running_events(raw)
    logger.info(f"filter_running: {len(events)} running events")
    relevant = filter_open_events(events, today) + filter_upcoming_events(events, today)
    logger.info(
        f"filter_relevant: {len(relevant)} open/upcoming events (today={today})"
    )
    if not relevant:
        logger.warning(
            f"No open/upcoming events for {today}; skip replace to avoid wiping cache"
        )
        return 0
    await enrich_events(relevant)
    db.replace_events(relevant)
    logger.info(f"Crawl complete: stored {len(relevant)} running events")
    return len(relevant)
