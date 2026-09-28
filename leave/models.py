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
