from datetime import date

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance, LeaveRequest, RequestStatus
from leave.services import Conflict

D = date.fromisoformat
TODAY = D("2026-09-23")  # Wednesday


class ServiceTestCase(TestCase):
    def setUp(self):
        self.employee = make_user("emma", make_password())
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="CASUAL", days=5)
        Allowance.objects.create(employee=self.employee, year=2026, leave_type="SICK", days=3)

    def create(self, start, end, leave_type="CASUAL", employee=None):
        return services.create_request(
            employee or self.employee, leave_type, D(start), D(end), "Family event", today=TODAY
        )

    def errors(self, start, end, leave_type="CASUAL"):
        with self.assertRaises(ValidationError) as caught:
            self.create(start, end, leave_type)
        return caught.exception.detail

    def balance(self, leave_type="CASUAL", year=2026):
        return services.balances_for(self.employee, year)[leave_type]


class CreateRequestTests(ServiceTestCase):
    def test_valid_request_is_pending_and_reserves_working_days(self):
        request = self.create("2026-09-25", "2026-09-28")  # Fri–Mon

        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.working_days, 2)
        balance = self.balance()
        self.assertEqual((balance.allowance, balance.approved, balance.pending, balance.available), (5, 0, 2, 3))
        self.assertEqual(self.balance("SICK").available, 3)

    def test_same_day_leave(self):
        self.assertEqual(self.create("2026-09-23", "2026-09-23").working_days, 1)

    def test_invalid_ranges_are_rejected_without_saving(self):
        cases = {
            ("2026-09-22", "2026-09-24"): "start_date",
            ("2026-10-05", "2026-10-02"): "end_date",
            ("2026-12-31", "2027-01-01"): "non_field_errors",
            ("2026-09-26", "2026-09-27"): "non_field_errors",
        }
        for (start, end), field in cases.items():
            with self.subTest(start=start, end=end):
                self.assertIn(field, self.errors(start, end))
        self.assertFalse(LeaveRequest.objects.exists())

    def test_unknown_leave_type(self):
        self.assertEqual(self.errors("2026-09-24", "2026-09-24", "MATERNITY"), {"leave_type": ["Select a valid choice."]})

    def test_overlap_with_pending_or_approved_is_rejected(self):
        first = self.create("2026-10-05", "2026-10-07")

        detail = self.errors("2026-10-07", "2026-10-08")
        self.assertEqual(
            [str(m) for m in detail["non_field_errors"]],
            [f"These dates overlap your pending or approved request #{first.pk} (5 Oct – 7 Oct 2026)."],
        )

        services.approve_request(first.pk, self.admin)
        self.assertIn("non_field_errors", self.errors("2026-10-05", "2026-10-05", "SICK"))

    def test_overlap_check_ignores_rejected_cancelled_and_other_employees(self):
        rejected = self.create("2026-10-05", "2026-10-05")
        services.reject_request(rejected.pk, self.admin, "Busy week")
        cancelled = self.create("2026-10-06", "2026-10-06")
        services.cancel_request(cancelled.pk)
        other = make_user("liam", make_password())
        Allowance.objects.create(employee=other, year=2026, leave_type="CASUAL", days=5)
        self.create("2026-10-05", "2026-10-06", employee=other)

        self.assertEqual(self.create("2026-10-05", "2026-10-06").working_days, 2)

    def test_adjacent_ranges_do_not_overlap(self):
        self.create("2026-10-05", "2026-10-06")
        self.assertEqual(self.create("2026-10-07", "2026-10-07").working_days, 1)

    def test_insufficient_balance(self):
        self.create("2026-10-05", "2026-10-07")  # 3 of 5

        detail = self.errors("2026-10-12", "2026-10-14")  # 3 more
        self.assertEqual(
            [str(m) for m in detail["non_field_errors"]],
            ["Not enough Casual Leave: 3 working days requested, 2 available."],
        )
        self.assertEqual(self.balance().pending, 3)

    def test_request_using_exactly_the_remaining_balance_is_allowed(self):
        self.assertEqual(self.create("2026-10-05", "2026-10-09").working_days, 5)
        self.assertEqual(self.balance().available, 0)

    def test_no_allowance_means_zero_available(self):
        detail = self.errors("2027-01-04", "2027-01-04")
        self.assertEqual(
            [str(m) for m in detail["non_field_errors"]],
            ["Not enough Casual Leave: 1 working day requested, 0 available."],
        )

    def test_balances_are_per_year_of_the_start_date(self):
        Allowance.objects.create(employee=self.employee, year=2027, leave_type="CASUAL", days=2)
        self.create("2027-01-04", "2027-01-05")

        self.assertEqual(self.balance(year=2027).pending, 2)
        self.assertEqual(self.balance(year=2026).pending, 0)


class StatusChangeTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.request = self.create("2026-10-05", "2026-10-07")  # 3 days

    def test_approve_moves_reservation_to_used_and_records_reviewer(self):
        approved = services.approve_request(self.request.pk, self.admin, "Enjoy")

        self.assertEqual(approved.status, RequestStatus.APPROVED)
        self.assertEqual(approved.reviewed_by, self.admin)
        self.assertIsNotNone(approved.reviewed_at)
        self.assertEqual(approved.review_remarks, "Enjoy")
        balance = self.balance()
        self.assertEqual((balance.approved, balance.pending, balance.available), (3, 0, 2))

    def test_reject_releases_reservation(self):
        services.reject_request(self.request.pk, self.admin, "Team offsite")

        balance = self.balance()
        self.assertEqual((balance.approved, balance.pending, balance.available), (0, 0, 5))

    def test_cancel_releases_reservation_once(self):
        cancelled = services.cancel_request(self.request.pk)
        self.assertEqual(cancelled.status, RequestStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        self.assertEqual(self.balance().available, 5)

        with self.assertRaisesMessage(Conflict, "Only pending requests can be cancelled. This request is Cancelled."):
            services.cancel_request(self.request.pk)
        self.assertEqual(self.balance().available, 5)

    def test_decisions_on_processed_requests_are_conflicts(self):
        services.approve_request(self.request.pk, self.admin)

        with self.assertRaisesMessage(Conflict, "This request has already been processed (Approved)."):
            services.approve_request(self.request.pk, self.admin)
        with self.assertRaisesMessage(Conflict, "This request has already been processed (Approved)."):
            services.reject_request(self.request.pk, self.admin, "No")
        with self.assertRaisesMessage(Conflict, "Only pending requests can be cancelled. This request is Approved."):
            services.cancel_request(self.request.pk)
        self.assertEqual(self.balance().approved, 3)

    def test_approval_rechecks_the_allowance(self):
        # Simulate an allowance lowered outside the API's own minimum check.
        Allowance.objects.filter(employee=self.employee, leave_type="CASUAL").update(days=2)

        with self.assertRaisesMessage(Conflict, "Approval would exceed the Casual Leave allowance for 2026 (2 days)."):
            services.approve_request(self.request.pk, self.admin)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.PENDING)

    def test_released_days_can_be_requested_again(self):
        services.reject_request(self.request.pk, self.admin, "No")

        self.assertEqual(self.create("2026-10-05", "2026-10-09").working_days, 5)
