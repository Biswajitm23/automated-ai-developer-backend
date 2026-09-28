from django.contrib import admin

from .models import Allowance, LeaveRequest


@admin.register(Allowance)
class AllowanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "year", "leave_type", "days", "updated_at")
    list_filter = ("year", "leave_type")
    search_fields = ("employee__username", "employee__email", "employee__first_name", "employee__last_name")
    # Allowances are changed through the API, which enforces the approved + pending minimum.
    readonly_fields = ("employee", "year", "leave_type", "days", "created_at", "updated_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    """Read-only view. Requests change only through the API, which applies the balance rules."""

    list_display = ("id", "employee", "leave_type", "start_date", "end_date", "working_days", "status", "created_at")
    list_filter = ("status", "leave_type")
    search_fields = ("employee__username", "employee__email", "employee__first_name", "employee__last_name")
    date_hierarchy = "start_date"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
