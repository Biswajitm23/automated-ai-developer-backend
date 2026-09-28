from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

MIN_YEAR = 2000
MAX_YEAR = 2100
MAX_ALLOWANCE_DAYS = 366


class LeaveType(models.TextChoices):
    """Phase 1 leave types. Fixed in code: adding one needs policy and UI changes anyway."""

    CASUAL = "CASUAL", "Casual Leave"
    SICK = "SICK", "Sick Leave"


class Allowance(models.Model):
    """Annual days of one leave type for one employee. No row means 0 days."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="allowances"
    )
    year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MIN_YEAR), MaxValueValidator(MAX_YEAR)]
    )
    leave_type = models.CharField(max_length=16, choices=LeaveType.choices)
    days = models.PositiveSmallIntegerField(validators=[MaxValueValidator(MAX_ALLOWANCE_DAYS)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "year", "leave_type"], name="unique_allowance_per_year_type"
            ),
            models.CheckConstraint(
                condition=models.Q(days__gte=0) & models.Q(days__lte=MAX_ALLOWANCE_DAYS),
                name="allowance_days_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(leave_type__in=LeaveType.values), name="allowance_known_leave_type"
            ),
        ]
        ordering = ["employee_id", "year", "leave_type"]

    def __str__(self) -> str:
        return f"{self.employee.get_username()} {self.year} {self.leave_type}: {self.days}"


class RequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


# Statuses that hold balance: pending reserves it, approved uses it.
ACTIVE_STATUSES = (RequestStatus.PENDING, RequestStatus.APPROVED)

REASON_MAX_LENGTH = 500
REMARKS_MAX_LENGTH = 500


class LeaveRequest(models.Model):
    """One full-day leave request. Create and change it only through leave.services,
    which applies the Project Brief rules under a per-employee lock."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_requests"
    )
    leave_type = models.CharField(max_length=16, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    # Monday–Friday days in [start_date, end_date], fixed when the request is created.
    working_days = models.PositiveSmallIntegerField()
    reason = models.TextField(max_length=REASON_MAX_LENGTH)
    status = models.CharField(
        max_length=16, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_remarks = models.TextField(max_length=REMARKS_MAX_LENGTH, blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Generated once per form by the frontend; a repeated submission returns the original.
    client_request_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "client_request_id"], name="leave_request_unique_client_id"
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="leave_request_end_not_before_start",
            ),
            models.CheckConstraint(
                condition=models.Q(working_days__gte=1), name="leave_request_has_working_days"
            ),
            models.CheckConstraint(
                condition=models.Q(leave_type__in=LeaveType.values), name="leave_request_known_type"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RequestStatus.values), name="leave_request_known_status"
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "status", "start_date"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.employee.get_username()} {self.leave_type} {self.start_date}–{self.end_date} {self.status}"
