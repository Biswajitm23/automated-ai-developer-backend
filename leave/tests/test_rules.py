from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.test import SimpleTestCase

from leave.rules import (
    MSG_END_BEFORE_START,
    MSG_NO_WORKING_DAYS,
    MSG_SPANS_YEARS,
    MSG_START_IN_PAST,
    count_working_days,
    date_errors,
    format_range,
    today_in_app_zone,
)

D = date.fromisoformat
TODAY = D("2026-09-23")  # a Wednesday


class CountWorkingDaysTests(SimpleTestCase):
    def test_reference_cases_from_the_ui_design(self):
        cases = [
            ("2026-09-25", "2026-09-25", 1),  # same-day leave on a Friday
            ("2026-09-26", "2026-09-27", 0),  # weekend only
            ("2026-09-25", "2026-09-28", 2),  # Fri–Mon across a weekend
            ("2026-09-28", "2026-10-11", 10),  # two full weeks
        ]
        for start, end, expected in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(count_working_days(D(start), D(end)), expected)

    def test_same_day_on_saturday_is_zero(self):
        self.assertEqual(count_working_days(D("2026-09-26"), D("2026-09-26")), 0)

    def test_reversed_range_is_zero(self):
        self.assertEqual(count_working_days(D("2026-10-05"), D("2026-10-02")), 0)

    def test_matches_day_by_day_count_for_every_start_weekday_and_length(self):
        base = D("2026-01-05")  # Monday
        for start_offset in range(7):
            for length in range(0, 40):
                start = base + timedelta(days=start_offset)
                end = start + timedelta(days=length)
                expected = sum(
                    1 for i in range(length + 1) if (start + timedelta(days=i)).weekday() < 5
                )
                self.assertEqual(count_working_days(start, end), expected, (start, end))


class DateErrorsTests(SimpleTestCase):
    def check(self, start, end):
        return date_errors(D(start), D(end), today=TODAY)

    def test_valid_range_including_today(self):
        self.assertEqual(self.check("2026-09-23", "2026-09-23"), {})

    def test_past_start(self):
        self.assertEqual(self.check("2026-09-22", "2026-09-24"), {"start_date": [MSG_START_IN_PAST]})

    def test_reversed_range(self):
        self.assertEqual(self.check("2026-10-05", "2026-10-02"), {"end_date": [MSG_END_BEFORE_START]})

    def test_past_start_and_reversed_range_are_both_reported(self):
        self.assertEqual(
            self.check("2026-09-20", "2026-09-19"),
            {"start_date": [MSG_START_IN_PAST], "end_date": [MSG_END_BEFORE_START]},
        )

    def test_cross_year(self):
        self.assertEqual(self.check("2026-12-31", "2027-01-01"), {"non_field_errors": [MSG_SPANS_YEARS]})

    def test_weekend_only(self):
        self.assertEqual(self.check("2026-09-26", "2026-09-27"), {"non_field_errors": [MSG_NO_WORKING_DAYS]})


class TimeZoneTests(SimpleTestCase):
    def test_today_uses_asia_kolkata(self):
        # 20:00 UTC on 22 Sep is already 01:30 on 23 Sep in India.
        instant = datetime(2026, 9, 22, 20, 0, tzinfo=dt_timezone.utc)
        with mock.patch("django.utils.timezone.now", return_value=instant):
            self.assertEqual(today_in_app_zone(), D("2026-09-23"))


class FormatRangeTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(format_range(D("2026-10-05"), D("2026-10-07")), "5 Oct – 7 Oct 2026")
        self.assertEqual(format_range(D("2026-10-05"), D("2026-10-05")), "5 Oct 2026")
