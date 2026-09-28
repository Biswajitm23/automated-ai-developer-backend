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


class CancelApiTests(APITestCase):
    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        self.employee = make_user("emma", make_password(), first_name="Emma", last_name="Stone")
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=10)
        self.request = services.create_request(
            self.employee, "CASUAL", D("2026-10-05"), D("2026-10-07"), "Trip", today=TODAY
        )
        self.client.force_authenticate(self.employee)

    def cancel(self, pk=None):
        return self.client.post(reverse("leave-request-cancel", args=[pk or self.request.pk]), {}, format="json")

    def balance(self):
        return services.balances_for(self.employee, 2026)["CASUAL"]

    def test_cancel_releases_reservation_and_keeps_the_request_in_history(self):
        self.assertEqual(self.balance().pending, 3)

        response = self.cancel()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["id"], body["status"]), (self.request.pk, "CANCELLED"))
        self.assertIsNotNone(body["cancelled_at"])
        self.assertEqual((self.balance().pending, self.balance().available), (0, 10))
        history = self.client.get(reverse("leave-requests"), {"year": 2026}).json()
        self.assertEqual([(r["id"], r["status"]) for r in history["results"]], [(self.request.pk, "CANCELLED")])
        balances = self.client.get(reverse("my-balances"), {"year": 2026}).json()["balances"]
        self.assertEqual(balances[0]["available"], 10)

    def test_repeated_cancel_is_409_and_releases_nothing_more(self):
        self.cancel()

        again = self.cancel()

        self.assertEqual(
            (again.status_code, again.json()),
            (409, {"detail": "Only pending requests can be cancelled. This request is Cancelled."}),
        )
        self.assertEqual((self.balance().pending, self.balance().available), (0, 10))

    def test_approved_and_rejected_requests_cannot_be_cancelled(self):
        rejected = services.create_request(
            self.employee, "CASUAL", D("2026-10-12"), D("2026-10-12"), "Visit", today=TODAY
        )
        services.approve_request(self.request.pk, self.admin)
        services.reject_request(rejected.pk, self.admin, "Busy week")

        for leave_request, label in ((self.request, "Approved"), (rejected, "Rejected")):
            with self.subTest(label=label):
                response = self.cancel(leave_request.pk)
                self.assertEqual(response.status_code, 409)
                self.assertIn(f"This request is {label}.", response.json()["detail"])
        self.assertEqual((self.balance().approved, self.balance().pending), (3, 0))

    def test_only_the_owner_can_cancel(self):
        other = make_user("olga", make_password())
        self.client.force_authenticate(other)
        self.assertEqual(self.cancel().json(), {"detail": "Not found."})

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.cancel().status_code, 403)

        self.client.force_authenticate(None)
        self.assertEqual(self.cancel().status_code, 401)

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.PENDING)

    def test_unknown_request_is_404(self):
        self.assertEqual(self.cancel(pk=999999).status_code, 404)


class ConcurrentCancelTests(TransactionTestCase):
    """The employee cancels while the request is being cancelled again or decided."""

    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        self.employee = make_user("emma", make_password())
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=4)
        self.request = services.create_request(
            self.employee, "CASUAL", D("2026-10-05"), D("2026-10-07"), "Trip", today=TODAY
        )

    def test_one_outcome_and_the_balance_changes_once(self):
        cancel = lambda: services.cancel_request(self.request.pk)  # noqa: E731
        for name, other in (
            ("double cancel", cancel),
            ("cancel vs reject", lambda: services.reject_request(self.request.pk, self.admin, "No")),
            ("cancel vs approve", lambda: services.approve_request(self.request.pk, self.admin)),
        ):
            with self.subTest(name):
                self.request.status = RequestStatus.PENDING
                self.request.save()

                outcomes = run_concurrently(cancel, other)

                self.assertEqual(sum(1 for kind, _ in outcomes if kind == "ok"), 1, outcomes)
                self.request.refresh_from_db()
                balance = services.balances_for(self.employee, 2026)["CASUAL"]
                expected_approved = 3 if self.request.status == RequestStatus.APPROVED else 0
                self.assertEqual((balance.approved, balance.pending), (expected_approved, 0))
