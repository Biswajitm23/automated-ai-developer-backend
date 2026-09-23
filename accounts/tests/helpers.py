import secrets

from django.contrib.auth import get_user_model

from accounts.models import Role

User = get_user_model()


def make_password() -> str:
    """Generate a throwaway test password (not a real credential)."""
    return f"Tp-{secrets.token_urlsafe(16)}"


def make_user(username: str, password: str, role: str = Role.EMPLOYEE, **extra):
    user = User.objects.create_user(username=username, password=password, **extra)
    user.profile.role = role
    user.profile.save()
    return user
