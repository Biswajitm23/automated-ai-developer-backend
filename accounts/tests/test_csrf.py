from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .helpers import make_password, make_user

FRONTEND_ORIGIN = "http://localhost:3000"


class CsrfTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.password = make_password()
        self.user = make_user("emma", self.password)

    def csrf_token(self) -> str:
        return self.client.get(reverse("auth-csrf")).json()["csrfToken"]

    def login(self, **extra):
        return self.client.post(
            reverse("auth-login"),
            {"username": "emma", "password": self.password},
            format="json",
            **extra,
        )

    def test_csrf_endpoint_returns_token_and_sets_cookie(self):
        response = self.client.get(reverse("auth-csrf"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["csrfToken"])
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)

    def test_login_without_csrf_token_is_rejected_403(self):
        self.client.get(reverse("auth-csrf"))

        response = self.login()

        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["detail"].startswith("CSRF Failed"))
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)

    def test_login_with_csrf_token_succeeds(self):
        response = self.login(HTTP_X_CSRFTOKEN=self.csrf_token())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

    def test_logout_without_csrf_token_is_rejected_and_session_kept(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

    def test_cross_origin_post_from_trusted_frontend_origin_passes(self):
        token = self.csrf_token()

        response = self.login(HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN=FRONTEND_ORIGIN)

        self.assertEqual(response.status_code, 200)

    def test_post_from_untrusted_origin_is_rejected(self):
        token = self.csrf_token()

        response = self.login(HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://evil.example")

        self.assertEqual(response.status_code, 403)

    def test_cors_allows_credentials_for_frontend_origin(self):
        response = self.client.get(reverse("auth-csrf"), HTTP_ORIGIN=FRONTEND_ORIGIN)

        self.assertEqual(response["Access-Control-Allow-Origin"], FRONTEND_ORIGIN)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
