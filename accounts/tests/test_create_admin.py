import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.management.commands import create_admin
from accounts.models import Role

from .helpers import make_password, make_user

User = get_user_model()

ADMIN_ENV_KEYS = ("ELM_ADMIN_USERNAME", "ELM_ADMIN_EMAIL", "ELM_ADMIN_PASSWORD")


class CreateAdminCommandTests(TestCase):
    def setUp(self):
        # Isolate from any ELM_ADMIN_* values loaded from the local .env file.
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ADMIN_ENV_KEYS:
            os.environ.pop(key, None)
        self.password = make_password()

    def run_command(self, *args, **env):
        os.environ.update(env)
        stdout, stderr = StringIO(), StringIO()
        call_command("create_admin", *args, stdout=stdout, stderr=stderr)
        return stdout.getvalue() + stderr.getvalue()

    def interactive(self, *passwords):
        stdin = mock.patch.object(create_admin.sys, "stdin", **{"isatty.return_value": True})
        getpass = mock.patch.object(create_admin, "getpass", side_effect=list(passwords))
        return stdin, getpass

    def test_creates_admin_from_env_password_no_input(self):
        output = self.run_command(
            "--username", "admin", "--email", "admin@example.com", "--no-input",
            ELM_ADMIN_PASSWORD=self.password,
        )

        user = User.objects.get(username="admin")
        self.assertIn('Administrator "admin" created.', output)
        self.assertEqual(user.profile.role, Role.ADMIN)
        self.assertEqual(user.email, "admin@example.com")
        self.assertTrue(user.is_active and user.is_staff and user.is_superuser)
        self.assertTrue(self.client.login(username="admin", password=self.password))

    def test_prompts_with_getpass_when_env_missing(self):
        stdin, getpass = self.interactive(self.password, self.password)
        with stdin, getpass as prompt:
            self.run_command(ELM_ADMIN_USERNAME="admin")

        self.assertEqual(prompt.call_count, 2)
        self.assertTrue(User.objects.get(username="admin").check_password(self.password))

    def test_mismatched_prompt_passwords_error(self):
        stdin, getpass = self.interactive(self.password, make_password())
        with stdin, getpass, self.assertRaisesMessage(CommandError, "Passwords do not match."):
            self.run_command("--username", "admin")

        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_no_input_without_password_raises_command_error(self):
        with self.assertRaisesMessage(CommandError, "ELM_ADMIN_PASSWORD"):
            self.run_command("--username", "admin", "--no-input")

        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_weak_password_rejected_by_validators(self):
        with self.assertRaisesMessage(CommandError, "This password is too common."):
            self.run_command(
                "--username", "admin", "--no-input", ELM_ADMIN_PASSWORD="password"
            )

        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_rerun_is_idempotent_and_keeps_password(self):
        self.run_command("--username", "admin", "--no-input", ELM_ADMIN_PASSWORD=self.password)

        output = self.run_command(
            "--username", "admin", "--no-input", ELM_ADMIN_PASSWORD=make_password()
        )

        self.assertIn('Administrator "admin" already exists; role and flags ensured.', output)
        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        self.assertTrue(User.objects.get(username="admin").check_password(self.password))

    def test_rerun_promotes_existing_employee_to_admin_and_reactivates(self):
        make_user("admin", self.password, is_active=False)

        self.run_command("--username", "admin", "--no-input")

        user = User.objects.get(username="admin")
        self.assertEqual(user.profile.role, Role.ADMIN)
        self.assertTrue(user.is_active and user.is_staff and user.is_superuser)
        self.assertTrue(user.check_password(self.password))

    def test_update_password_flag_changes_password(self):
        self.run_command("--username", "admin", "--no-input", ELM_ADMIN_PASSWORD=self.password)
        new_password = make_password()

        self.run_command(
            "--username", "admin", "--no-input", "--update-password",
            ELM_ADMIN_PASSWORD=new_password,
        )

        user = User.objects.get(username="admin")
        self.assertTrue(user.check_password(new_password))
        self.assertFalse(user.check_password(self.password))

    def test_output_never_contains_password(self):
        output = self.run_command(
            "--username", "admin", "--no-input", ELM_ADMIN_PASSWORD=self.password
        )
        output += self.run_command(
            "--username", "admin", "--no-input", "--update-password",
            ELM_ADMIN_PASSWORD=self.password,
        )

        self.assertNotIn(self.password, output)
