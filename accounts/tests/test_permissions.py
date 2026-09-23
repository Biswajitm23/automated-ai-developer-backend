from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIRequestFactory, APITestCase

from accounts.models import Role
from accounts.permissions import IsAdminRole

from .helpers import make_password, make_user


class AdminPermissionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user("alice", make_password(), role=Role.ADMIN)
        self.employee = make_user("emma", make_password())

    def test_admin_ping_allows_admin_role(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin-ping"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "role": "ADMIN"})

    def test_admin_ping_forbids_employee_returns_403(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse("admin-ping"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Administrator role required."})

    def test_admin_ping_anonymous_returns_401(self):
        response = self.client.get(reverse("admin-ping"))

        self.assertEqual(response.status_code, 401)

    def test_superuser_flag_without_admin_role_is_forbidden(self):
        self.employee.is_superuser = True
        self.employee.is_staff = True
        self.employee.save()
        self.client.force_login(self.employee)

        response = self.client.get(reverse("admin-ping"))

        self.assertEqual(response.status_code, 403)

    def test_inactive_user_with_live_session_loses_access(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

        self.employee.is_active = False
        self.employee.save()

        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)
        self.assertEqual(self.client.get(reverse("admin-ping")).status_code, 401)

    def test_inactive_admin_with_live_session_cannot_reach_admin_api(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin-ping")).status_code, 200)

        self.admin.is_active = False
        self.admin.save()

        self.assertEqual(self.client.get(reverse("admin-ping")).status_code, 401)

    def test_password_change_invalidates_existing_session(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

        self.employee.set_password(make_password())
        self.employee.save()

        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)

    def test_is_admin_role_permission_unit(self):
        permission = IsAdminRole()
        request = APIRequestFactory().get("/")
        inactive_admin = make_user("old_admin", make_password(), role=Role.ADMIN, is_active=False)

        cases = [
            (AnonymousUser(), False),
            (self.employee, False),
            (self.admin, True),
            (inactive_admin, False),
        ]
        for user, expected in cases:
            with self.subTest(user=str(user)):
                request.user = user
                self.assertIs(permission.has_permission(request, None), expected)
