from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from src.scraper.running_biji import (
    RaceEvent,
    enrich_events,
    fetch_events,
    filter_open_events,
    filter_running_events,
    filter_upcoming_events,
)

logger = logging.getLogger(__name__)


class _EventStore(Protocol):
    def replace_events(self, events: list[RaceEvent]) -> None: ...


async def crawl_and_store(db: _EventStore, today: date | None = None) -> int:
    """爬取運動筆記、過濾路跑、補齊圖片與報名連結後存進 DB。

    只保留目前可報名或 30 天內即將開放的活動（已截止的不存）。
    回傳實際儲存的活動數量。
    """
    today = today or date.today()
    raw = fetch_events()
    if not raw:
        # 爬蟲回傳空清單通常代表來源網站改版或暫時失效，
        # 此時若繼續會把整個快取清空，故直接跳過不覆寫。
        logger.warning(
            "fetch_events returned empty; skip replace to avoid wiping cache"
        )
        return 0
    events = filter_running_events(raw)
    relevant = filter_open_events(events, today) + filter_upcoming_events(events, today)
    await enrich_events(relevant)
    db.replace_events(relevant)
    logger.info(f"Crawl complete: stored {len(relevant)} running events")
    return len(relevant)
