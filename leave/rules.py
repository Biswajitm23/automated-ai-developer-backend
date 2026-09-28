"""Pure leave rules from the Project Brief (no database access).

Mirrors the frontend preview (frontend docs/ui-design.md §7) — same steps, same
messages — but the backend is authoritative.
"""

from datetime import date

from django.utils import timezone

MSG_START_IN_PAST = "Start date cannot be in the past."
MSG_END_BEFORE_START = "End date must be on or after the start date."
MSG_SPANS_YEARS = "Leave cannot span two calendar years. Submit a separate request for each year."
MSG_NO_WORKING_DAYS = "The selected dates contain no working days (Monday to Friday)."

SATURDAY = 5  # date.weekday(): Monday = 0 … Sunday = 6


def today_in_app_zone() -> date:
    """Today's calendar date in the application time zone (settings.TIME_ZONE, Asia/Kolkata)."""
    return timezone.localdate()


def count_working_days(start: date, end: date) -> int:
    """Monday–Friday days in [start, end], inclusive. 0 when end < start. O(1)."""
    total = (end - start).days + 1
    if total <= 0:
        return 0
    count = (total // 7) * 5
    first = start.weekday()
    for offset in range(total % 7):
        if (first + offset) % 7 < SATURDAY:
            count += 1
    return count


def date_errors(start: date, end: date, today: date | None = None) -> dict[str, list[str]]:
    """Errors in DRF's shape for a date range; empty when the range is acceptable.

    Order follows the frontend preview: past start, then reversed range, then year span,
    then "no working days" (the last two are form-level: non_field_errors).
    """
    today = today or today_in_app_zone()
    errors: dict[str, list[str]] = {}
    if start < today:
        errors["start_date"] = [MSG_START_IN_PAST]
    if end < start:
        errors["end_date"] = [MSG_END_BEFORE_START]
    if errors:
        return errors
    if start.year != end.year:
        return {"non_field_errors": [MSG_SPANS_YEARS]}
    if count_working_days(start, end) == 0:
        return {"non_field_errors": [MSG_NO_WORKING_DAYS]}
    return {}


def days_label(count: int, noun: str = "working day") -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def format_range(start: date, end: date) -> str:
    """'5 Oct – 7 Oct 2026' (same year), '5 Oct 2026' (one day)."""
    if start == end:
        return f"{start.day} {start:%b %Y}"
    left = f"{start.day} {start:%b}" if start.year == end.year else f"{start.day} {start:%b %Y}"
    return f"{left} – {end.day} {end:%b %Y}"

