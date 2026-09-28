"""Balance-affecting operations (Project Brief, ELM-004).

Every function that can change what an employee has used or reserved first locks that
employee's user row (SELECT … FOR UPDATE) inside a transaction. Allowance edits
(leave.views.AllowanceDetailView) take the same lock, so for one employee these
operations run one at a time: two concurrent requests cannot both pass the balance
check, and an approval cannot race a cancellation. Lock order is always employee row,
then request row.
"""

from dataclasses import dataclass
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from .models import ACTIVE_STATUSES, Allowance, LeaveRequest, LeaveType, RequestStatus
from .rules import count_working_days, date_errors, days_label, format_range
from .usage import usage_for

User = get_user_model()


class Conflict(APIException):
    """409: the request is no longer in a state that allows this action."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This request has changed. Reload and try again."
    default_code = "conflict"


@dataclass(frozen=True)
class Balance:
    leave_type: str
    year: int
    allowance: int
    approved: int
    pending: int

    @property
    def available(self) -> int:
        return self.allowance - self.approved - self.pending

    def as_dict(self) -> dict:
        return {
            "leave_type": self.leave_type,
            "year": self.year,
            "allowance": self.allowance,
            "approved": self.approved,
            "pending": self.pending,
            "available": self.available,
        }


def balances_for(employee, year: int) -> dict[str, Balance]:
    """Balance per leave type code (every type present; no allowance row = 0 days)."""
    allowances = dict(
        Allowance.objects.filter(employee=employee, year=year).values_list("leave_type", "days")
    )
    usage = usage_for(employee, year)
    return {
        code: Balance(code, year, allowances.get(code, 0), usage[code].approved, usage[code].pending)
        for code in LeaveType.values
    }


def _lock_employee(employee_id: int):
    return User.objects.select_for_update().get(pk=employee_id)


def _overlapping(employee, start: date, end: date):
    return (
        LeaveRequest.objects.filter(
            employee=employee,
            status__in=ACTIVE_STATUSES,
            start_date__lte=end,
            end_date__gte=start,
        )
        .order_by("start_date", "id")
        .first()
    )


def check_request(employee, leave_type: str, start: date, end: date, today: date | None = None):
    """Validate a new request without saving it. Returns (working_days, balance) or raises
    ValidationError (400) with DRF-shaped errors, in the order the UI expects."""
    if leave_type not in LeaveType.values:
        raise ValidationError({"leave_type": ["Select a valid choice."]})
    errors = date_errors(start, end, today)
    if errors:
        raise ValidationError(errors)
    working_days = count_working_days(start, end)

    clash = _overlapping(employee, start, end)
    if clash is not None:
        raise ValidationError(
            {
                "non_field_errors": [
                    f"These dates overlap your pending or approved request #{clash.pk} "
                    f"({format_range(clash.start_date, clash.end_date)})."
                ]
            }
        )

    balance = balances_for(employee, start.year)[leave_type]
    if working_days > balance.available:
        raise ValidationError(
            {
                "non_field_errors": [
                    f"Not enough {LeaveType(leave_type).label}: {days_label(working_days)} requested, "
                    f"{max(balance.available, 0)} available."
                ]
            }
        )
    return working_days, balance


def create_request(
    employee,
    leave_type: str,
    start: date,
    end: date,
    reason: str,
    today: date | None = None,
    client_request_id=None,
) -> LeaveRequest:
    """Create a PENDING request that reserves its working days, or raise ValidationError.

    With `client_request_id`, a repeat from the same employee returns the original request
    unchanged (check `request.created_now`); the check runs under the employee lock, so two
    simultaneous submissions of one form still create a single request.
    """
    with transaction.atomic():
        employee = _lock_employee(employee.pk)
        if client_request_id is not None:
            existing = LeaveRequest.objects.filter(
                employee=employee, client_request_id=client_request_id
            ).first()
            if existing is not None:
                existing.created_now = False
                return existing
        working_days, _ = check_request(employee, leave_type, start, end, today)
        leave_request = LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start,
            end_date=end,
            working_days=working_days,
            reason=reason,
            status=RequestStatus.PENDING,
            client_request_id=client_request_id,
        )
        leave_request.created_now = True
        return leave_request


def _lock_request(request_id: int) -> LeaveRequest:
    """Lock the owning employee, then the request (fixed lock order)."""
    employee_id = LeaveRequest.objects.values_list("employee_id", flat=True).get(pk=request_id)
    _lock_employee(employee_id)
    return LeaveRequest.objects.select_for_update().select_related("employee").get(pk=request_id)


def _assert_pending(leave_request: LeaveRequest) -> None:
    if leave_request.status != RequestStatus.PENDING:
        raise Conflict(
            f"This request has already been processed ({leave_request.get_status_display()})."
        )


def approve_request(request_id: int, reviewer, remarks: str = "") -> LeaveRequest:
    """PENDING → APPROVED: the reservation becomes used leave. Rechecks status and that the
    allowance still covers everything approved and pending (409 otherwise)."""
    with transaction.atomic():
        leave_request = _lock_request(request_id)
        _assert_pending(leave_request)
        year = leave_request.start_date.year
        balance = balances_for(leave_request.employee, year)[leave_request.leave_type]
        # This request is already counted in `pending`, so approving it changes nothing
        # unless the allowance no longer covers approved + pending.
        if balance.available < 0:
            raise Conflict(
                f"Approval would exceed the {LeaveType(leave_request.leave_type).label} allowance "
                f"for {year} ({days_label(balance.allowance, 'day')})."
            )
        leave_request.status = RequestStatus.APPROVED
        leave_request.reviewed_by = reviewer
        leave_request.reviewed_at = timezone.now()
        leave_request.review_remarks = remarks
        leave_request.save()
        return leave_request


def reject_request(request_id: int, reviewer, remarks: str) -> LeaveRequest:
    """PENDING → REJECTED: the reservation is released."""
    with transaction.atomic():
        leave_request = _lock_request(request_id)
        _assert_pending(leave_request)
        leave_request.status = RequestStatus.REJECTED
        leave_request.reviewed_by = reviewer
        leave_request.reviewed_at = timezone.now()
        leave_request.review_remarks = remarks
        leave_request.save()
        return leave_request


def cancel_request(request_id: int) -> LeaveRequest:
    """PENDING → CANCELLED by the employee: the reservation is released. A second cancel is
    a 409, so the balance is never released twice."""
    with transaction.atomic():
        leave_request = _lock_request(request_id)
        if leave_request.status != RequestStatus.PENDING:
            raise Conflict(
                "Only pending requests can be cancelled. "
                f"This request is {leave_request.get_status_display()}."
            )
        leave_request.status = RequestStatus.CANCELLED
        leave_request.cancelled_at = timezone.now()
        leave_request.save()
        return leave_request
