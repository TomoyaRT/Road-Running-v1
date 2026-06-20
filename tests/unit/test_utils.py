from __future__ import annotations

from datetime import date, timedelta

from src.utils import tw_today


def test_tw_today_returns_date_type():
    assert isinstance(tw_today(), date)


def test_tw_today_within_one_day_of_utc():
    # TW is UTC+8, so TW date is the same as UTC date or one day ahead
    utc_today = date.today()
    result = tw_today()
    assert result in (utc_today, utc_today + timedelta(days=1))
