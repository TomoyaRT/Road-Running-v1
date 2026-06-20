from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.db.firestore_client import (
    FirestoreClient,
    _dict_to_event,
    _event_to_dict,
)
from src.scraper.running_biji import RaceEvent

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


def test_subscribe_saves_user_with_hour_and_city(db, mock_firestore):
    db.subscribe(user_id=123, notification_hour=8, preferred_city="台北市")

    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.set.assert_called_once_with(
        {"user_id": 123, "notification_hour": 8, "preferred_city": "台北市"},
        merge=True,
    )


def test_subscribe_returns_true_for_new_subscriber(db, mock_firestore):
    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.get.return_value.exists = False

    result = db.subscribe(user_id=123, notification_hour=8)

    assert result is True


def test_subscribe_returns_false_for_existing_subscriber(db, mock_firestore):
    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.get.return_value.exists = True

    result = db.subscribe(user_id=123, notification_hour=8)

    assert result is False


def test_subscribe_defaults_preferred_city_to_all(db, mock_firestore):
    db.subscribe(user_id=123, notification_hour=8)

    doc_ref = mock_firestore.collection.return_value.document.return_value
    data = doc_ref.set.call_args[0][0]
    assert data["preferred_city"] == "all"


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


def test_get_users_for_hour_returns_dicts_with_city(db, mock_firestore):
    doc1 = MagicMock()
    doc1.to_dict.return_value = {
        "user_id": 111,
        "notification_hour": 8,
        "preferred_city": "台北市",
    }
    doc2 = MagicMock()
    doc2.to_dict.return_value = {
        "user_id": 222,
        "notification_hour": 8,
        "preferred_city": "高雄市",
    }

    mock_firestore.collection.return_value.where.return_value.stream.return_value = [
        doc1,
        doc2,
    ]

    result = db.get_users_for_hour(hour=8)

    assert result == [
        {"user_id": 111, "preferred_city": "台北市"},
        {"user_id": 222, "preferred_city": "高雄市"},
    ]


def test_get_users_for_hour_defaults_city_to_all_when_missing(db, mock_firestore):
    doc = MagicMock()
    doc.to_dict.return_value = {"user_id": 333, "notification_hour": 8}

    mock_firestore.collection.return_value.where.return_value.stream.return_value = [
        doc
    ]

    result = db.get_users_for_hour(hour=8)

    assert result == [{"user_id": 333, "preferred_city": "all"}]


def test_get_users_for_hour_queries_correct_field(db, mock_firestore):
    mock_firestore.collection.return_value.where.return_value.stream.return_value = []

    db.get_users_for_hour(hour=20)

    mock_firestore.collection.return_value.where.assert_called_once_with(
        "notification_hour", "==", 20
    )


# ── update_city ───────────────────────────────────────────────────────────────


def test_update_city_only_updates_preferred_city(db, mock_firestore):
    db.update_city(user_id=123, preferred_city="高雄市")

    doc_ref = mock_firestore.collection.return_value.document.return_value
    doc_ref.set.assert_called_once_with({"preferred_city": "高雄市"}, merge=True)


def test_update_city_uses_correct_document(db, mock_firestore):
    db.update_city(user_id=456, preferred_city="all")

    mock_firestore.collection.assert_called_with("users")
    mock_firestore.collection.return_value.document.assert_called_with("456")


# ── replace_events / get_events ───────────────────────────────────────────────


def _sample_event() -> RaceEvent:
    return RaceEvent(
        name="台北馬拉松",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
        city="台北市",
        image_url="https://reg.example.com/banner.jpg",
        official_url="https://reg.example.com/signup",
        categories=["半程馬拉松", "全程馬拉松"],
    )


def test_replace_events_writes_each_event_in_batch(db, mock_firestore):
    mock_firestore.collection.return_value.stream.return_value = []
    batch = mock_firestore.batch.return_value

    db.replace_events([_sample_event()])

    assert batch.set.call_count == 1
    written = batch.set.call_args[0][1]
    assert written["name"] == "台北馬拉松"
    assert written["race_date"] == "2026-11-15"
    assert written["image_url"] == "https://reg.example.com/banner.jpg"
    assert written["official_url"] == "https://reg.example.com/signup"
    assert written["categories"] == ["半程馬拉松", "全程馬拉松"]
    batch.commit.assert_called()


def test_replace_events_deletes_stale_docs(db, mock_firestore):
    stale = MagicMock()
    stale.id = "stale-doc-id"
    stale.reference = MagicMock()
    mock_firestore.collection.return_value.stream.return_value = [stale]
    batch = mock_firestore.batch.return_value

    db.replace_events([_sample_event()])

    batch.delete.assert_called_once_with(stale.reference)


def test_replace_events_uses_events_collection(db, mock_firestore):
    mock_firestore.collection.return_value.stream.return_value = []
    db.replace_events([_sample_event()])
    mock_firestore.collection.assert_any_call("events")


def test_replace_events_chunks_over_batch_limit(db, mock_firestore):
    mock_firestore.collection.return_value.stream.return_value = []
    batch = mock_firestore.batch.return_value
    # 500 個唯一活動 → 超過 450 上限 → 應分 2 批 commit
    events = [
        RaceEvent(
            name=f"活動{i}",
            race_date=date(2026, 11, 15),
            location="台北市",
            url=f"https://running.biji.co/cid={i}",
            reg_start=date(2026, 6, 1),
            reg_end=date(2026, 8, 31),
        )
        for i in range(500)
    ]

    db.replace_events(events)

    assert batch.set.call_count == 500
    assert batch.commit.call_count == 2


def test_get_events_returns_race_events(db, mock_firestore):
    doc = MagicMock()
    doc.to_dict.return_value = {
        "name": "高雄夜跑",
        "race_date": "2026-12-06",
        "location": "高雄市",
        "url": "https://running.biji.co/x",
        "reg_start": "2026-06-05",
        "reg_end": "2026-09-15",
        "city": "高雄市",
        "image_url": "https://reg.example.com/img.jpg",
        "official_url": "https://reg.example.com/go",
        "categories": ["10K"],
    }
    mock_firestore.collection.return_value.stream.return_value = [doc]

    events = db.get_events()

    assert len(events) == 1
    e = events[0]
    assert e.name == "高雄夜跑"
    assert e.race_date == date(2026, 12, 6)
    assert e.reg_start == date(2026, 6, 5)
    assert e.image_url == "https://reg.example.com/img.jpg"
    assert e.categories == ["10K"]


def test_event_source_round_trips_through_firestore():
    """source 欄位必須寫入並讀回，否則跨來源活動會被誤標為 biji。"""
    event = RaceEvent(
        name="全統路跑",
        race_date=date(2026, 8, 8),
        location="嘉義市",
        url="https://www.ctrun.com.tw/Activity?EventMain_ID=1",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 7, 15),
        source="ctrun",
    )
    restored = _dict_to_event(_event_to_dict(event))
    assert restored.source == "ctrun"


def test_get_events_handles_null_reg_dates(db, mock_firestore):
    doc = MagicMock()
    doc.to_dict.return_value = {
        "name": "無日期活動",
        "race_date": "2026-12-06",
        "location": "台中市",
        "url": "https://running.biji.co/y",
        "reg_start": None,
        "reg_end": None,
        "city": "台中市",
        "image_url": None,
        "official_url": None,
        "categories": [],
    }
    mock_firestore.collection.return_value.stream.return_value = [doc]

    events = db.get_events()

    assert events[0].reg_start is None
    assert events[0].reg_end is None
    assert events[0].image_url is None
