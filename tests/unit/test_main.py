from __future__ import annotations

import json
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.main as main_module
from src.main import notify_endpoint, quart_app
from src.scraper.running_biji import RaceEvent


@pytest.mark.asyncio
async def test_notify_endpoint_returns_200_on_success():
    mock_tg_app = MagicMock()
    mock_tg_app.bot = MagicMock()

    with (
        patch.object(main_module, "_telegram_app", mock_tg_app),
        patch.object(main_module, "notify_users", new=AsyncMock()),
    ):
        response = await notify_endpoint()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_notify_endpoint_returns_500_on_exception():
    """notify_users 拋例外時，endpoint 應回 500 並呼叫 logger.exception。"""
    mock_tg_app = MagicMock()
    mock_tg_app.bot = MagicMock()

    with (
        patch.object(main_module, "_telegram_app", mock_tg_app),
        patch.object(
            main_module,
            "notify_users",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch.object(main_module, "logger") as mock_logger,
    ):
        response = await notify_endpoint()

    assert response.status_code == 500
    mock_logger.exception.assert_called_once()


# ── /api/events 按鈕 URL 防護測試（T2 regression guard） ────────────────────


def _open_event(official_url: str, url: str | None = None) -> RaceEvent:
    today = date(2026, 6, 21)
    return RaceEvent(
        name="測試路跑",
        race_date=date(2026, 9, 1),
        location="台北市信義區",
        url=url or official_url,
        reg_start=today,
        reg_end=date(2026, 8, 31),
        official_url=official_url,
        city="台北市",
        source="baoming",
    )


@pytest.mark.asyncio
async def test_api_events_button_url_uses_official_url():
    """當 official_url 與 url 不同時，按鈕應使用 official_url。"""
    event = _open_event(
        official_url="https://bao-ming.com/eb/content/7028",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=13072",
    )
    mock_db = MagicMock()
    mock_db.get_events.return_value = [event]

    with (
        patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}),
        patch.object(main_module, "validate_init_data", return_value=True),
        patch.object(main_module, "get_db", return_value=mock_db),
        patch.object(main_module, "tw_today", return_value=date(2026, 6, 21)),
    ):
        async with quart_app.test_client() as client:
            resp = await client.get(
                "/api/events?type=open&city=all",
                headers={"Authorization": "test"},
            )

    assert resp.status_code == 200
    data = json.loads(await resp.get_data())
    assert data["events"][0]["url"] == "https://bao-ming.com/eb/content/7028"


@pytest.mark.asyncio
async def test_api_events_button_url_never_contains_running_biji():
    """回傳的任何按鈕 URL 都不得含 running.biji.co（中覽站）。"""
    event = _open_event(
        official_url="https://bao-ming.com/eb/content/9999",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=9999",
    )
    mock_db = MagicMock()
    mock_db.get_events.return_value = [event]

    with (
        patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}),
        patch.object(main_module, "validate_init_data", return_value=True),
        patch.object(main_module, "get_db", return_value=mock_db),
        patch.object(main_module, "tw_today", return_value=date(2026, 6, 21)),
    ):
        async with quart_app.test_client() as client:
            resp = await client.get(
                "/api/events?type=open&city=all",
                headers={"Authorization": "test"},
            )

    assert resp.status_code == 200
    data = json.loads(await resp.get_data())
    for evt in data["events"]:
        assert "running.biji.co" not in evt["url"]
