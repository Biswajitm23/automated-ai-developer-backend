from django.contrib import admin

from .models import Allowance


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
