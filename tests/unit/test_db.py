from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.db.firestore_client import FirestoreClient

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_firestore():
    """mock google-cloud-firestore Client。"""
    with patch("src.db.firestore_client.firestore") as mock_fs:
        mock_client = MagicMock()
        mock_fs.Client.return_value = mock_client
        yield mock_client


@pytest.fixture
def db(mock_firestore) -> FirestoreClient:
    return FirestoreClient(project_id="test-project")


# ── subscribe ─────────────────────────────────────────────────────────────────


def test_subscribe_saves_user_with_hour(db, mock_firestore):
    db.subscribe(user_id=123, notification_hour=8)

    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.set.assert_called_once_with(
        {"user_id": 123, "notification_hour": 8}, merge=True
    )


def test_subscribe_uses_users_collection(db, mock_firestore):
    db.subscribe(user_id=456, notification_hour=20)

    mock_firestore.collection.assert_called_with("users")
    mock_firestore.collection.return_value.document.assert_called_with("456")


# ── unsubscribe ───────────────────────────────────────────────────────────────


def test_unsubscribe_deletes_user_document(db, mock_firestore):
    db.unsubscribe(user_id=123)

    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.delete.assert_called_once()


# ── get_users_for_hour ────────────────────────────────────────────────────────


def test_get_users_for_hour_returns_matching_user_ids(db, mock_firestore):
    doc1 = MagicMock()
    doc1.to_dict.return_value = {"user_id": 111, "notification_hour": 8}
    doc2 = MagicMock()
    doc2.to_dict.return_value = {"user_id": 222, "notification_hour": 8}

    mock_firestore.collection.return_value.where.return_value.stream.return_value = [
        doc1,
        doc2,
    ]

    result = db.get_users_for_hour(hour=8)

    assert result == [111, 222]


def test_get_users_for_hour_queries_correct_field(db, mock_firestore):
    mock_firestore.collection.return_value.where.return_value.stream.return_value = []

    db.get_users_for_hour(hour=20)

    mock_firestore.collection.return_value.where.assert_called_once_with(
        "notification_hour", "==", 20
    )
