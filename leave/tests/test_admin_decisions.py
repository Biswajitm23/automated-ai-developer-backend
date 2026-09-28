from datetime import date

from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance, RequestStatus
from leave.tests.test_concurrency import run_concurrently

TODAY = date(2026, 9, 23)
D = date.fromisoformat


class AdminDecisionApiTests(APITestCase):
    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN, first_name="Neha", last_name="D")
        self.employee = make_user("emma", make_password(), first_name="Emma", last_name="Stone")
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=10)
        self.request = services.create_request(
            self.employee, "CASUAL", D("2026-10-05"), D("2026-10-07"), "Trip", today=TODAY
        )
        self.client.force_authenticate(self.admin)

    def decide(self, action, remarks=None, pk=None):
        body = {} if remarks is None else {"remarks": remarks}
        return self.client.post(
            reverse(f"admin-leave-request-{action}", args=[pk or self.request.pk]), body, format="json"
        )

    def balance(self):
        return services.balances_for(self.employee, 2026)["CASUAL"]

    def test_detail_includes_the_employees_balances_for_that_year(self):
        body = self.client.get(reverse("admin-leave-request", args=[self.request.pk])).json()

        self.assertEqual(body["id"], self.request.pk)
        self.assertEqual(body["employee"]["full_name"], "Emma Stone")
        self.assertEqual(
            body["balances"],
            [
                {"leave_type": "CASUAL", "year": 2026, "allowance": 10, "approved": 0, "pending": 3, "available": 7},
                {"leave_type": "SICK", "year": 2026, "allowance": 0, "approved": 0, "pending": 0, "available": 0},
            ],
        )

    def test_approve_with_optional_remarks_records_reviewer_and_time(self):
        response = self.decide("approve")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")
        self.assertEqual(body["reviewed_by"], {"id": self.admin.pk, "full_name": "Neha D"})
        self.assertIsNotNone(body["reviewed_at"])
        self.assertEqual(body["review_remarks"], "")
        self.assertEqual((self.balance().approved, self.balance().pending), (3, 0))

    def test_reject_requires_remarks_and_releases_reservation(self):
        for remarks in (None, "", "   "):
            with self.subTest(remarks=remarks):
                response = self.decide("reject", remarks)
                self.assertEqual(response.json(), {"remarks": ["Remarks are required when rejecting a request."]})
        self.assertEqual(self.decide("reject", "x" * 501).json(), {"remarks": ["Ensure this field has no more than 500 characters."]})

        response = self.decide("reject", "  Team offsite that week  ")
        self.assertEqual(response.json()["status"], "REJECTED")
        self.assertEqual(response.json()["review_remarks"], "Team offsite that week")
        self.assertEqual((self.balance().pending, self.balance().available), (0, 10))

    def test_repeated_decisions_are_409_and_change_nothing(self):
        self.decide("approve", "OK")

        again = self.decide("approve")
        reject = self.decide("reject", "Changed my mind")

        self.assertEqual((again.status_code, again.json()), (409, {"detail": "This request has already been processed (Approved)."}))
        self.assertEqual(reject.status_code, 409)
        self.assertEqual((self.balance().approved, self.balance().pending), (3, 0))

    def test_decisions_on_deactivated_employees_requests_still_work(self):
        self.employee.is_active = False
        self.employee.save()

        self.assertEqual(self.decide("approve").json()["status"], "APPROVED")

    def test_decision_details_appear_in_the_employees_history(self):
        self.decide("reject", "Busy week")
        self.client.force_authenticate(self.employee)

        body = self.client.get(reverse("leave-request", args=[self.request.pk])).json()
        self.assertEqual((body["status"], body["review_remarks"], body["reviewed_by"]["full_name"]), ("REJECTED", "Busy week", "Neha D"))

    def test_only_administrators_can_review_or_decide(self):
        self.client.force_authenticate(self.employee)
        self.assertEqual(self.client.get(reverse("admin-leave-request", args=[self.request.pk])).status_code, 403)
        self.assertEqual(self.decide("approve").status_code, 403)
        self.assertEqual(self.decide("reject", "no").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.decide("approve").status_code, 401)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.PENDING)

    def test_unknown_request_is_404(self):
        self.assertEqual(self.decide("approve", pk=999999).json(), {"detail": "Not found."})


class ConcurrentDecisionTests(TransactionTestCase):
    """Two admins deciding the same request at the same moment."""

    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        self.other_admin = make_user("chief", make_password(), role=Role.ADMIN)
        self.employee = make_user("emma", make_password())
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=4)
        self.request = services.create_request(
            self.employee, "CASUAL", D("2026-10-05"), D("2026-10-07"), "Trip", today=TODAY
        )

    def test_double_approve_and_approve_vs_reject_decide_once(self):
        for second in (
            lambda: services.approve_request(self.request.pk, self.other_admin),
            lambda: services.reject_request(self.request.pk, self.other_admin, "No"),
        ):
            with self.subTest(second=second):
                self.request.status = RequestStatus.PENDING
                self.request.save()
                outcomes = run_concurrently(lambda: services.approve_request(self.request.pk, self.admin), second)

                self.assertEqual(sum(1 for kind, _ in outcomes if kind == "ok"), 1, outcomes)
                balance = services.balances_for(self.employee, 2026)["CASUAL"]
                self.assertEqual(balance.approved + balance.pending, 3 if balance.approved else 0)
