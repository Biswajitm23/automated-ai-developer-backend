from django.core.exceptions import ObjectDoesNotExist

from .models import Role


def get_role(user) -> Role:
    """Return the user's role. Fails closed to EMPLOYEE if the user has no profile."""
    try:
        return Role(user.profile.role)
    except (AttributeError, ObjectDoesNotExist, ValueError):
        return Role.EMPLOYEE


def is_admin(user) -> bool:
    return get_role(user) == Role.ADMIN
