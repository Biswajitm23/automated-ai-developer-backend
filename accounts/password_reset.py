"""Forgot-password flow: email a one-time code, then let the user choose a new password.

Every public entry point gives the same answer whether or not the email belongs to an
account, so the flow cannot be used to discover which addresses are registered.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import PasswordResetCode

logger = logging.getLogger(__name__)

User = get_user_model()

CODE_LENGTH = 6
_HMAC_SALT = "accounts.password_reset.code"


def _hash_code(user, code: str) -> str:
    return salted_hmac(_HMAC_SALT, f"{user.pk}:{code}", algorithm="sha256").hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def _eligible_users(email: str):
    """Active users with a usable password whose email matches (case-insensitive)."""
    users = User.objects.filter(email__iexact=email.strip(), is_active=True).exclude(email="")
    return [user for user in users if user.has_usable_password()]


def _open_codes(email: str):
    return PasswordResetCode.objects.filter(
        user__email__iexact=email.strip(),
        user__is_active=True,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
        failed_attempts__lt=settings.PASSWORD_RESET_MAX_ATTEMPTS,
    ).select_related("user")


def request_code(email: str) -> None:
    """Email a fresh code to each eligible account with this address; silently no-op otherwise.

    A newer code replaces any earlier one. Within the resend cooldown no new code is sent,
    which stops the endpoint from being used to flood someone's inbox.
    """
    now = timezone.now()
    cooldown = timedelta(seconds=settings.PASSWORD_RESET_RESEND_COOLDOWN)
    ttl_minutes = settings.PASSWORD_RESET_CODE_TTL // 60

    for user in _eligible_users(email):
        with transaction.atomic():
            # Lock the user's row so two concurrent requests cannot both pass the cooldown check.
            User.objects.select_for_update().filter(pk=user.pk).first()
            if PasswordResetCode.objects.filter(user=user, created_at__gt=now - cooldown).exists():
                continue
            PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
            code = _new_code()
            PasswordResetCode.objects.create(
                user=user,
                code_hash=_hash_code(user, code),
                expires_at=now + timedelta(seconds=settings.PASSWORD_RESET_CODE_TTL),
            )

        try:
            send_mail(
                subject="Your password reset code",
                message=(
                    f"Hello {user.get_short_name() or user.get_username()},\n\n"
                    f"Your password reset code is: {code}\n\n"
                    f"It expires in {ttl_minutes} minutes. If you did not ask to reset your "
                    "password, you can ignore this email; your password will not change.\n\n"
                    "Employee Leave Management"
                ),
                from_email=None,
                recipient_list=[user.email],
            )
        except Exception:
            # Keep the response identical for every address; the failure is logged for admins.
            logger.exception("Could not send the password reset email to user id %s", user.pk)


def find_valid_code(email: str, code: str, *, lock: bool = False) -> PasswordResetCode | None:
    """Return the open code matching (email, code), or None.

    A wrong guess counts against every open code for that address, so each code allows at
    most PASSWORD_RESET_MAX_ATTEMPTS guesses. With lock=True the caller must be inside a
    transaction; the matched row stays locked until it commits.
    """
    codes = _open_codes(email)
    if lock:
        codes = codes.select_for_update(of=("self",))
    candidates = list(codes)
    for candidate in candidates:
        if constant_time_compare(candidate.code_hash, _hash_code(candidate.user, code)):
            return candidate
    if candidates:
        PasswordResetCode.objects.filter(pk__in=[c.pk for c in candidates]).update(
            failed_attempts=F("failed_attempts") + 1
        )
    return None


def notify_password_changed(user) -> None:
    try:
        send_mail(
            subject="Your password was changed",
            message=(
                f"Hello {user.get_short_name() or user.get_username()},\n\n"
                "The password for your Employee Leave Management account was just changed. "
                "If this was not you, contact your administrator straight away.\n\n"
                "Employee Leave Management"
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception:
        logger.exception("Could not send the password changed email to user id %s", user.pk)
