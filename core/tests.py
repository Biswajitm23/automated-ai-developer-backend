from unittest import mock

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_reports_ok_when_database_is_reachable(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_reports_503_when_database_is_unreachable(self):
        with mock.patch("core.views.connection.cursor", side_effect=OperationalError("down")):
            with self.assertLogs("core.views", level="ERROR"):
                response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "database": "error"})

    def test_allows_frontend_origin_via_cors(self):
        response = self.client.get(reverse("health"), HTTP_ORIGIN="http://localhost:3000")

        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:3000")

    def test_health_is_public_without_session(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WWW-Authenticate", response)
