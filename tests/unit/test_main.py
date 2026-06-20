from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.main as main_module
from src.main import notify_endpoint


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
