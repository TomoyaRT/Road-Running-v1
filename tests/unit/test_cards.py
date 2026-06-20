from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.bot.cards import (
    build_nav_markup,
    format_card_text,
    format_carousel_text,
    send_carousel_start,
    send_event_card,
)
from src.scraper.running_biji import RaceEvent

_EVENT = RaceEvent(
    name="台北馬拉松",
    race_date=date(2026, 11, 15),
    location="台北市",
    url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
    reg_start=date(2026, 6, 1),
    reg_end=date(2026, 8, 31),
)

_EVENT_WITH_IMAGE = RaceEvent(
    name="高雄路跑",
    race_date=date(2026, 12, 6),
    location="高雄市",
    url="https://running.biji.co/index.php?q=competition&act=info&cid=22222",
    reg_start=date(2026, 6, 5),
    reg_end=date(2026, 9, 15),
    image_url="https://example.com/image.jpg",
    categories=["42K全程組", "21K半程組"],
)

_EVENT_WITH_ORGANIZER = RaceEvent(
    name="花蓮超馬",
    race_date=date(2026, 10, 10),
    location="花蓮縣",
    url="https://running.biji.co/index.php?q=competition&act=info&cid=33333",
    reg_start=date(2026, 7, 1),
    reg_end=date(2026, 9, 30),
    organizer="台灣超馬協會",
    categories=["50K", "100K"],
)

# ── format_card_text ──────────────────────────────────────────────────────────


def test_format_card_text_contains_name():
    text = format_card_text(_EVENT)
    assert "台北馬拉松" in text


def test_format_card_text_contains_race_date():
    text = format_card_text(_EVENT)
    assert "2026-11-15" in text


def test_format_card_text_contains_location():
    text = format_card_text(_EVENT)
    assert "台北市" in text


def test_format_card_text_contains_reg_period():
    text = format_card_text(_EVENT)
    assert "06/01" in text
    assert "08/31" in text


def test_format_card_text_contains_categories_when_present():
    text = format_card_text(_EVENT_WITH_IMAGE)
    assert "42K全程組" in text
    assert "21K半程組" in text


def test_format_card_text_omits_categories_when_empty():
    text = format_card_text(_EVENT)
    assert "報名組別" not in text


def test_format_card_text_shows_organizer_when_present():
    text = format_card_text(_EVENT_WITH_ORGANIZER)
    assert "台灣超馬協會" in text


def test_format_card_text_omits_organizer_label_when_none():
    text = format_card_text(_EVENT)
    assert "主辦" not in text


def test_format_card_text_uses_html_bold_for_name():
    text = format_card_text(_EVENT)
    assert "<b>台北馬拉松</b>" in text


# ── send_event_card ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_event_card_uses_send_message_when_no_image():
    mock_bot = AsyncMock()
    await send_event_card(mock_bot, 123, _EVENT)

    mock_bot.send_message.assert_called_once()
    call = mock_bot.send_message.call_args
    assert call.kwargs["chat_id"] == 123
    assert "台北馬拉松" in call.kwargs["text"]
    assert call.kwargs["parse_mode"] == "HTML"
    mock_bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_card_uses_send_photo_when_image_present():
    mock_bot = AsyncMock()
    await send_event_card(mock_bot, 456, _EVENT_WITH_IMAGE)

    mock_bot.send_photo.assert_called_once()
    call = mock_bot.send_photo.call_args
    assert call.kwargs["chat_id"] == 456
    assert call.kwargs["photo"] == "https://example.com/image.jpg"
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_card_falls_back_to_message_on_photo_error():
    mock_bot = AsyncMock()
    mock_bot.send_photo.side_effect = Exception("network error")

    await send_event_card(mock_bot, 123, _EVENT_WITH_IMAGE)

    mock_bot.send_photo.assert_called_once()
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_event_card_includes_reg_button():
    mock_bot = AsyncMock()
    await send_event_card(mock_bot, 123, _EVENT)

    call = mock_bot.send_message.call_args
    markup = call.kwargs.get("reply_markup")
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    reg_buttons = [b for b in buttons if b.text == "立刻報名"]
    assert len(reg_buttons) == 1
    assert reg_buttons[0].url == _EVENT.url


@pytest.mark.asyncio
async def test_send_event_card_uses_official_url_when_present():
    mock_bot = AsyncMock()
    event = RaceEvent(
        name="測試活動",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=99999",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
        official_url="https://official-site.example.com/register",
    )
    await send_event_card(mock_bot, 123, event)

    call = mock_bot.send_message.call_args
    markup = call.kwargs.get("reply_markup")
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    reg_buttons = [b for b in buttons if b.text == "立刻報名"]
    assert reg_buttons[0].url == "https://official-site.example.com/register"


# ── format_carousel_text ──────────────────────────────────────────────────────


def test_format_carousel_text_contains_name_and_date():
    text = format_carousel_text(_EVENT, index=0, total=5)
    assert "台北馬拉松" in text
    assert "2026-11-15" in text


def test_format_carousel_text_contains_location_and_reg_period():
    text = format_carousel_text(_EVENT, index=0, total=5)
    assert "台北市" in text
    assert "06/01" in text
    assert "08/31" in text


def test_format_carousel_text_shows_index_and_total():
    text = format_carousel_text(_EVENT, index=2, total=10)
    assert "3 / 10" in text


def test_format_carousel_text_includes_categories_when_present():
    text = format_carousel_text(_EVENT_WITH_IMAGE, index=0, total=1)
    assert "42K全程組" in text


def test_format_carousel_text_shows_organizer_when_present():
    text = format_carousel_text(_EVENT_WITH_ORGANIZER, index=0, total=1)
    assert "台灣超馬協會" in text


def test_format_carousel_text_omits_organizer_label_when_none():
    text = format_carousel_text(_EVENT, index=0, total=1)
    assert "主辦" not in text


# ── build_nav_markup ──────────────────────────────────────────────────────────


def test_build_nav_markup_has_next_button_when_not_last():
    markup = build_nav_markup(
        "o", index=0, total=5, city="all", reg_url="https://example.com"
    )
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert any("nav:o:1:all" in d for d in all_data)


def test_build_nav_markup_has_prev_button_when_not_first():
    markup = build_nav_markup(
        "o", index=2, total=5, city="台北市", reg_url="https://example.com"
    )
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert any("nav:o:1:台北市" in d for d in all_data)


def test_build_nav_markup_no_prev_when_first():
    markup = build_nav_markup(
        "o", index=0, total=5, city="all", reg_url="https://example.com"
    )
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert not any("nav:o:-1:" in d for d in all_data)


def test_build_nav_markup_no_next_when_last():
    markup = build_nav_markup(
        "o", index=4, total=5, city="all", reg_url="https://example.com"
    )
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert not any("nav:o:5:" in d for d in all_data)


def test_build_nav_markup_always_has_reg_button():
    markup = build_nav_markup(
        "o", index=0, total=1, city="all", reg_url="https://reg.example.com"
    )
    url_buttons = [btn for row in markup.inline_keyboard for btn in row if btn.url]
    assert len(url_buttons) == 1
    assert url_buttons[0].url == "https://reg.example.com"
    assert url_buttons[0].text == "立刻報名"


# ── send_carousel_start ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_carousel_start_uses_send_photo_when_image_present():
    mock_bot = AsyncMock()
    events = [_EVENT_WITH_IMAGE]
    await send_carousel_start(mock_bot, 123, events, "o", "all")
    mock_bot.send_photo.assert_called_once()
    call = mock_bot.send_photo.call_args
    assert call.kwargs["photo"] == "https://example.com/image.jpg"
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_carousel_start_uses_placeholder_when_no_image():
    from src.bot.cards import PLACEHOLDER_IMAGE_URL

    mock_bot = AsyncMock()
    events = [_EVENT]  # no image_url
    await send_carousel_start(mock_bot, 123, events, "o", "all")
    mock_bot.send_photo.assert_called_once()
    call = mock_bot.send_photo.call_args
    assert call.kwargs["photo"] == PLACEHOLDER_IMAGE_URL
    mock_bot.send_message.assert_not_called()
