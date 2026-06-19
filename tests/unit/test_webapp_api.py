from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from src.bot.webapp_api import validate_init_data


def _make_valid_init_data(bot_token: str, payload: dict) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_value = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode({**payload, "hash": hash_value})


def _fresh_auth_date() -> str:
    return str(int(time.time()))


def test_validate_init_data_valid():
    token = "test_bot_token"
    init_data = _make_valid_init_data(
        token, {"user": '{"id":123}', "auth_date": _fresh_auth_date()}
    )
    assert validate_init_data(init_data, token) is True


def test_validate_init_data_wrong_hash():
    auth_date = _fresh_auth_date()
    init_data = f"user=%7B%22id%22%3A123%7D&auth_date={auth_date}&hash=badhash"
    assert validate_init_data(init_data, "test_bot_token") is False


def test_validate_init_data_missing_hash():
    auth_date = _fresh_auth_date()
    init_data = f"user=%7B%22id%22%3A123%7D&auth_date={auth_date}"
    assert validate_init_data(init_data, "test_bot_token") is False


def test_validate_init_data_empty_string():
    assert validate_init_data("", "test_bot_token") is False


def test_validate_init_data_wrong_token():
    init_data = _make_valid_init_data(
        "real_token", {"user": '{"id":123}', "auth_date": _fresh_auth_date()}
    )
    assert validate_init_data(init_data, "wrong_token") is False


def test_validate_init_data_expired_auth_date():
    token = "test_bot_token"
    expired = str(int(time.time()) - 90000)  # 25 小時前
    init_data = _make_valid_init_data(
        token, {"user": '{"id":123}', "auth_date": expired}
    )
    assert validate_init_data(init_data, token) is False
