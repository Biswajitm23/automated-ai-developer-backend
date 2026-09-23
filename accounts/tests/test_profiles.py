import importlib

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Profile, Role
from accounts.roles import get_role, is_admin

from .helpers import make_password

User = get_user_model()


class ProfileTests(TestCase):
    def test_profile_auto_created_for_new_user_as_employee(self):
        user = User.objects.create_user(username="emma", password=make_password())

        self.assertEqual(user.profile.role, Role.EMPLOYEE)
        self.assertEqual(str(user.profile), "emma (EMPLOYEE)")
        self.assertFalse(is_admin(user))

    def test_superuser_profile_gets_admin_role(self):
        user = User.objects.create_superuser(username="root", password=make_password())

        self.assertEqual(user.profile.role, Role.ADMIN)
        self.assertTrue(is_admin(user))

    def test_get_role_defaults_to_employee_when_profile_missing(self):
        user = User.objects.create_superuser(username="orphan", password=make_password())
        Profile.objects.filter(user=user).delete()
        user = User.objects.get(pk=user.pk)

        self.assertEqual(get_role(user), Role.EMPLOYEE)
        self.assertFalse(is_admin(user))

    def test_backfill_migration_creates_missing_profiles(self):
        employee = User.objects.create_user(username="old_employee", password=make_password())
        admin = User.objects.create_superuser(username="old_admin", password=make_password())
        Profile.objects.all().delete()

        migration = importlib.import_module("accounts.migrations.0002_backfill_profiles")
        migration.backfill_profiles(apps, None)

        self.assertEqual(Profile.objects.get(user=employee).role, Role.EMPLOYEE)
        self.assertEqual(Profile.objects.get(user=admin).role, Role.ADMIN)
        # Running it again must not duplicate or change anything.
        migration.backfill_profiles(apps, None)
        self.assertEqual(Profile.objects.count(), 2)

    def test_admin_role_grants_staff_and_superuser_and_employee_role_revokes_both(self):
        user = User.objects.create_user(username="sam", password=make_password())

        user.profile.role = Role.ADMIN
        user.profile.save()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        user.is_superuser = True
        user.save()
        user.profile.role = Role.EMPLOYEE
        user.profile.save()
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_demotion_with_stale_user_instance_still_revokes_flags(self):
        user = User.objects.create_user(username="stale", password=make_password())
        profile = Profile.objects.select_related("user").get(user=user)
        # Flags change in the database behind the cached instance's back.
        User.objects.filter(pk=user.pk).update(is_staff=True, is_superuser=True)

        profile.role = Role.EMPLOYEE
        profile.save()

        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
