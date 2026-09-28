from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import password_reset
from .authentication import enforce_csrf
from .models import PasswordResetCode
from .permissions import IsAdminRole
from .roles import get_role
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    UserSerializer,
)

INVALID_CREDENTIALS = "Invalid username or password."
RESET_CODE_SENT = (
    "If an account uses this email address, a reset code has been sent to it."
)
INVALID_RESET_CODE = "This code is incorrect or has expired. Request a new code and try again."


class CsrfView(APIView):
    """Issue a CSRF token in the body (and the csrftoken cookie) for the frontend's unsafe requests."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request: Request) -> Response:
        return Response({"csrfToken": get_token(request._request)})


class LoginView(APIView):
    """Start a session. Wrong password, unknown user and inactive user get the same 400 response."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request._request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": INVALID_CREDENTIALS}, status=status.HTTP_400_BAD_REQUEST)

        login(request._request, user)
        if serializer.validated_data["remember_me"]:
            # Persistent cookie that survives closing the browser.
            request.session.set_expiry(settings.REMEMBER_ME_SESSION_AGE)
        else:
            # Cookie ends with the browser session; the server still caps it at
            # SESSION_COOKIE_AGE.
            request.session.set_expiry(0)
        return Response({"user": UserSerializer(user).data})


class LogoutView(APIView):
    """End the session (server-side flush). Idempotent: anonymous callers also get 204.

    Keeps the default session authentication so user_logged_out receives the real user;
    CSRF is still enforced explicitly for anonymous callers.
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    """Email a one-time code. The response is the same whether or not the address is known."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.request_code(serializer.validated_data["email"])
        return Response({"detail": RESET_CODE_SENT})


class PasswordResetVerifyView(APIView):
    """Check a code without using it up, so the frontend can move on to the new-password step."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if password_reset.find_valid_code(data["email"], data["code"]) is None:
            return Response({"code": [INVALID_RESET_CODE]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Code accepted."})


class PasswordResetConfirmView(APIView):
    """Set a new password with a valid code. Signs the user out everywhere; no auto-login."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            reset_code = password_reset.find_valid_code(data["email"], data["code"], lock=True)
            if reset_code is None:
                return Response(
                    {"code": [INVALID_RESET_CODE]}, status=status.HTTP_400_BAD_REQUEST
                )
            user = reset_code.user
            try:
                validate_password(data["new_password"], user)
            except DjangoValidationError as error:
                # The code stays valid so the user can pick a stronger password.
                return Response(
                    {"new_password": list(error.messages)}, status=status.HTTP_400_BAD_REQUEST
                )
            # Changing the password also invalidates every existing session of this user.
            user.set_password(data["new_password"])
            user.save(update_fields=["password"])
            PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(
                used_at=timezone.now()
            )

        password_reset.notify_password_changed(user)
        return Response({"detail": "Your password has been updated. You can now sign in."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class AdminPingView(APIView):
    """Admin-only probe proving backend role enforcement."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "role": get_role(request.user).value})
