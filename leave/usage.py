"""Leave already taken or reserved against an employee's allowances.

Approved leave is "used"; pending requests "reserve" balance (Project Brief). Leave
requests arrive with ELM-005; until then nothing is used or reserved. This module is
the single place allowance checks read usage from, so ELM-005 only has to fill in
`_usage_rows`.
"""

from dataclasses import dataclass

from .models import LeaveType


@dataclass(frozen=True)
class Usage:
    approved: int = 0
    pending: int = 0

    @property
    def committed(self) -> int:
        """Days an allowance may not drop below."""
        return self.approved + self.pending


def _usage_rows(employee, year: int) -> dict[str, Usage]:
    # ELM-005: sum working_days of APPROVED and PENDING requests per leave type here.
    return {}


def usage_for(employee, year: int) -> dict[str, Usage]:
    """Usage per leave type code for one employee and calendar year (every type present)."""
    rows = _usage_rows(employee, year)
    return {code: rows.get(code, Usage()) for code in LeaveType.values}
