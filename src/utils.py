from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

_TW = timezone(timedelta(hours=8))


def tw_today() -> date:
    """回傳台灣時間（UTC+8）的今天日期。"""
    return datetime.now(_TW).date()
