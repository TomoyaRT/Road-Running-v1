from __future__ import annotations

import logging

from google.cloud import firestore

logger = logging.getLogger(__name__)

_COLLECTION = "users"


class FirestoreClient:
    def __init__(self, project_id: str) -> None:
        self._db = firestore.Client(project=project_id)

    def subscribe(self, user_id: int, notification_hour: int) -> None:
        """新增或更新使用者的通知訂閱。"""
        self._db.collection(_COLLECTION).document(str(user_id)).set(
            {"user_id": user_id, "notification_hour": notification_hour},
            merge=True,
        )
        logger.info(f"User {user_id} subscribed at hour {notification_hour}")

    def unsubscribe(self, user_id: int) -> None:
        """刪除使用者的通知訂閱。"""
        self._db.collection(_COLLECTION).document(str(user_id)).delete()
        logger.info(f"User {user_id} unsubscribed")

    def get_users_for_hour(self, hour: int) -> list[int]:
        """回傳指定推播時段的所有使用者 ID。"""
        docs = (
            self._db.collection(_COLLECTION)
            .where("notification_hour", "==", hour)
            .stream()
        )
        return [doc.to_dict()["user_id"] for doc in docs]
