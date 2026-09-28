"""Leave already taken or reserved against an employee's allowances.

Approved requests are "used"; pending requests "reserve" balance; rejected and
cancelled requests hold nothing (Project Brief). A request belongs to the year of its
start date — requests never span two years.
"""

from dataclasses import dataclass

from django.db.models import Sum

from .models import LeaveRequest, LeaveType, RequestStatus


@dataclass(frozen=True)
class Usage:
    approved: int = 0
    pending: int = 0

    @property
    def committed(self) -> int:
        """Days an allowance may not drop below, and that are not available to new requests."""
        return self.approved + self.pending


def usage_for(employee, year: int) -> dict[str, Usage]:
    """Usage per leave type code for one employee and calendar year (every type present)."""
    totals = (
        LeaveRequest.objects.filter(
            employee=employee,
            start_date__year=year,
            status__in=[RequestStatus.APPROVED, RequestStatus.PENDING],
        )
        .values("leave_type", "status")
        .annotate(days=Sum("working_days"))
    )
    days = {(row["leave_type"], row["status"]): row["days"] for row in totals}
    return {
        code: Usage(
            approved=days.get((code, RequestStatus.APPROVED), 0),
            pending=days.get((code, RequestStatus.PENDING), 0),
        )
        for code in LeaveType.values
    }
