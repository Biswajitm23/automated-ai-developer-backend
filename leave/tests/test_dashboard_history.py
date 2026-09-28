"""ELM-006 acceptance: dashboard figures, current statuses in history, own records only."""

from datetime import date
from unittest import mock

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance

TODAY = date(2026, 9, 23)
D = date.fromisoformat


@mock.patch("leave.rules.today_in_app_zone", return_value=TODAY)
@mock.patch("leave.employee_views.today_in_app_zone", return_value=TODAY)
class DashboardAndHistoryTests(APITestCase):
    def setUp(self):
        self.employee = make_user("emma", make_password())
        self.other = make_user("liam", make_password())
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        for user in (self.employee, self.other):
            Allowance.objects.create(employee=user, year=2026, leave_type="CASUAL", days=12)
            Allowance.objects.create(employee=user, year=2026, leave_type="SICK", days=6)
        make = lambda start, end, kind="CASUAL", who=None: services.create_request(  # noqa: E731
            who or self.employee, kind, D(start), D(end), "Reason", today=TODAY
        )
        self.approved = make("2026-10-05", "2026-10-07")  # 3
        services.approve_request(self.approved.pk, self.admin, "Enjoy")
        self.pending = make("2026-10-12", "2026-10-13")  # 2
        self.rejected = make("2026-10-19", "2026-10-19")  # 1
        services.reject_request(self.rejected.pk, self.admin, "Team offsite")
        self.cancelled = make("2026-10-20", "2026-10-21")  # 2
        services.cancel_request(self.cancelled.pk)
        self.sick = make("2026-11-02", "2026-11-02", "SICK")  # 1
        self.theirs = make("2026-10-05", "2026-10-05", who=self.other)
        self.client.force_authenticate(self.employee)

    def test_dashboard_figures_match_backend_calculations(self, *_):
        body = self.client.get(reverse("my-balances"), {"year": 2026}).json()

        self.assertEqual(
            {b["leave_type"]: (b["allowance"], b["approved"], b["pending"], b["available"]) for b in body["balances"]},
            # Casual: 12 - 3 approved - 2 pending; rejected and cancelled do not count.
            {"CASUAL": (12, 3, 2, 7), "SICK": (6, 0, 1, 5)},
        )

    def test_history_reflects_current_statuses_and_decision_details(self, *_):
        results = self.client.get(reverse("leave-requests"), {"year": 2026}).json()["results"]
        by_id = {r["id"]: r for r in results}

        self.assertEqual(
            {k: by_id[getattr(self, k).pk]["status"] for k in ("approved", "pending", "rejected", "cancelled", "sick")},
            {"approved": "APPROVED", "pending": "PENDING", "rejected": "REJECTED", "cancelled": "CANCELLED", "sick": "PENDING"},
        )
        self.assertEqual(by_id[self.rejected.pk]["review_remarks"], "Team offsite")
        self.assertIsNotNone(by_id[self.approved.pk]["reviewed_at"])
        self.assertIsNotNone(by_id[self.cancelled.pk]["cancelled_at"])

        services.approve_request(self.pending.pk, self.admin)
        refreshed = self.client.get(reverse("leave-request", args=[self.pending.pk])).json()
        self.assertEqual(refreshed["status"], "APPROVED")

    def test_changing_ids_never_reveals_other_employees_records(self, *_):
        listed = {r["id"] for r in self.client.get(reverse("leave-requests")).json()["results"]}
        self.assertNotIn(self.theirs.pk, listed)
        self.assertEqual(len(listed), 5)

        for pk in (self.theirs.pk, 999999):
            with self.subTest(pk=pk):
                response = self.client.get(reverse("leave-request", args=[pk]))
                self.assertEqual((response.status_code, response.json()), (404, {"detail": "Not found."}))

        # Query parameters cannot widen the scope either.
        self.assertEqual(
            self.client.get(reverse("leave-requests"), {"employee": self.other.pk}).json()["count"], 5
        )
