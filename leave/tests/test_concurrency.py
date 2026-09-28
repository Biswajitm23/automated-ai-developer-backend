import threading
from datetime import date

from django.db import connection
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance, LeaveRequest, RequestStatus
from leave.services import Conflict

D = date.fromisoformat
TODAY = D("2026-09-23")


def run_concurrently(*calls):
    """Start every call at the same moment on its own thread/connection; return outcomes."""
    barrier = threading.Barrier(len(calls))
    outcomes = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait()
            outcomes[index] = ("ok", call())
        except Exception as error:  # noqa: BLE001 - the test inspects every outcome
            outcomes[index] = ("error", error)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes


class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.employee = make_user("emma", make_password())
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=4)

    def create(self, start, end):
        return lambda: services.create_request(
            self.employee, "CASUAL", D(start), D(end), "Trip", today=TODAY
        )

    def test_concurrent_requests_cannot_overspend_the_allowance(self):
        # Each needs 3 of the 4 days; only one may succeed.
        outcomes = run_concurrently(
            self.create("2026-10-05", "2026-10-07"),
            self.create("2026-10-12", "2026-10-14"),
            self.create("2026-10-19", "2026-10-21"),
        )

        successes = [o for o in outcomes if o[0] == "ok"]
        failures = [o for o in outcomes if o[0] == "error"]
        self.assertEqual(len(successes), 1, outcomes)
        self.assertTrue(all(isinstance(error, ValidationError) for _, error in failures), outcomes)
        balance = services.balances_for(self.employee, 2026)["CASUAL"]
        self.assertEqual((balance.pending, balance.available), (3, 1))

    def test_concurrent_overlapping_requests_create_only_one(self):
        outcomes = run_concurrently(
            self.create("2026-10-05", "2026-10-05"),
            self.create("2026-10-05", "2026-10-05"),
        )

        self.assertEqual(sum(1 for o in outcomes if o[0] == "ok"), 1, outcomes)
        self.assertEqual(LeaveRequest.objects.count(), 1)

    def test_concurrent_approve_and_cancel_resolve_to_one_outcome(self):
        request = services.create_request(
            self.employee, "CASUAL", D("2026-10-05"), D("2026-10-06"), "Trip", today=TODAY
        )

        outcomes = run_concurrently(
            lambda: services.approve_request(request.pk, self.admin),
            lambda: services.cancel_request(request.pk),
        )

        self.assertEqual(sum(1 for o in outcomes if o[0] == "ok"), 1, outcomes)
        self.assertTrue(any(isinstance(o[1], Conflict) for o in outcomes), outcomes)
        request.refresh_from_db()
        self.assertIn(request.status, {RequestStatus.APPROVED, RequestStatus.CANCELLED})
