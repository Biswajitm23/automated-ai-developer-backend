import uuid
from datetime import date
from unittest import mock

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance, LeaveRequest, RequestStatus

TODAY = date(2026, 9, 23)  # Wednesday


@mock.patch("leave.rules.today_in_app_zone", return_value=TODAY)
@mock.patch("leave.employee_views.today_in_app_zone", return_value=TODAY)
class EmployeeLeaveApiTests(APITestCase):
    def setUp(self):
        self.employee = make_user("emma", make_password(), first_name="Emma", last_name="Stone", email="emma@example.com")
        self.employee.profile.department = "Finance"
        self.employee.profile.save()
        self.other = make_user("liam", make_password())
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=5)
        Allowance.objects.create(employee=self.other, year=2026, leave_type="CASUAL", days=5)
        self.client.force_authenticate(self.employee)

    def submit(self, start="2026-10-05", end="2026-10-07", leave_type="CASUAL", reason="Family event", **extra):
        payload = {
            "leave_type": leave_type,
            "start_date": start,
            "end_date": end,
            "reason": reason,
            "client_request_id": str(uuid.uuid4()),
        }
        payload.update(extra)
        return self.client.post(reverse("leave-requests"), payload, format="json")

    def balances(self, year=None):
        params = {"year": year} if year else {}
        return {b["leave_type"]: b for b in self.client.get(reverse("my-balances"), params).json()["balances"]}

    # --- Submitting ---

    def test_valid_request_is_created_pending_and_reserves_balance(self, *_):
        response = self.submit()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["working_days"], 3)
        self.assertEqual(
            body["employee"],
            {"id": self.employee.pk, "full_name": "Emma Stone", "email": "emma@example.com", "department": "Finance", "is_active": True},
        )
        self.assertIsNone(body["reviewed_by"])
        self.assertEqual(body["review_remarks"], "")
        casual = self.balances()["CASUAL"]
        self.assertEqual((casual["allowance"], casual["pending"], casual["available"]), (5, 3, 2))

    def test_employee_field_is_ignored(self, *_):
        response = self.submit(employee=self.other.pk)

        self.assertEqual(response.json()["employee"]["id"], self.employee.pk)
        self.assertFalse(LeaveRequest.objects.filter(employee=self.other).exists())

    def test_repeated_submission_returns_the_original_request(self, *_):
        client_id = str(uuid.uuid4())
        first = self.submit(client_request_id=client_id)
        again = self.submit(client_request_id=client_id)

        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(LeaveRequest.objects.count(), 1)
        self.assertEqual(self.balances()["CASUAL"]["pending"], 3)

    def test_validation_errors_do_not_change_the_balance(self, *_):
        cases = [
            ({"leave_type": "MATERNITY"}, {"leave_type": ['"MATERNITY" is not a valid choice.']}),
            ({"start": "2026-09-22"}, {"start_date": ["Start date cannot be in the past."]}),
            ({"start": "2026-10-07", "end": "2026-10-05"}, {"end_date": ["End date must be on or after the start date."]}),
            ({"start": "2026-12-31", "end": "2027-01-01"}, {"non_field_errors": ["Leave cannot span two calendar years. Submit a separate request for each year."]}),
            ({"start": "2026-10-03", "end": "2026-10-04"}, {"non_field_errors": ["The selected dates contain no working days (Monday to Friday)."]}),
            ({"start": "2026-10-05", "end": "2026-10-12"}, {"non_field_errors": ["Not enough Casual Leave: 6 working days requested, 5 available."]}),
            ({"reason": "   "}, {"reason": ["This field may not be blank."]}),
            ({"reason": "x" * 501}, {"reason": ["Ensure this field has no more than 500 characters."]}),
            ({"start": "05-10-2026"}, None),
        ]
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                response = self.submit(**overrides)
                self.assertEqual(response.status_code, 400)
                if expected is not None:
                    self.assertEqual(response.json(), expected)
        self.assertFalse(LeaveRequest.objects.exists())
        self.assertEqual(self.balances()["CASUAL"]["available"], 5)

    def test_missing_client_request_id_is_rejected(self, *_):
        response = self.client.post(
            reverse("leave-requests"),
            {"leave_type": "CASUAL", "start_date": "2026-10-05", "end_date": "2026-10-05", "reason": "x"},
            format="json",
        )
        self.assertEqual(response.json(), {"client_request_id": ["This field is required."]})

    def test_overlap_message_names_the_existing_request(self, *_):
        first = self.submit().json()

        response = self.submit(start="2026-10-07", end="2026-10-08")

        self.assertEqual(
            response.json(),
            {"non_field_errors": [f"These dates overlap your pending or approved request #{first['id']} (5 Oct – 7 Oct 2026)."]},
        )

    # --- Access ---

    def test_admin_and_anonymous_cannot_use_employee_endpoints(self, *_):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.client.get(reverse("my-balances")).json(), {"detail": "Employee role required."})
        self.client.force_authenticate(None)
        self.assertEqual(self.submit().status_code, 401)

    def test_detail_only_for_own_requests(self, *_):
        own = self.submit().json()
        theirs = services.create_request(self.other, "CASUAL", date(2026, 10, 5), date(2026, 10, 5), "x", today=TODAY)

        self.assertEqual(self.client.get(reverse("leave-request", args=[own["id"]])).json()["id"], own["id"])
        response = self.client.get(reverse("leave-request", args=[theirs.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not found."})

    # --- Preview ---

    def preview(self, **params):
        base = {"leave_type": "CASUAL", "start_date": "2026-10-05", "end_date": "2026-10-07"}
        base.update(params)
        return self.client.get(reverse("leave-request-preview"), base).json()

    def test_preview_valid(self, *_):
        body = self.preview()
        self.assertEqual(body["valid"], True)
        self.assertEqual(body["working_days"], 3)
        self.assertEqual(body["balance"]["available"], 5)
        self.assertFalse(LeaveRequest.objects.exists())

    def test_preview_invalid_uses_the_400_error_shape(self, *_):
        self.assertEqual(
            self.preview(end_date="2026-10-12"),
            {"valid": False, "working_days": 6, "errors": {"non_field_errors": ["Not enough Casual Leave: 6 working days requested, 5 available."]}},
        )
        self.assertEqual(
            self.preview(start_date="bad"),
            {"valid": False, "working_days": 0, "errors": {"start_date": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]}},
        )

    # --- Balances ---

    def test_balances_default_to_current_year_and_list_every_type(self, *_):
        body = self.client.get(reverse("my-balances")).json()

        self.assertEqual(body["year"], 2026)
        self.assertEqual(
            body["balances"],
            [
                {"leave_type": "CASUAL", "year": 2026, "allowance": 5, "approved": 0, "pending": 0, "available": 5},
                {"leave_type": "SICK", "year": 2026, "allowance": 0, "approved": 0, "pending": 0, "available": 0},
            ],
        )
        self.assertEqual(self.client.get(reverse("my-balances"), {"year": "20"}).json(), {"year": ["Enter a valid year."]})

    def test_balances_follow_status_changes(self, *_):
        created = self.submit().json()
        services.approve_request(created["id"], self.admin)

        casual = self.balances()["CASUAL"]
        self.assertEqual((casual["approved"], casual["pending"], casual["available"]), (3, 0, 2))
        self.assertEqual(LeaveRequest.objects.get().status, RequestStatus.APPROVED)

    # --- History list ---

    def test_list_shows_only_own_requests_newest_first_with_filters(self, *_):
        first = self.submit(start="2026-10-05", end="2026-10-05").json()
        second = self.submit(start="2026-10-06", end="2026-10-06").json()
        services.reject_request(first["id"], self.admin, "Busy")
        services.create_request(self.other, "CASUAL", date(2026, 10, 5), date(2026, 10, 5), "x", today=TODAY)
        url = reverse("leave-requests")

        body = self.client.get(url).json()
        self.assertEqual([r["id"] for r in body["results"]], [second["id"], first["id"]])
        self.assertEqual(body["count"], 2)
        self.assertEqual([r["id"] for r in self.client.get(url, {"status": "REJECTED"}).json()["results"]], [first["id"]])
        self.assertEqual(self.client.get(url, {"year": "2027"}).json()["count"], 0)
        self.assertEqual(self.client.get(url, {"status": "DONE"}).json(), {"status": ["Select a valid choice."]})
        rejected = self.client.get(url, {"status": "REJECTED"}).json()["results"][0]
        self.assertEqual(rejected["review_remarks"], "Busy")
        self.assertEqual(rejected["reviewed_by"], {"id": self.admin.pk, "full_name": "boss"})
