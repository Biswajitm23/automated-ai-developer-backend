from datetime import date
from unittest import mock

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance
from leave.usage import Usage


class LeaveTypeTests(APITestCase):
    def test_any_signed_in_user_gets_the_two_leave_types(self):
        self.client.force_authenticate(make_user("emma", make_password()))

        response = self.client.get(reverse("leave-types"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [{"code": "CASUAL", "name": "Casual Leave"}, {"code": "SICK", "name": "Sick Leave"}],
        )

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(reverse("leave-types")).status_code, 401)


class AllowanceTests(APITestCase):
    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        self.employee = make_user("emma", make_password(), email="emma@example.com")
        self.client.force_authenticate(self.admin)

    def put(self, days, year=2026, leave_type="CASUAL", employee=None):
        employee = employee or self.employee
        return self.client.put(
            reverse("admin-employee-allowance", args=[employee.pk, year, leave_type]),
            {"days": days},
            format="json",
        )

    def get(self, year="2026", employee=None):
        employee = employee or self.employee
        params = {} if year is None else {"year": year}
        return self.client.get(reverse("admin-employee-allowances", args=[employee.pk]), params)

    def test_unset_year_lists_one_zero_row_per_leave_type(self):
        body = self.get().json()

        self.assertEqual(body["employee_id"], self.employee.pk)
        self.assertEqual(body["year"], 2026)
        self.assertEqual([row["leave_type"] for row in body["allowances"]], ["CASUAL", "SICK"])
        for row in body["allowances"]:
            self.assertEqual(
                {k: row[k] for k in ("days", "approved", "pending", "available", "minimum_allowed", "updated_at")},
                {"days": 0, "approved": 0, "pending": 0, "available": 0, "minimum_allowed": 0, "updated_at": None},
            )

    def test_put_creates_then_updates_one_row(self):
        created = self.put(12)
        updated = self.put(15)

        self.assertEqual(created.status_code, 200)
        self.assertEqual(updated.json()["days"], 15)
        self.assertEqual(updated.json()["available"], 15)
        self.assertIsNotNone(updated.json()["updated_at"])
        self.assertEqual(Allowance.objects.get().days, 15)
        sick = self.get().json()["allowances"][1]
        self.assertEqual(sick["days"], 0)

    def test_allowances_are_per_year(self):
        self.put(12, year=2026)
        self.put(10, year=2027)

        self.assertEqual(self.get("2026").json()["allowances"][0]["days"], 12)
        self.assertEqual(self.get("2027").json()["allowances"][0]["days"], 10)

    def test_negative_and_invalid_days_are_rejected(self):
        cases = [
            (-1, "Ensure this value is greater than or equal to 0."),
            (367, "Ensure this value is less than or equal to 366."),
            (1.5, "A valid integer is required."),
            ("12", "A valid integer is required."),
            (True, "A valid integer is required."),
            (None, "This field may not be null."),
        ]
        for days, message in cases:
            with self.subTest(days=days):
                response = self.put(days)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"days": [message]})
        self.assertFalse(Allowance.objects.exists())

    def test_cannot_reduce_below_approved_plus_pending(self):
        self.put(10)
        usage = {"CASUAL": Usage(approved=4, pending=3), "SICK": Usage()}
        with mock.patch("leave.views.usage_for", return_value=usage):
            too_low = self.put(6)
            at_minimum = self.put(7)

        self.assertEqual(too_low.status_code, 400)
        self.assertEqual(
            too_low.json(), {"days": ["Allowance cannot be less than approved plus pending leave (7 days)."]}
        )
        self.assertEqual(at_minimum.status_code, 200)
        self.assertEqual(
            {k: at_minimum.json()[k] for k in ("days", "approved", "pending", "available", "minimum_allowed")},
            {"days": 7, "approved": 4, "pending": 3, "available": 0, "minimum_allowed": 7},
        )

    def test_minimum_message_uses_singular_for_one_day(self):
        usage = {"CASUAL": Usage(approved=1), "SICK": Usage()}
        with mock.patch("leave.views.usage_for", return_value=usage):
            response = self.put(0)

        self.assertEqual(
            response.json(), {"days": ["Allowance cannot be less than approved plus pending leave (1 day)."]}
        )

    def test_year_query_validation(self):
        self.assertEqual(self.get(None).json(), {"year": ["This field is required."]})
        for year in ["26", "1999", "2101", "abcd"]:
            with self.subTest(year=year):
                self.assertEqual(self.get(year).json(), {"year": ["Enter a valid year."]})

    def test_unknown_leave_type_year_or_employee_is_404(self):
        self.assertEqual(self.put(5, leave_type="MATERNITY").status_code, 404)
        self.assertEqual(self.put(5, year=1999).status_code, 404)
        self.assertEqual(self.put(5, employee=self.admin).status_code, 404)
        self.assertEqual(self.get(employee=self.admin).status_code, 404)

    def test_deactivated_employee_keeps_allowances(self):
        self.put(12)
        self.client.post(reverse("admin-employee-deactivate", args=[self.employee.pk]), {}, format="json")

        self.assertEqual(self.get().json()["allowances"][0]["days"], 12)

    def test_employee_cannot_read_or_change_allowances(self):
        self.client.force_authenticate(self.employee)

        self.assertEqual(self.get().status_code, 403)
        self.assertEqual(self.put(99).status_code, 403)
        self.assertFalse(Allowance.objects.exists())


class AllowanceMinimumWithRealRequestsTests(APITestCase):
    def test_reduction_below_approved_plus_pending_is_refused(self):
        admin = make_user("boss", make_password(), role=Role.ADMIN)
        employee = make_user("emma", make_password())
        Allowance.objects.create(employee=employee, year=2026, leave_type="CASUAL", days=10)
        today = date(2026, 9, 23)
        approved = services.create_request(employee, "CASUAL", date(2026, 10, 5), date(2026, 10, 6), "A", today=today)
        services.approve_request(approved.pk, admin)
        services.create_request(employee, "CASUAL", date(2026, 10, 12), date(2026, 10, 14), "B", today=today)
        self.client.force_authenticate(admin)
        url = reverse("admin-employee-allowance", args=[employee.pk, 2026, "CASUAL"])

        refused = self.client.put(url, {"days": 4}, format="json")
        accepted = self.client.put(url, {"days": 5}, format="json")

        self.assertEqual(
            refused.json(), {"days": ["Allowance cannot be less than approved plus pending leave (5 days)."]}
        )
        self.assertEqual(
            {k: accepted.json()[k] for k in ("days", "approved", "pending", "available", "minimum_allowed")},
            {"days": 5, "approved": 2, "pending": 3, "available": 0, "minimum_allowed": 5},
        )
