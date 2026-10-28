from datetime import date

import pytest

from mock_hris.workdays import add_working_days, breakdown, count_working_days

HOL = {date(2026, 12, 7), date(2026, 12, 10), date(2026, 12, 31)}


def test_friday_plus_substitution_monday_is_one_day():  # UC1
    assert count_working_days(date(2026, 12, 4), date(2026, 12, 7), HOL) == 1


def test_weekends_not_counted():
    assert count_working_days(date(2026, 11, 5), date(2026, 11, 10), HOL) == 4  # Thu..Tue


def test_half_day():
    assert count_working_days(date(2026, 11, 5), date(2026, 11, 5), HOL, "am") == 0.5
    assert count_working_days(date(2026, 12, 7), date(2026, 12, 7), HOL, "pm") == 0  # holiday


def test_half_day_must_be_single_date():
    with pytest.raises(ValueError):
        count_working_days(date(2026, 11, 5), date(2026, 11, 6), HOL, "am")


def test_reversed_range():
    with pytest.raises(ValueError):
        count_working_days(date(2026, 11, 6), date(2026, 11, 5), HOL)


def test_breakdown_labels():
    b = breakdown(date(2026, 12, 4), date(2026, 12, 7), {date(2026, 12, 7): "วันหยุดชดเชยวันพ่อ"})
    assert [d["type"] for d in b["days"]] == ["working_day", "weekend", "weekend", "holiday"]
    assert b["working_days"] == 1


def test_add_working_days_skips_holidays():
    # Fri 4 Dec + 1 working day -> Tue 8 Dec (Mon 7 is a holiday)
    assert add_working_days(date(2026, 12, 4), 1, HOL) == date(2026, 12, 8)
