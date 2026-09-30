import os
import stat
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave.models import LeaveRequest, RequestStatus

User = get_user_model()


class SeedDemoTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_seed(self, name="creds.txt"):
        path = Path(self.tmp.name) / name
        out = StringIO()
        call_command("seed_demo", credentials_file=str(path), stdout=out)
        return path, out.getvalue()

    def test_creates_one_admin_two_employees_and_requests(self):
        path, _ = self.run_seed()
        roles = {u.username: u.profile.role for u in User.objects.all()}
        self.assertEqual(roles, {"DM001": Role.ADMIN, "DM002": Role.EMPLOYEE, "DM003": Role.EMPLOYEE})
        statuses = sorted(LeaveRequest.objects.values_list("status", flat=True))
        self.assertEqual(
            statuses,
            sorted([RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.PENDING, RequestStatus.REJECTED]),
        )
        self.assertTrue(all(u.email.endswith("@example.com") for u in User.objects.all()))

    def test_passwords_go_only_to_the_private_file(self):
        path, output = self.run_seed()
        text = path.read_text()
        for username in ("DM001", "DM002", "DM003"):
            line = next(line for line in text.splitlines() if f"username {username}" in line)
            password = line.split("password ")[1].strip()
            self.assertNotIn(password, output)
            self.assertTrue(User.objects.get(username=username).check_password(password))
        if os.name == "posix" and not str(path).startswith("/mnt/"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_rerun_resets_passwords_without_duplicating_data(self):
        self.run_seed("first.txt")
        self.run_seed("second.txt")
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(LeaveRequest.objects.count(), 4)

    def test_refuses_existing_credentials_file(self):
        path = Path(self.tmp.name) / "exists.txt"
        path.write_text("keep me")
        with self.assertRaises(CommandError):
            call_command("seed_demo", credentials_file=str(path), stdout=StringIO())
        self.assertEqual(path.read_text(), "keep me")

    def test_refuses_database_with_real_users(self):
        make_user("BP080", make_password())
        with self.assertRaises(CommandError):
            self.run_seed()
        self.assertFalse(User.objects.filter(username__startswith="DM").exists())
