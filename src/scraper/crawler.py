from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date
from typing import Protocol

from src.scraper import bao_ming, ctrun
from src.scraper.dedup import merge_events
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
    """多來源爬取（運動筆記 + 報名網 + 全統）、過濾路跑、跨來源去重後存進 DB。

    只保留目前可報名或 30 天內即將開放的活動。回傳去重後實際儲存的數量。
    biji 為來源之一（不再是唯一）；任一來源失敗不影響其他來源。
    """
    today = today or tw_today()
    clear_enrich_cache()

    biji_events = await _collect_biji(today)
    other_events = await _collect_other_sources(today)
    all_events = biji_events + other_events
    logger.info(
        f"collected: biji={len(biji_events)} others={len(other_events)} "
        f"total={len(all_events)}"
    )
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


async def _collect_biji(today: date) -> list[RaceEvent]:
    raw = fetch_events()
    logger.info(f"biji fetch: {len(raw)} events")
    relevant = _filter_relevant(raw, today)
    if relevant:
        await enrich_events(relevant)
    return relevant


async def _collect_other_sources(today: date) -> list[RaceEvent]:
    """bao-ming 與 ctrun 並行抓取；各自詳情頁已含完整欄位，無須額外 enrich。"""
    fetched = await asyncio.gather(
        asyncio.to_thread(_safe_fetch, bao_ming.fetch_events, "bao-ming"),
        asyncio.to_thread(_safe_fetch, ctrun.fetch_events, "ctrun"),
    )
    collected: list[RaceEvent] = []
    for events in fetched:
        collected.extend(_filter_relevant(events, today))
    return collected


def _safe_fetch(fetch: Callable[[], list[RaceEvent]], name: str) -> list[RaceEvent]:
    try:
        events = fetch()
        logger.info(f"{name} fetch: {len(events)} events")
        return events
    except Exception:
        logger.exception(f"source {name} fetch failed")
        return []
