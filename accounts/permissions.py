from rest_framework.permissions import BasePermission

from .roles import is_admin


class IsAdminRole(BasePermission):
    """Allow only active users whose profile role is ADMIN."""

    message = "Administrator role required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and is_admin(user))


class IsEmployeeRole(BasePermission):
    """Allow only active users whose profile role is EMPLOYEE (admins are not leave-takers)."""

    message = "Employee role required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and not is_admin(user))
