import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role
from leave import services
from leave.models import Allowance, LeaveType

# Fictional accounts only. Usernames follow the company's employee-code style.
DEMO_USERS = [
    ("DM001", "Meera", "Kapoor", "Administration", Role.ADMIN),
    ("DM002", "Arjun", "Sen", "Engineering", Role.EMPLOYEE),
    ("DM003", "Priya", "Nair", "Design", Role.EMPLOYEE),
]
DEMO_EMAIL_DOMAIN = "example.com"  # Reserved for documentation; never delivers mail.
ALLOWANCES = {LeaveType.CASUAL: 12, LeaveType.SICK: 8}


def next_weekday(day: date, weeks_ahead: int, weekday: int = 0) -> date:
    """The given weekday (Monday = 0) `weeks_ahead` weeks after `day`'s week."""
    return day + timedelta(days=(weekday - day.weekday()) % 7 + 7 * weeks_ahead)


class Command(BaseCommand):
    help = (
        "Load fictional demo data: one administrator, two employees, allowances and a few leave "
        "requests. Passwords are generated and written only to --credentials-file (never "
        "printed). Refuses to run on a database that has non-demo users. Safe to re-run; "
        "each run sets new passwords."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--credentials-file",
            required=True,
            help="New file to write the demo sign-in details to. Keep it out of Git and Trello.",
        )

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        path = Path(options["credentials_file"]).expanduser()
        if path.exists():
            raise CommandError(f"{path} already exists; choose a new file so nothing is overwritten.")

        demo_usernames = [u[0] for u in DEMO_USERS]
        if User.objects.exclude(username__in=demo_usernames).exists():
            raise CommandError(
                "This database has users that are not demo accounts. Demo data is only loaded "
                "into an empty demo database."
            )

        today = date.today()
        credentials = []
        with transaction.atomic():
            users = {}
            for username, first, last, department, role in DEMO_USERS:
                password = f"Demo-{secrets.token_urlsafe(12)}"
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": first,
                        "last_name": last,
                        "email": f"{first}.{last}@{DEMO_EMAIL_DOMAIN}".lower(),
                    },
                )
                user.set_password(password)
                user.is_active = True
                user.save()
                profile = user.profile
                profile.role = role
                profile.department = department
                profile.employee_code = username
                profile.save()
                users[username] = user
                credentials.append((username, password, role.label))

                if role == Role.EMPLOYEE:
                    # Next year too, so requests a few weeks ahead work in December.
                    for year in (today.year, today.year + 1):
                        for leave_type, days in ALLOWANCES.items():
                            Allowance.objects.update_or_create(
                                employee=user, year=year, leave_type=leave_type, defaults={"days": days}
                            )

            admin = users["DM001"]
            if not users["DM002"].leave_requests.exists():
                self._request(users["DM002"], LeaveType.CASUAL, today, 2, 2, "Family visit")
                approved = self._request(users["DM002"], LeaveType.SICK, today, 4, 1, "Doctor's appointment")
                services.approve_request(approved.pk, admin, "Get well soon.")
            if not users["DM003"].leave_requests.exists():
                self._request(users["DM003"], LeaveType.CASUAL, today, 3, 3, "Short holiday")
                rejected = self._request(users["DM003"], LeaveType.CASUAL, today, 5, 1, "Personal errand")
                services.reject_request(rejected.pk, admin, "Team deadline that day; please pick another date.")

        self._write_credentials(path, credentials)
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded. Sign-in details written to {path}."))

    @staticmethod
    def _request(employee, leave_type, today, weeks_ahead, days, reason):
        start = next_weekday(today, weeks_ahead)
        return services.create_request(
            employee, leave_type, start, start + timedelta(days=days - 1), reason, today=today
        )

    @staticmethod
    def _write_credentials(path: Path, credentials) -> None:
        lines = ["Demo sign-in details (fictional accounts). Share privately; never post on Trello.", ""]
        lines += [f"{role}: username {username}  password {password}" for username, password, role in credentials]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
