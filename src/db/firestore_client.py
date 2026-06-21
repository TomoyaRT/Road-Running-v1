from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any

from google.cloud import firestore

from src.scraper.running_biji import (
    RaceEvent,
    filter_open_events,
    filter_upcoming_events,
)

logger = logging.getLogger(__name__)

_COLLECTION = "users"
_EVENTS_COLLECTION = "events"
_BATCH_LIMIT = 450  # Firestore 單批上限 500，保留安全邊際

# sportsnet / joinnow 型活動的 reg_start / reg_end 為 None。
# Firestore 不支援對 null 欄位做範圍查詢，以哨兵字串代替 None 儲存，
# 讀回時再還原為 None 供 Python 層正確處理。
_SENTINEL_REG_START = "0001-01-01"  # 相當於「無限早於」任何報名開始日
_SENTINEL_REG_END = "9999-12-31"  # 相當於「永遠不截止」


def _event_to_dict(event: RaceEvent) -> dict[str, Any]:
    return {
        "name": event.name,
        "race_date": event.race_date.isoformat(),
        "location": event.location,
        "url": event.url,
        "reg_start": event.reg_start.isoformat()
        if event.reg_start
        else _SENTINEL_REG_START,
        "reg_end": event.reg_end.isoformat() if event.reg_end else _SENTINEL_REG_END,
        "city": event.city,
        "image_url": event.image_url,
        "official_url": event.official_url,
        "organizer": event.organizer,
        "categories": event.categories,
        "source": event.source,
    }


def _dict_to_event(data: dict[str, Any]) -> RaceEvent:
    raw_start = data["reg_start"]
    raw_end = data["reg_end"]
    return RaceEvent(
        name=data["name"],
        race_date=date.fromisoformat(data["race_date"]),
        location=data["location"],
        url=data["url"],
        reg_start=(
            None
            if (not raw_start or raw_start == _SENTINEL_REG_START)
            else date.fromisoformat(raw_start)
        ),
        reg_end=(
            None
            if (not raw_end or raw_end == _SENTINEL_REG_END)
            else date.fromisoformat(raw_end)
        ),
        city=data.get("city", ""),
        image_url=data.get("image_url"),
        official_url=data.get("official_url"),
        organizer=data.get("organizer"),
        categories=data.get("categories", []),
        source=data.get("source", "biji"),
    )


def _event_doc_id(event: RaceEvent) -> str:
    return hashlib.md5(event.url.encode()).hexdigest()


class FirestoreClient:
    def __init__(self, project_id: str) -> None:
        self._db = firestore.Client(project=project_id)

    def subscribe(
        self, user_id: int, notification_hour: int, preferred_city: str = "all"
    ) -> bool:
        """新增或更新使用者的通知訂閱（含推播時段與城市偏好）。回傳 True 表示首次訂閱。"""
        doc_ref = self._db.collection(_COLLECTION).document(str(user_id))
        is_new = not doc_ref.get().exists
        doc_ref.set(
            {
                "user_id": user_id,
                "notification_hour": notification_hour,
                "preferred_city": preferred_city,
            },
            merge=True,
        )
        logger.info(
            f"User {user_id} subscribed at hour {notification_hour}, city={preferred_city}"
        )
        return is_new

    def get_user_city(self, user_id: int) -> str:
        """回傳使用者已設定的地區偏好；未訂閱或欄位缺漏時回 'all'。"""
        doc = self._db.collection(_COLLECTION).document(str(user_id)).get()
        if not doc.exists:
            return "all"
        return str(doc.to_dict().get("preferred_city", "all"))

    def update_hour(self, user_id: int, notification_hour: int) -> None:
        """只更新推播時段，不動城市偏好。"""
        self._db.collection(_COLLECTION).document(str(user_id)).set(
            {"notification_hour": notification_hour},
            merge=True,
        )
        logger.info(f"User {user_id} updated hour to {notification_hour}")

    def update_city(self, user_id: int, preferred_city: str) -> None:
        """只更新城市偏好，不動推播時段。"""
        self._db.collection(_COLLECTION).document(str(user_id)).set(
            {"preferred_city": preferred_city},
            merge=True,
        )
        logger.info(f"User {user_id} updated city to {preferred_city}")

    def get_notification_hour(self, user_id: int) -> int | None:
        """回傳使用者推播時段；未設定或欄位缺漏時回 None。"""
        doc = self._db.collection(_COLLECTION).document(str(user_id)).get()
        if not doc.exists:
            return None
        hour = doc.to_dict().get("notification_hour")
        return int(hour) if hour is not None else None

    def unsubscribe(self, user_id: int) -> None:
        """刪除使用者的通知訂閱。"""
        self._db.collection(_COLLECTION).document(str(user_id)).delete()
        logger.info(f"User {user_id} unsubscribed")

    def replace_events(self, events: list[RaceEvent]) -> None:
        """以最新爬取結果整批覆寫 events collection（並刪除已不存在的活動）。

        寫入與刪除以 _BATCH_LIMIT 為單位分批 commit，避免超過 Firestore 單批 500 筆上限。
        """
        col = self._db.collection(_EVENTS_COLLECTION)
        new_ids = {_event_doc_id(e): e for e in events}

        sets = [(col.document(did), _event_to_dict(ev)) for did, ev in new_ids.items()]
        deletes = [doc.reference for doc in col.stream() if doc.id not in new_ids]

        for i in range(0, len(sets), _BATCH_LIMIT):
            batch = self._db.batch()
            for ref, data in sets[i : i + _BATCH_LIMIT]:
                batch.set(ref, data)
            batch.commit()
        for i in range(0, len(deletes), _BATCH_LIMIT):
            batch = self._db.batch()
            for ref in deletes[i : i + _BATCH_LIMIT]:
                batch.delete(ref)
            batch.commit()
        logger.info(
            f"Replaced events collection: {len(sets)} set, {len(deletes)} deleted"
        )

    def get_events(self) -> list[RaceEvent]:
        """讀取快取的活動清單（全表掃描；舊版相容）。"""
        docs = self._db.collection(_EVENTS_COLLECTION).stream()
        return [_dict_to_event(doc.to_dict()) for doc in docs]

    def get_open_events(self, city: str, today: date) -> list[RaceEvent]:
        """Firestore クエリで候補を絞り込み、Python 側で filter_open_events を適用。

        reg_end >= today を Firestore で絞り込む（哨兵 "9999-12-31" で null も命中）。
        city != "all" の場合は city フィルターも追加（複合索引: city + reg_end）。
        """
        today_str = today.isoformat()
        q = self._db.collection(_EVENTS_COLLECTION).where("reg_end", ">=", today_str)
        if city != "all":
            q = q.where("city", "==", city)
        candidates = [_dict_to_event(doc.to_dict()) for doc in q.stream()]
        return filter_open_events(candidates, today)

    def get_upcoming_events(
        self, city: str, today: date, days: int = 30
    ) -> list[RaceEvent]:
        """Firestore クエリで候補を絞り込み、Python 側で filter_upcoming_events を適用。

        reg_start が今日より大きく deadline 以内のものを Firestore で絞り込む
        （哨兵 "0001-01-01" は today より小さいため upcoming に入らない）。
        city != "all" の場合は city フィルターも追加（複合索引: city + reg_start）。
        """
        today_str = today.isoformat()
        deadline_str = (today + timedelta(days=days)).isoformat()
        q = (
            self._db.collection(_EVENTS_COLLECTION)
            .where("reg_start", ">", today_str)
            .where("reg_start", "<=", deadline_str)
        )
        if city != "all":
            q = q.where("city", "==", city)
        candidates = [_dict_to_event(doc.to_dict()) for doc in q.stream()]
        return filter_upcoming_events(candidates, today, days)

    def get_users_for_hour(self, hour: int) -> list[dict[str, Any]]:
        """回傳指定推播時段的所有使用者資訊（含 user_id 與 preferred_city）。"""
        docs = (
            self._db.collection(_COLLECTION)
            .where("notification_hour", "==", hour)
            .stream()
        )
        result: list[dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict()
            result.append(
                {
                    "user_id": data["user_id"],
                    "preferred_city": data.get("preferred_city", "all"),
                }
            )
        return result
