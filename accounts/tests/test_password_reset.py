import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import PasswordResetCode

from .helpers import make_password, make_user

User = get_user_model()

CODE_SENT = {"detail": "If an account uses this email address, a reset code has been sent to it."}
INVALID_CODE = {
    "code": ["This code is incorrect or has expired. Request a new code and try again."]
}


def code_from(message) -> str:
    return re.search(r"reset code is: (\d{6})", message.body).group(1)


class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = make_password()
        self.user = make_user("emma", self.password, first_name="Emma", email="emma@example.com")

    def request_code(self, email="emma@example.com"):
        return self.client.post(
            reverse("auth-password-reset-request"), {"email": email}, format="json"
        )

    def verify(self, code, email="emma@example.com"):
        return self.client.post(
            reverse("auth-password-reset-verify"), {"email": email, "code": code}, format="json"
        )

    def confirm(self, code, new_password, email="emma@example.com"):
        return self.client.post(
            reverse("auth-password-reset-confirm"),
            {"email": email, "code": code, "new_password": new_password},
            format="json",
        )

    def issue_code(self) -> str:
        self.request_code()
        return code_from(mail.outbox[-1])

    # --- Requesting a code ---

    def test_request_emails_a_six_digit_code_and_stores_only_its_hash(self):
        response = self.request_code()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CODE_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["emma@example.com"])
        code = code_from(mail.outbox[0])
        stored = PasswordResetCode.objects.get(user=self.user)
        self.assertNotIn(code, stored.code_hash)

    def test_request_matches_email_case_insensitively(self):
        self.request_code("EMMA@Example.com")

        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_email_gets_the_same_response_and_no_email(self):
        response = self.request_code("nobody@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CODE_SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_gets_the_same_response_and_no_email(self):
        self.user.is_active = False
        self.user.save()

        response = self.request_code()

        self.assertEqual(response.json(), CODE_SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_email_format_returns_field_error(self):
        response = self.request_code("not-an-email")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_second_request_within_cooldown_sends_nothing(self):
        self.request_code()
        response = self.request_code()

        self.assertEqual(response.json(), CODE_SENT)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(PASSWORD_RESET_RESEND_COOLDOWN=0)
    def test_new_code_replaces_the_previous_one(self):
        first = self.issue_code()
        second = self.issue_code()

        self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_request_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)

        response = client.post(
            reverse("auth-password-reset-request"), {"email": "emma@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    # --- Verifying a code ---

    def test_verify_accepts_the_right_code_without_using_it_up(self):
        code = self.issue_code()

        self.assertEqual(self.verify(code).status_code, 200)
        self.assertEqual(self.verify(code).status_code, 200)

    def test_verify_rejects_a_wrong_code(self):
        code = self.issue_code()
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"

        response = self.verify(wrong)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_CODE)

    def test_verify_rejects_a_code_for_another_email(self):
        make_user("liam", make_password(), email="liam@example.com")
        code = self.issue_code()

        self.assertEqual(self.verify(code, email="liam@example.com").status_code, 400)

    def test_code_stops_working_after_too_many_wrong_guesses(self):
        code = self.issue_code()
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"
        for _ in range(5):
            self.verify(wrong)

        self.assertEqual(self.verify(code).status_code, 400)

    def test_expired_code_is_rejected(self):
        code = self.issue_code()
        PasswordResetCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.verify(code).status_code, 400)

    def test_malformed_code_returns_friendly_field_error(self):
        response = self.verify("12ab")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"code": ["Enter the 6-digit code from the email."]})

    # --- Setting the new password ---

    def test_confirm_sets_new_password_and_sends_notice(self):
        code = self.issue_code()
        new_password = make_password()

        response = self.confirm(code, new_password)

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(mail.outbox[-1].subject, "Your password was changed")
        login = self.client.post(
            reverse("auth-login"), {"username": "emma", "password": new_password}, format="json"
        )
        self.assertEqual(login.status_code, 200)

    def test_code_cannot_be_used_twice(self):
        code = self.issue_code()
        self.confirm(code, make_password())

        response = self.confirm(code, make_password())

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), INVALID_CODE)

    def test_weak_password_is_rejected_and_code_stays_valid(self):
        code = self.issue_code()

        response = self.confirm(code, "123")

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.confirm(code, make_password()).status_code, 200)

    def test_confirm_with_wrong_code_does_not_change_password(self):
        code = self.issue_code()
        wrong = f"{(int(code) + 1) % 1_000_000:06d}"

        response = self.confirm(wrong, make_password())

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_reset_signs_the_user_out_of_existing_sessions(self):
        signed_in = APIClient()
        signed_in.post(
            reverse("auth-login"), {"username": "emma", "password": self.password}, format="json"
        )
        self.assertEqual(signed_in.get(reverse("auth-me")).status_code, 200)

        self.confirm(self.issue_code(), make_password())

        self.assertEqual(signed_in.get(reverse("auth-me")).status_code, 401)

    def test_user_deactivated_after_request_cannot_reset(self):
        code = self.issue_code()
        self.user.is_active = False
        self.user.save()

        self.assertEqual(self.confirm(code, make_password()).status_code, 400)

    def test_password_reset_endpoints_are_throttled(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"password_reset": "2/hour"}):
            self.request_code("a@example.com")
            self.verify("000000")
            response = self.request_code("c@example.com")

        self.assertEqual(response.status_code, 429)
