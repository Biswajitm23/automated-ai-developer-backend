from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Employee"
    ADMIN = "ADMIN", "Administrator"


class Profile(models.Model):
    """Application role for a user. The role, not is_staff/is_superuser, drives API permissions."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        self.sync_user_flags()

    def sync_user_flags(self) -> None:
        """Make Django admin-site access follow the role.

        ADMIN grants is_staff and is_superuser (full Django admin, as create_admin does);
        EMPLOYEE revokes both. The flags are always written, never diffed against the cached
        user, so a stale instance cannot leave them set. A queryset update is used so the
        user's own save() and its signals are not re-triggered.
        """
        is_admin = self.role == Role.ADMIN
        flags = {"is_staff": is_admin, "is_superuser": is_admin}
        user = self.user
        type(user).objects.filter(pk=user.pk).update(**flags)
        for name, value in flags.items():
            setattr(user, name, value)

    def __str__(self) -> str:
        return f"{self.user.get_username()} ({self.role})"
