from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role

from .helpers import make_password, make_user

User = get_user_model()


class AdminSiteTests(TestCase):
    """Account creation happens in Django's admin site; roles are set on the change page."""

    def setUp(self):
        cache.clear()
        self.superuser = User.objects.create_superuser(username="root", password=make_password())
        self.client.force_login(self.superuser)

    def change_form_data(self, user, role):
        joined = timezone.localtime(user.date_joined)
        return {
            "username": user.username,
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "date_joined_0": joined.strftime("%Y-%m-%d"),
            "date_joined_1": joined.strftime("%H:%M:%S"),
            "last_login_0": "",
            "last_login_1": "",
            "profile-TOTAL_FORMS": "1",
            "profile-INITIAL_FORMS": "1",
            "profile-MIN_NUM_FORMS": "0",
            "profile-MAX_NUM_FORMS": "1",
            "profile-0-id": str(user.profile.pk),
            "profile-0-user": str(user.pk),
            "profile-0-role": role,
            "_save": "Save",
        }

    def test_add_user_page_has_no_profile_inline(self):
        response = self.client.get(reverse("admin:auth_user_add"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["inline_admin_formsets"], [])

    def test_admin_can_add_user_then_set_admin_role_on_change_page(self):
        password = make_password()
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "newbie",
                "password1": password,
                "password2": password,
                "usable_password": "true",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        user = User.objects.get(username="newbie")
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.assertEqual(user.profile.role, Role.EMPLOYEE)

        change_url = reverse("admin:auth_user_change", args=[user.pk])
        response = self.client.post(change_url, self.change_form_data(user, Role.ADMIN))

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.profile.role, Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        # The new administrator can manage accounts in the Django admin site.
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_user_add")).status_code, 200)

    def test_superuser_checkbox_on_employee_is_reset_by_role(self):
        employee = make_user("emma", make_password())
        data = self.change_form_data(employee, Role.EMPLOYEE)
        data.update(is_staff="on", is_superuser="on")

        response = self.client.post(
            reverse("admin:auth_user_change", args=[employee.pk]), data
        )

        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertFalse(employee.is_staff)
        self.assertFalse(employee.is_superuser)

    def test_employee_is_blocked_from_django_admin_site(self):
        employee = make_user("emma", make_password())
        self.client.force_login(employee)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("admin:login")))
