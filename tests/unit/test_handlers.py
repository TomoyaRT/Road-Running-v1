from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.bot.handlers import (
    build_hour_keyboard,
    build_region_keyboard,
    build_region_only_keyboard,
    build_settings_keyboard,
    build_slot_keyboard,
    city_callback,
    city_only_callback,
    handle_text_message,
    hour_callback,
    open_settings_callback,
    region_callback,
    region_only_callback,
    settings_city_callback,
    settings_time_callback,
    slot_callback,
    start_command,
    unsubscribe_btn_callback,
    unsubscribe_command,
)
from src.scraper.running_biji import RaceEvent

# ── /start ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_command_sends_welcome_with_persistent_keyboard(
    mock_update, mock_context
):
    await start_command(mock_update, mock_context)

    assert mock_update.message.reply_text.call_count == 2
    first_call = mock_update.message.reply_text.call_args_list[0]
    text = first_call.args[0] if first_call.args else first_call.kwargs["text"]
    markup = first_call.kwargs.get("reply_markup")
    assert "歡迎" in text
    assert isinstance(markup, ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_command_sends_slot_selection_keyboard(mock_update, mock_context):
    await start_command(mock_update, mock_context)

    second_call = mock_update.message.reply_text.call_args_list[1]
    markup = second_call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("slot:") for d in all_data)


# ── slot_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slot_callback_shows_hour_buttons(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "slot:s1"
    await slot_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("hour:") for d in all_data)


@pytest.mark.asyncio
async def test_slot_callback_shows_hours_in_s1_range(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:s1"
    await slot_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {5, 6, 7, 8, 9, 10}


@pytest.mark.asyncio
async def test_slot_callback_shows_hours_in_s4_range(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:s4"
    await slot_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {20, 21, 22, 23}


# ── hour_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hour_callback_shows_city_selection_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:9"
    await hour_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("region:9:") for d in all_data)


@pytest.mark.asyncio
async def test_hour_callback_includes_selected_hour_in_region_callbacks(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:20"
    await hour_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("region:20:") or d == "city:20:all" for d in all_data)


@pytest.mark.asyncio
async def test_hour_callback_does_not_save_subscription(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:8"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await hour_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_not_called()


# ── city_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_city_callback_saves_subscription(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city:9:台北市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        notification_hour=9,
        preferred_city="台北市",
    )


@pytest.mark.asyncio
async def test_city_callback_saves_all_city(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city:14:all"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        notification_hour=14,
        preferred_city="all",
    )


@pytest.mark.asyncio
async def test_city_callback_shows_confirmation_for_returning_subscriber(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city:9:台北市"
    mock_db = MagicMock()
    mock_db.subscribe.return_value = False  # 舊訂閱者

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "09:00" in text
    assert "台北市" in text
    assert "設定完成" in text
    assert "感謝" not in text


@pytest.mark.asyncio
async def test_city_callback_shows_thank_you_for_new_subscriber(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city:9:台北市"
    mock_db = MagicMock()
    mock_db.subscribe.return_value = True  # 首次訂閱

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "09:00" in text
    assert "台北市" in text
    assert "感謝" in text


# ── open_settings_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_settings_callback_shows_settings_menu(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "open_settings"
    await open_settings_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── settings_time_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_time_callback_shows_slot_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "settings_time"
    await settings_time_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("slot:") for d in all_data)


# ── settings_city_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_city_callback_shows_city_only_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "settings_city"
    await settings_city_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("city_only:") for d in all_data)


# ── city_only_callback ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_city_only_callback_calls_update_city(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city_only:台中市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    mock_db.update_city.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        preferred_city="台中市",
    )


@pytest.mark.asyncio
async def test_city_only_callback_does_not_touch_hour(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city_only:all"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_city_only_callback_shows_confirmation(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city_only:高雄市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "高雄市" in text


# ── unsubscribe_btn_callback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_btn_callback_deletes_user(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "unsubscribe_btn"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_btn_callback(mock_callback_update, mock_context)

    mock_db.unsubscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id
    )


@pytest.mark.asyncio
async def test_unsubscribe_btn_callback_shows_confirmation(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "unsubscribe_btn"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_btn_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "取消" in text


# ── handle_text_message ────────────────────────────────────────────────────────

_SAMPLE_EVENTS = [
    RaceEvent(
        name="台北馬拉松",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
    )
]


def _mock_db_city(city: str = "all") -> MagicMock:
    db = MagicMock()
    db.get_user_city.return_value = city
    return db


@pytest.mark.asyncio
async def test_handle_text_open_events_sends_webapp_button(mock_update, mock_context):
    mock_update.message.text = "查詢可報名活動"

    with (
        patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}),
        patch("src.bot.handlers.get_db", return_value=_mock_db_city()),
    ):
        await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(
        btn.web_app is not None and "type=open" in btn.web_app.url for btn in buttons
    )


@pytest.mark.asyncio
async def test_handle_text_open_events_includes_user_city_in_url(
    mock_update, mock_context
):
    """查詢時 mini app URL 應帶入使用者已設定的城市（URL-encoded）。"""
    from urllib.parse import quote

    mock_update.message.text = "查詢可報名活動"

    with (
        patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}),
        patch("src.bot.handlers.get_db", return_value=_mock_db_city("台北市")),
    ):
        await handle_text_message(mock_update, mock_context)

    buttons = [
        btn
        for row in mock_update.message.reply_text.call_args.kwargs[
            "reply_markup"
        ].inline_keyboard
        for btn in row
    ]
    urls = [btn.web_app.url for btn in buttons if btn.web_app]
    assert any(quote("台北市") in url for url in urls)


@pytest.mark.asyncio
async def test_handle_text_open_events_city_defaults_to_all(mock_update, mock_context):
    """未設定地區時 city=all 應出現在 URL 中。"""
    mock_update.message.text = "查詢可報名活動"

    with (
        patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}),
        patch("src.bot.handlers.get_db", return_value=_mock_db_city("all")),
    ):
        await handle_text_message(mock_update, mock_context)

    buttons = [
        btn
        for row in mock_update.message.reply_text.call_args.kwargs[
            "reply_markup"
        ].inline_keyboard
        for btn in row
    ]
    urls = [btn.web_app.url for btn in buttons if btn.web_app]
    assert any("city=all" in url for url in urls)


@pytest.mark.asyncio
async def test_handle_text_upcoming_events_sends_webapp_button(
    mock_update, mock_context
):
    mock_update.message.text = "即將開放活動"

    with (
        patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}),
        patch("src.bot.handlers.get_db", return_value=_mock_db_city()),
    ):
        await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(
        btn.web_app is not None and "type=upcoming" in btn.web_app.url
        for btn in buttons
    )


@pytest.mark.asyncio
async def test_handle_text_upcoming_events_includes_user_city_in_url(
    mock_update, mock_context
):
    """即將開放活動查詢 URL 也應帶城市。"""
    from urllib.parse import quote

    mock_update.message.text = "即將開放活動"

    with (
        patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}),
        patch("src.bot.handlers.get_db", return_value=_mock_db_city("高雄市")),
    ):
        await handle_text_message(mock_update, mock_context)

    buttons = [
        btn
        for row in mock_update.message.reply_text.call_args.kwargs[
            "reply_markup"
        ].inline_keyboard
        for btn in row
    ]
    urls = [btn.web_app.url for btn in buttons if btn.web_app]
    assert any(quote("高雄市") in url for url in urls)


@pytest.mark.asyncio
async def test_handle_text_settings_shows_settings_keyboard(mock_update, mock_context):
    mock_update.message.text = "設定"
    await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── /unsubscribe ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_deletes_user(mock_update, mock_context):
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_command(mock_update, mock_context)

    mock_db.unsubscribe.assert_called_once_with(user_id=mock_update.effective_user.id)
    text = mock_update.message.reply_text.call_args.args[0]
    assert "取消" in text


# ── build_hour_keyboard ────────────────────────────────────────────────────────


def test_build_hour_keyboard_s1_has_correct_range():
    markup = build_hour_keyboard("s1")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {5, 6, 7, 8, 9, 10}


def test_build_hour_keyboard_s2_has_correct_range():
    markup = build_hour_keyboard("s2")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {10, 11, 12, 13, 14, 15}


def test_build_hour_keyboard_s3_has_correct_range():
    markup = build_hour_keyboard("s3")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {15, 16, 17, 18, 19, 20}


def test_build_hour_keyboard_s4_has_correct_range():
    markup = build_hour_keyboard("s4")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {20, 21, 22, 23}


def test_build_hour_keyboard_uses_three_per_row():
    markup = build_hour_keyboard("s1")
    for row in markup.inline_keyboard:
        assert len(row) <= 3


# ── build_slot_keyboard ────────────────────────────────────────────────────────


def test_build_slot_keyboard_has_four_slots():
    markup = build_slot_keyboard()
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 4
    assert all(btn.callback_data.startswith("slot:") for btn in buttons)


def test_build_slot_keyboard_has_two_per_row():
    markup = build_slot_keyboard()
    for row in markup.inline_keyboard:
        assert len(row) == 2


def test_build_slot_keyboard_covers_all_slots():
    markup = build_slot_keyboard()
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "slot:s1" in all_data
    assert "slot:s2" in all_data
    assert "slot:s3" in all_data
    assert "slot:s4" in all_data


# ── build_city_keyboard ────────────────────────────────────────────────────────


def test_build_region_keyboard_contains_all_regions():
    markup = build_region_keyboard(hour=9)
    all_labels = [btn.text for row in markup.inline_keyboard for btn in row]
    for label in ["北部", "中部", "南部", "東部", "離島", "不限地區"]:
        assert label in all_labels


def test_build_region_keyboard_embeds_hour_in_region_callbacks():
    markup = build_region_keyboard(hour=9)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("region:9:") for d in all_data)


def test_build_region_keyboard_all_taiwan_uses_city_callback():
    markup = build_region_keyboard(hour=9)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "city:9:all" in all_data


# ── build_settings_keyboard ───────────────────────────────────────────────────


def test_build_settings_keyboard_has_time_city_and_unsubscribe():
    markup = build_settings_keyboard()
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── build_city_only_keyboard ──────────────────────────────────────────────────


def test_build_region_only_keyboard_contains_all_regions():
    markup = build_region_only_keyboard()
    all_labels = [btn.text for row in markup.inline_keyboard for btn in row]
    for label in ["北部", "中部", "南部", "東部", "離島", "不限地區"]:
        assert label in all_labels


def test_build_region_only_keyboard_all_taiwan_uses_city_only_callback():
    markup = build_region_only_keyboard()
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "city_only:all" in all_data


@pytest.mark.asyncio
async def test_region_callback_shows_north_cities(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "region:8:north"
    await region_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    all_labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "台北市" in all_labels
    assert "新北市" in all_labels
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("city:8:") for d in all_data)


@pytest.mark.asyncio
async def test_region_only_callback_shows_south_cities(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "region_only:south"
    await region_only_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    all_labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert "高雄市" in all_labels
    assert "台南市" in all_labels
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("city_only:") for d in all_data)
