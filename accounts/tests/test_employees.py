from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role

from .helpers import make_password, make_user

User = get_user_model()


def employee_payload(**overrides):
    data = {
        "first_name": "Palash",
        "last_name": "Purkait",
        "email": "palash@example.com",
        "department": "Engineering",
        "username": "palash081",
        "password": make_password(),
        "employee_code": "BP081",
    }
    data.update(overrides)
    return data


class EmployeeApiTestCase(APITestCase):
    def setUp(self):
        self.admin = make_user("boss", make_password(), role=Role.ADMIN, email="boss@example.com")
        self.client.force_authenticate(self.admin)
        self.employee = make_user(
            "emma", make_password(), first_name="Emma", last_name="Stone", email="emma@example.com"
        )
        self.employee.profile.department = "Finance"
        self.employee.profile.save()

    def create(self, **overrides):
        return self.client.post(reverse("admin-employees"), employee_payload(**overrides), format="json")


class CreateEmployeeTests(EmployeeApiTestCase):
    def test_admin_creates_employee_and_password_is_hashed_never_returned(self):
        payload = employee_payload()

        response = self.create(password=payload["password"])

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertNotIn("password", body)
        self.assertNotIn(payload["password"], response.content.decode())
        self.assertEqual(body["full_name"], "Palash Purkait")
        self.assertEqual(body["department"], "Engineering")
        self.assertEqual(body["employee_code"], "BP081")
        self.assertTrue(body["is_active"])
        user = User.objects.get(username="palash081")
        self.assertEqual(user.profile.role, Role.EMPLOYEE)
        self.assertFalse(user.is_staff)
        self.assertNotEqual(user.password, payload["password"])
        self.assertTrue(user.check_password(payload["password"]))

    def test_duplicate_email_is_rejected_case_insensitively(self):
        response = self.create(email="EMMA@Example.com")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"email": ["An account with this email address already exists."]}
        )

    def test_email_used_by_an_admin_is_also_rejected(self):
        self.assertEqual(self.create(email="boss@example.com").status_code, 400)

    def test_duplicate_username_is_rejected_case_insensitively(self):
        response = self.create(username="EMMA")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"username": ["A user with that username already exists."]})

    def test_duplicate_employee_code_is_rejected_case_insensitively(self):
        self.create()

        response = self.create(email="other@example.com", username="other", employee_code="bp081")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"employee_code": ["An employee with this Employee ID already exists."]}
        )

    def test_employee_code_is_optional_and_blank_codes_do_not_clash(self):
        first = self.create(employee_code="")
        second = self.create(email="b@example.com", username="bee", employee_code="")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertIsNone(second.json()["employee_code"])

    def test_weak_password_is_rejected_with_validator_messages(self):
        response = self.create(password="123")

        self.assertEqual(response.status_code, 400)
        self.assertIn("This password is too short. It must contain at least 8 characters.", response.json()["password"])
        self.assertFalse(User.objects.filter(username="palash081").exists())

    def test_password_similar_to_username_is_rejected(self):
        response = self.create(password="palash081x")

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json())

    def test_required_fields(self):
        response = self.client.post(reverse("admin-employees"), {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            set(response.json()), {"first_name", "email", "department", "username", "password"}
        )

    def test_blank_department_is_rejected(self):
        response = self.create(department="  ")

        self.assertEqual(response.json(), {"department": ["This field may not be blank."]})

    def test_role_in_payload_is_ignored(self):
        response = self.create(role="ADMIN", is_staff=True)

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="palash081")
        self.assertEqual(user.profile.role, Role.EMPLOYEE)
        self.assertFalse(user.is_staff)


class ListAndDetailTests(EmployeeApiTestCase):
    def setUp(self):
        super().setUp()
        self.create()
        self.inactive = make_user("zed", make_password(), first_name="Zed", email="zed@example.com")
        self.inactive.is_active = False
        self.inactive.save()

    def list(self, **params):
        return self.client.get(reverse("admin-employees"), params)

    def test_list_shows_only_employees_ordered_by_name_with_pagination_fields(self):
        body = self.list().json()

        self.assertEqual(
            set(body), {"count", "next", "previous", "page", "page_size", "total_pages", "results"}
        )
        self.assertEqual([e["username"] for e in body["results"]], ["emma", "palash081", "zed"])
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(body["total_pages"], 1)

    def test_status_filter(self):
        self.assertEqual([e["username"] for e in self.list(status="active").json()["results"]], ["emma", "palash081"])
        self.assertEqual([e["username"] for e in self.list(status="inactive").json()["results"]], ["zed"])
        self.assertEqual(self.list(status="gone").status_code, 400)

    def test_search_matches_name_email_department_and_employee_code(self):
        for query, expected in [
            ("stone", ["emma"]),
            ("PALASH@", ["palash081"]),
            ("finance", ["emma"]),
            ("bp081", ["palash081"]),
            ("Palash Purkait", ["palash081"]),
        ]:
            with self.subTest(query=query):
                self.assertEqual([e["username"] for e in self.list(q=query).json()["results"]], expected)

    def test_page_size_and_out_of_range_page(self):
        body = self.list(page_size=2).json()
        self.assertEqual((body["count"], body["total_pages"], len(body["results"])), (3, 2, 2))
        self.assertIsNotNone(body["next"])

        response = self.list(page=9)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Invalid page."})

    def test_newest_first_ordering(self):
        body = self.list(ordering="-created_at").json()

        self.assertEqual(body["results"][0]["username"], "zed")

    def test_detail_and_admin_accounts_are_not_found(self):
        self.assertEqual(self.client.get(reverse("admin-employee", args=[self.employee.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin-employee", args=[self.admin.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("admin-employee", args=[99999])).status_code, 404)


class UpdateAndDeactivateTests(EmployeeApiTestCase):
    def patch(self, **data):
        return self.client.patch(reverse("admin-employee", args=[self.employee.pk]), data, format="json")

    def test_patch_updates_fields(self):
        response = self.patch(first_name="Emily", department="HR", employee_code="bp100")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["full_name"], body["department"], body["employee_code"]), ("Emily Stone", "HR", "BP100"))

    def test_patch_keeps_own_email_and_rejects_someone_elses(self):
        self.assertEqual(self.patch(email="Emma@example.com").status_code, 200)
        response = self.patch(email="boss@example.com")
        self.assertEqual(response.json(), {"email": ["An account with this email address already exists."]})

    def test_patch_cannot_change_role_username_password_or_active(self):
        before = self.employee.password
        self.patch(role="ADMIN", username="hacker", password="x", is_active=False)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.profile.role, Role.EMPLOYEE)
        self.assertEqual(self.employee.username, "emma")
        self.assertEqual(self.employee.password, before)
        self.assertTrue(self.employee.is_active)

    def test_partial_patch_does_not_clear_other_fields(self):
        self.patch(employee_code="BP001")
        self.patch(first_name="Em")

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.last_name, "Stone")
        self.assertEqual(self.employee.profile.employee_code, "BP001")

    def test_deactivate_and_reactivate_are_idempotent_and_block_access(self):
        password = make_password()
        self.employee.set_password(password)
        self.employee.save()
        employee_client = APIClient()
        employee_client.post(reverse("auth-login"), {"username": "emma", "password": password}, format="json")
        self.assertEqual(employee_client.get(reverse("auth-me")).status_code, 200)

        url = reverse("admin-employee-deactivate", args=[self.employee.pk])
        self.assertFalse(self.client.post(url, {}, format="json").json()["is_active"])
        self.assertFalse(self.client.post(url, {}, format="json").json()["is_active"])
        self.assertEqual(employee_client.get(reverse("auth-me")).status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.employee.pk).exists())

        url = reverse("admin-employee-reactivate", args=[self.employee.pk])
        self.assertTrue(self.client.post(url, {}, format="json").json()["is_active"])


class PermissionTests(APITestCase):
    def setUp(self):
        self.employee = make_user("emma", make_password(), email="emma@example.com")

    def test_employee_cannot_use_admin_employee_endpoints(self):
        self.client.force_authenticate(self.employee)
        urls = [
            ("get", reverse("admin-employees")),
            ("post", reverse("admin-employees")),
            ("get", reverse("admin-employee", args=[self.employee.pk])),
            ("patch", reverse("admin-employee", args=[self.employee.pk])),
            ("post", reverse("admin-employee-deactivate", args=[self.employee.pk])),
            ("post", reverse("admin-employee-reactivate", args=[self.employee.pk])),
        ]
        for method, url in urls:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {"role": "ADMIN"}, format="json")
                self.assertEqual(response.status_code, 403)
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.role, Role.EMPLOYEE)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(reverse("admin-employees")).status_code, 401)
