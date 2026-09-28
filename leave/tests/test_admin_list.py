from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.helpers import make_password, make_user
from leave import services
from leave.models import Allowance

TODAY = date(2026, 9, 23)
D = date.fromisoformat
NO_COUNTS = {"PENDING": 0, "APPROVED": 0, "REJECTED": 0, "CANCELLED": 0, "total": 0}


class AdminRequestListTests(APITestCase):
    """Emma: casual 5–7 Oct (approved), sick 12 Oct (pending), casual 2–3 Nov (rejected).
    Ravi (deactivated later): casual 8–9 Oct (pending), casual 20 Oct (cancelled).
    Created in that order, so the newest is Ravi's cancelled one."""

    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN)
        self.emma = make_user("emma", make_password(), first_name="Emma", last_name="Stone")
        self.ravi = make_user("ravi", make_password(), first_name="Ravi", last_name="Kumar")
        for employee in (self.emma, self.ravi):
            for leave_type in ("CASUAL", "SICK"):
                Allowance.objects.create(employee=employee, year=2026, leave_type=leave_type, days=10)

        def make(employee, leave_type, start, end):
            return services.create_request(employee, leave_type, D(start), D(end), "Reason", today=TODAY)

        self.emma_approved = make(self.emma, "CASUAL", "2026-10-05", "2026-10-07")
        self.emma_sick = make(self.emma, "SICK", "2026-10-12", "2026-10-12")
        self.emma_rejected = make(self.emma, "CASUAL", "2026-11-02", "2026-11-03")
        self.ravi_pending = make(self.ravi, "CASUAL", "2026-10-08", "2026-10-09")
        self.ravi_cancelled = make(self.ravi, "CASUAL", "2026-10-20", "2026-10-20")
        services.approve_request(self.emma_approved.pk, self.admin)
        services.reject_request(self.emma_rejected.pk, self.admin, "Busy")
        services.cancel_request(self.ravi_cancelled.pk)
        self.ravi.is_active = False
        self.ravi.save()
        self.client.force_authenticate(self.admin)

    def list(self, **params):
        response = self.client.get(reverse("admin-leave-requests"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def ids(self, body):
        return [row["id"] for row in body["results"]]

    def test_all_requests_newest_first_with_counts_and_row_details(self):
        body = self.list()

        self.assertEqual(
            self.ids(body),
            [r.pk for r in (self.ravi_cancelled, self.ravi_pending, self.emma_rejected, self.emma_sick, self.emma_approved)],
        )
        self.assertEqual(body["counts"], {"PENDING": 2, "APPROVED": 1, "REJECTED": 1, "CANCELLED": 1, "total": 5})
        row = body["results"][-1]
        self.assertEqual(
            (row["employee"]["full_name"], row["leave_type"], row["start_date"], row["end_date"], row["working_days"], row["status"]),
            ("Emma Stone", "CASUAL", "2026-10-05", "2026-10-07", 3, "APPROVED"),
        )

    def test_each_filter_on_its_own(self):
        self.assertEqual(set(self.ids(self.list(employee=self.ravi.pk))), {self.ravi_pending.pk, self.ravi_cancelled.pk})
        self.assertEqual(set(self.ids(self.list(status="PENDING"))), {self.emma_sick.pk, self.ravi_pending.pk})
        self.assertEqual(self.ids(self.list(leave_type="SICK")), [self.emma_sick.pk])
        self.assertEqual(self.ids(self.list(date_from="2026-11-01")), [self.emma_rejected.pk])
        self.assertEqual(self.ids(self.list(date_to="2026-10-05")), [self.emma_approved.pk])

    def test_date_range_includes_requests_that_overlap_it(self):
        # 6–8 Oct overlaps 5–7 Oct (approved) and 8–9 Oct (pending), but not 12 Oct.
        body = self.list(date_from="2026-10-06", date_to="2026-10-08")
        self.assertEqual(set(self.ids(body)), {self.emma_approved.pk, self.ravi_pending.pk})
        # A single day inside a longer request still matches it.
        self.assertEqual(self.ids(self.list(date_from="2026-10-06", date_to="2026-10-06")), [self.emma_approved.pk])

    def test_filters_combine_and_counts_follow_all_filters_but_status(self):
        body = self.list(employee=self.emma.pk, leave_type="CASUAL", status="APPROVED")

        self.assertEqual(self.ids(body), [self.emma_approved.pk])
        # Emma's casual requests: one approved, one rejected, whatever the status filter says.
        self.assertEqual(body["counts"], {**NO_COUNTS, "APPROVED": 1, "REJECTED": 1, "total": 2})

        body = self.list(employee=self.ravi.pk, date_from="2026-10-15")
        self.assertEqual(self.ids(body), [self.ravi_cancelled.pk])
        self.assertEqual(body["counts"], {**NO_COUNTS, "CANCELLED": 1, "total": 1})

    def test_no_matches_is_an_empty_page_with_zero_counts(self):
        body = self.list(date_from="2027-01-01")
        self.assertEqual((body["count"], body["results"], body["counts"]), (0, [], NO_COUNTS))

    def test_blank_parameters_are_ignored(self):
        self.assertEqual(self.list(employee="", status="", leave_type="", date_from="", date_to="")["count"], 5)

    def test_pagination(self):
        body = self.list(page_size=2, page=2)
        self.assertEqual((body["count"], body["page"], body["total_pages"]), (5, 2, 3))
        self.assertEqual(self.ids(body), [self.emma_rejected.pk, self.emma_sick.pk])
        self.assertEqual(body["counts"]["total"], 5)

    def test_invalid_parameters_are_400(self):
        cases = [
            ({"employee": "abc"}, {"employee": ["Select a valid choice."]}),
            ({"employee": self.admin.pk}, {"employee": ["Select a valid choice."]}),
            ({"employee": 999999}, {"employee": ["Select a valid choice."]}),
            ({"status": "DONE"}, {"status": ["Select a valid choice."]}),
            ({"leave_type": "EARNED"}, {"leave_type": ["Select a valid choice."]}),
            ({"date_from": "05-10-2026"}, {"date_from": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]}),
            ({"date_from": "2026-10-09", "date_to": "2026-10-08"}, {"date_to": ["End of range must be on or after the start."]}),
        ]
        for params, errors in cases:
            with self.subTest(params=params):
                response = self.client.get(reverse("admin-leave-requests"), params)
                self.assertEqual((response.status_code, response.json()), (400, errors))

    def test_summary_counts_active_employees_and_recent_requests(self):
        body = self.client.get(reverse("admin-summary")).json()

        self.assertEqual(body["counts"], {"PENDING": 2, "APPROVED": 1, "REJECTED": 1, "CANCELLED": 1, "total": 5})
        self.assertEqual(body["pending_count"], 2)
        self.assertEqual(body["active_employee_count"], 1)  # Ravi is deactivated; admins do not count
        self.assertEqual([r["id"] for r in body["recent_requests"]][:2], [self.ravi_cancelled.pk, self.ravi_pending.pk])

    def test_summary_keeps_only_the_newest_eight(self):
        Allowance.objects.filter(employee=self.emma, leave_type="CASUAL").update(days=30)
        weekdays = [f"2026-12-{day:02d}" for day in (1, 2, 3, 4, 7, 8, 9, 10, 11, 14)]
        for day in weekdays:  # 10 more one-day requests, created oldest first
            services.create_request(self.emma, "CASUAL", D(day), D(day), "x", today=TODAY)
        recent = self.client.get(reverse("admin-summary")).json()["recent_requests"]
        self.assertEqual([r["start_date"] for r in recent], weekdays[::-1][:8])

    def test_employees_and_anonymous_users_cannot_use_the_dashboard_apis(self):
        for url in (reverse("admin-leave-requests"), reverse("admin-summary")):
            with self.subTest(url=url):
                self.client.force_authenticate(self.emma)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.client.force_authenticate(None)
                self.assertEqual(self.client.get(url).status_code, 401)
