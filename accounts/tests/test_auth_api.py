from unittest import mock

from django.conf import settings
from django.contrib.auth.signals import user_logged_out
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import Role

from .helpers import make_password, make_user

INVALID_CREDENTIALS = {"detail": "Invalid username or password."}


class AuthApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = make_password()
        self.user = make_user(
            "emma", self.password, first_name="Emma", last_name="Stone", email="emma@example.com"
        )

    def login(self, username="emma", password=None):
        return self.client.post(
            reverse("auth-login"),
            {"username": username, "password": self.password if password is None else password},
            format="json",
        )

    def test_login_with_valid_credentials_returns_user_and_sets_session(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "emma")
        self.assertEqual(response.json()["user"]["role"], Role.EMPLOYEE)
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]["httponly"])

    def test_login_with_wrong_password_returns_generic_400(self):
        response = self.login(password="wrong-password")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_CREDENTIALS)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)

    def test_login_with_unknown_username_returns_same_generic_400(self):
        response = self.login(username="nobody")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_CREDENTIALS)

    def test_login_inactive_user_returns_same_generic_400(self):
        self.user.is_active = False
        self.user.save()

        response = self.login()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_CREDENTIALS)

    def test_login_missing_fields_returns_field_errors(self):
        response = self.client.post(reverse("auth-login"), {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"username": ["This field is required."], "password": ["This field is required."]},
        )

    def test_login_response_never_contains_password_or_staff_flags(self):
        response = self.login()
        body = response.json()["user"]

        self.assertEqual(
            set(body), {"id", "username", "email", "first_name", "last_name", "role"}
        )
        self.assertNotIn(self.password, response.content.decode())

    def test_me_returns_current_user_when_authenticated(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.user.pk,
                "username": "emma",
                "email": "emma@example.com",
                "first_name": "Emma",
                "last_name": "Stone",
                "role": Role.EMPLOYEE,
            },
        )

    def test_me_requires_authentication_returns_401(self):
        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Session")

    def test_logout_ends_access_to_protected_endpoints(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)

    def test_logout_flushes_server_side_session(self):
        self.login()
        old_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value

        self.client.post(reverse("auth-logout"))

        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        replay = APIClient()
        replay.cookies[settings.SESSION_COOKIE_NAME] = old_key
        self.assertEqual(replay.get(reverse("auth-me")).status_code, 401)

    def test_logout_when_anonymous_returns_204(self):
        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 204)

    def test_login_without_remember_me_uses_a_browser_session_cookie(self):
        response = self.login()

        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie["max-age"], "")
        self.assertEqual(cookie["expires"], "")
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_login_with_remember_me_sets_a_persistent_cookie(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": "emma", "password": self.password, "remember_me": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie["max-age"], settings.REMEMBER_ME_SESSION_AGE)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_login_is_throttled_after_rate_exceeded(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "2/minute"}):
            self.login(password="wrong-1")
            self.login(password="wrong-2")
            response = self.login()

        self.assertEqual(response.status_code, 429)

    def test_login_throttle_ignores_rotating_x_forwarded_for(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "2/minute"}):
            statuses = [
                self.client.post(
                    reverse("auth-login"),
                    {"username": "emma", "password": f"wrong-{n}"},
                    format="json",
                    HTTP_X_FORWARDED_FOR=f"203.0.113.{n}",
                ).status_code
                for n in range(3)
            ]

        self.assertEqual(statuses, [400, 400, 429])

    def test_logout_sends_user_logged_out_with_real_user(self):
        received = []

        def receiver(sender, request, user, **kwargs):
            received.append(user)

        user_logged_out.connect(receiver)
        self.addCleanup(user_logged_out.disconnect, receiver)
        self.client.force_login(self.user)

        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(received, [self.user])

    def test_session_cycled_on_login(self):
        session = self.client.session
        session["marker"] = "pre-login"
        session.save()
        pre_login_key = session.session_key

        self.login()

        new_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertNotEqual(new_key, pre_login_key)
        self.assertFalse(Session.objects.filter(session_key=pre_login_key).exists())
