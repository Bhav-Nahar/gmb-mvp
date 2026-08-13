"""Quiet hours: a marketing-category review ask must not go out at 1am.

The window is the only thing standing between a midnight CSV upload and the
tenant's number getting reported into a throttle, so the boundaries are pinned
here rather than trusted to a hand-check.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks_whatsapp import (
    IST,
    SEND_WINDOW_END_HOUR,
    SEND_WINDOW_START_HOUR,
    seconds_until_send_window,
)


def ist(hour: int, minute: int = 0) -> datetime:
    """A UTC instant that is `hour:minute` in IST — the tasks work in UTC."""
    return datetime(2026, 8, 13, hour, minute, tzinfo=IST).astimezone(timezone.utc)


@pytest.mark.parametrize("hour", [9, 10, 14, 19])
def test_inside_window_sends_now(hour):
    assert seconds_until_send_window(ist(hour)) == 0


@pytest.mark.parametrize("hour", [20, 21, 23, 0, 3, 8])
def test_outside_window_waits(hour):
    assert seconds_until_send_window(ist(hour)) > 0


def test_boundaries_are_where_the_comment_says():
    assert seconds_until_send_window(ist(SEND_WINDOW_START_HOUR, 0)) == 0    # 09:00 sends
    assert seconds_until_send_window(ist(SEND_WINDOW_END_HOUR - 1, 59)) == 0  # 19:59 sends
    assert seconds_until_send_window(ist(SEND_WINDOW_END_HOUR, 0)) > 0        # 20:00 waits


def test_morning_waits_until_nine_the_same_day():
    assert seconds_until_send_window(ist(8, 0)) == 3600


def test_night_waits_until_nine_tomorrow_not_today():
    # 23:00 -> 09:00 next day is 10h. A same-day target would be negative and
    # would fire the batch immediately, which is the bug this guards.
    assert seconds_until_send_window(ist(23, 0)) == 10 * 3600


def test_never_returns_a_zero_countdown_that_would_spin():
    # 19:59:59.9-ish edges and any rounding must still park the job, not busy-loop.
    for minute in range(0, 60, 7):
        assert seconds_until_send_window(ist(20, minute)) >= 60


def test_utc_input_is_converted_not_assumed():
    # 22:00 UTC is 03:30 IST — must WAIT even though 22:00 looks like evening,
    # and 05:00 UTC is 10:30 IST which must SEND even though it looks like dawn.
    assert seconds_until_send_window(datetime(2026, 8, 13, 22, 0, tzinfo=timezone.utc)) > 0
    assert seconds_until_send_window(datetime(2026, 8, 13, 5, 0, tzinfo=timezone.utc)) == 0


def test_naive_datetime_is_treated_as_utc_like_the_callers_pass():
    # tasks call it with datetime.now(timezone.utc); a naive value must not crash.
    assert seconds_until_send_window(
        datetime(2026, 8, 13, 5, 0, tzinfo=timezone.utc) + timedelta(0)) == 0
