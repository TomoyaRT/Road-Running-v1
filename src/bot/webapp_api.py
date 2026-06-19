from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl

_MAX_AGE_SECONDS = 86400  # 24 小時


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """驗證 Telegram Mini App 傳來的 initData HMAC 簽章與時效。"""
    if not init_data:
        return False
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_value = parsed.pop("hash", "")
    if not hash_value:
        return False
    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > _MAX_AGE_SECONDS:
        return False
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, hash_value)
