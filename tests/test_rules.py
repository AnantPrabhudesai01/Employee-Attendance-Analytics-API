"""Pure business-rule checks. No MongoDB needed."""
from datetime import datetime, timedelta, timezone

from app.main import (
    attendance_date_for,
    avg4,
    avg2_half_up,
    compute_late_minutes,
    compute_overtime_minutes,
    pct2,
    rate4,
    shift_end_utc,
    utc_from_ms,
    work_hours_half_up,
    working_days_in_month,
)

IST = timezone(timedelta(hours=5, minutes=30))


def ist(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=IST).astimezone(timezone.utc)


def test_truncate_to_seconds():
    # 1783312500900 ms = 10:05:00.900 IST -> truncated 10:05:00 IST = 04:35:00 UTC
    assert utc_from_ms(1783312500900) == datetime(2026, 7, 6, 4, 35, tzinfo=timezone.utc)


def test_r2_boundaries():
    assert compute_late_minutes(ist(2026, 7, 6, 9, 40, 0), "2026-07-06", "09:30") == 0
    assert compute_late_minutes(ist(2026, 7, 6, 9, 40, 1), "2026-07-06", "09:30") == 10
    assert compute_late_minutes(ist(2026, 7, 6, 10, 15, 59), "2026-07-06", "09:30") == 45
    assert compute_late_minutes(ist(2026, 7, 6, 9, 10, 0), "2026-07-06", "09:30") == 0


def test_r1_day_and_overnight():
    assert attendance_date_for(ist(2026, 7, 6, 9, 28), "09:30", "18:30") == "2026-07-06"
    assert attendance_date_for(ist(2026, 7, 7, 1, 0), "22:00", "06:00") == "2026-07-06"
    assert attendance_date_for(ist(2026, 7, 6, 21, 55), "22:00", "06:00") == "2026-07-06"


def test_r3_minimum_and_floor():
    assert compute_overtime_minutes(datetime(2026, 7, 6, 13, 5, tzinfo=timezone.utc), "2026-07-06", "18:30", "09:30") == 0
    assert compute_overtime_minutes(datetime(2026, 7, 6, 13, 40, tzinfo=timezone.utc), "2026-07-06", "18:30", "09:30") == 40


def test_r4_half_up_not_bankers():
    a = datetime(2026, 7, 6, 3, 58, tzinfo=timezone.utc)
    assert work_hours_half_up(a, datetime(2026, 7, 6, 13, 5, tzinfo=timezone.utc)) == 9.12
    assert work_hours_half_up(datetime(2026, 7, 6, 0, 0, tzinfo=timezone.utc), datetime(2026, 7, 6, 2, 40, 30, tzinfo=timezone.utc)) == 2.68


def test_r5_and_rates():
    assert (3.5 < 4.50) is True
    assert rate4(0, 6, True) == 0.0
    assert rate4(1, 6, False) is None
    assert avg4([0.5, 0.0]) == 0.25
    assert pct2(1.5, 23) == 6.52
    assert pct2(0, 0) is None
    assert avg2_half_up([9.12, 9.08]) == 9.1
    assert working_days_in_month("2026-01-05", "2026-07") == 23
    assert working_days_in_month("2026-07-13", "2026-07") == 15


def test_overnight_end_next_day():
    assert shift_end_utc("2026-07-06", "06:00", "22:00") == datetime(2026, 7, 7, 0, 30, tzinfo=timezone.utc)
