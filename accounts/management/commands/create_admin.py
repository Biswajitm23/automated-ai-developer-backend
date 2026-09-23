import os
import sys
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Profile, Role


class Command(BaseCommand):
    help = (
        "Create the initial administrator, or make an existing user an active administrator. "
        "The password is read from ELM_ADMIN_PASSWORD or prompted for; it is never printed. "
        "Safe to re-run."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", help="Defaults to ELM_ADMIN_USERNAME.")
        parser.add_argument("--email", help="Defaults to ELM_ADMIN_EMAIL.")
        parser.add_argument(
            "--no-input",
            action="store_true",
            dest="no_input",
            help="Never prompt; the password must come from ELM_ADMIN_PASSWORD.",
        )
        parser.add_argument(
            "--update-password",
            action="store_true",
            help="Also set a new password when the user already exists.",
        )

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        username = (options["username"] or os.environ.get("ELM_ADMIN_USERNAME", "")).strip()
        email = (options["email"] or os.environ.get("ELM_ADMIN_EMAIL", "")).strip()
        if not username:
            raise CommandError("A username is required: pass --username or set ELM_ADMIN_USERNAME.")

        with transaction.atomic():
            user = User.objects.select_for_update().filter(username=username).first()
            exists = user is not None
            password = None
            if not exists or options["update_password"]:
                candidate = user or User(username=username, email=email)
                password = self._get_password(no_input=options["no_input"])
                self._validate(password, candidate)

            if exists:
                if email:
                    user.email = email
                if password is not None:
                    user.set_password(password)
            else:
                user = User.objects.create_user(username=username, email=email, password=password)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.save()
            Profile.objects.update_or_create(user=user, defaults={"role": Role.ADMIN})

        if exists:
            message = f'Administrator "{username}" already exists; role and flags ensured.'
            if password is not None:
                message += " Password updated."
        else:
            message = f'Administrator "{username}" created.'
        self.stdout.write(self.style.SUCCESS(message))

    def _get_password(self, *, no_input: bool) -> str:
        password = os.environ.get("ELM_ADMIN_PASSWORD", "")
        if password:
            return password
        if no_input or not sys.stdin.isatty():
            raise CommandError(
                "No password available: set ELM_ADMIN_PASSWORD or run interactively "
                "without --no-input."
            )
        password = getpass("Password: ")
        if password != getpass("Password (again): "):
            raise CommandError("Passwords do not match.")
        if not password:
            raise CommandError("The password cannot be empty.")
        return password

    @staticmethod
    def _validate(password: str, user) -> None:
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError("Password rejected: " + " ".join(error.messages)) from None
