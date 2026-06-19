from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "users"


class FirestoreClient:
    def __init__(self, project_id: str) -> None:
        self._db = firestore.Client(project=project_id)

    def subscribe(
        self, user_id: int, notification_hour: int, preferred_city: str = "all"
    ) -> None:
        """新增或更新使用者的通知訂閱（含推播時段與城市偏好）。"""
        self._db.collection(_COLLECTION).document(str(user_id)).set(
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

    def update_city(self, user_id: int, preferred_city: str) -> None:
        """只更新城市偏好，不動推播時段。"""
        self._db.collection(_COLLECTION).document(str(user_id)).set(
            {"preferred_city": preferred_city},
            merge=True,
        )
        logger.info(f"User {user_id} updated city to {preferred_city}")

    def unsubscribe(self, user_id: int) -> None:
        """刪除使用者的通知訂閱。"""
        self._db.collection(_COLLECTION).document(str(user_id)).delete()
        logger.info(f"User {user_id} unsubscribed")

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
