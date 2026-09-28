"""Admin API for employee accounts (ELM-003).

Only users whose role is EMPLOYEE are listed and managed here; administrators are
managed with `create_admin` and the Django admin site. Passwords are write-only,
validated by Django's password validators and stored hashed.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination

from .models import Profile, Role
from .permissions import IsAdminRole

User = get_user_model()

DUPLICATE_EMAIL = "An account with this email address already exists."
DUPLICATE_USERNAME = "A user with that username already exists."
DUPLICATE_EMPLOYEE_CODE = "An employee with this Employee ID already exists."


def employee_queryset():
    return User.objects.filter(profile__role=Role.EMPLOYEE).select_related("profile")


def full_name(user) -> str:
    return user.get_full_name().strip() or user.get_username()


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    department = serializers.CharField(source="profile.department")
    employee_code = serializers.CharField(source="profile.employee_code", allow_null=True)
    created_at = serializers.DateTimeField(source="date_joined")
    updated_at = serializers.DateTimeField(source="profile.updated_at")

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "department",
            "employee_code",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_full_name(self, user) -> str:
        return full_name(user)


class _EmployeeFieldsMixin(serializers.Serializer):
    """Field rules shared by create and update; `self.instance` is the user being edited."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False, default="")
    email = serializers.EmailField(max_length=254)
    department = serializers.CharField(max_length=100)
    employee_code = serializers.CharField(
        max_length=20, allow_blank=True, allow_null=True, required=False, default=None
    )

    def _others(self):
        users = User.objects.all()
        return users.exclude(pk=self.instance.pk) if self.instance is not None else users

    def validate_email(self, value: str) -> str:
        value = value.strip()
        if self._others().filter(email__iexact=value).exists():
            raise ValidationError(DUPLICATE_EMAIL)
        return value

    def validate_employee_code(self, value: str | None) -> str | None:
        # Stored upper-case so "bp081" and "BP081" count as the same ID.
        value = (value or "").strip().upper() or None
        if value is not None:
            others = Profile.objects.filter(employee_code=value)
            if self.instance is not None:
                others = others.exclude(user=self.instance)
            if others.exists():
                raise ValidationError(DUPLICATE_EMPLOYEE_CODE)
        return value


class EmployeeCreateSerializer(_EmployeeFieldsMixin):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    password = serializers.CharField(
        max_length=128, write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError(DUPLICATE_USERNAME)
        return value

    def validate(self, attrs: dict) -> dict:
        # Run the validators against an unsaved user so similarity checks see the new values.
        candidate = User(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as error:
            raise ValidationError({"password": list(error.messages)}) from error
        return attrs

    def create(self, validated_data: dict):
        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data["first_name"],
                last_name=validated_data.get("last_name", ""),
            )
            # The post_save signal created the profile with role EMPLOYEE.
            profile = user.profile
            profile.role = Role.EMPLOYEE
            profile.department = validated_data["department"]
            profile.employee_code = validated_data.get("employee_code")
            profile.save()
        return user


class EmployeeUpdateSerializer(_EmployeeFieldsMixin):
    """PATCH: role, username, password and is_active cannot be changed here."""

    def update(self, user, validated_data: dict):
        with transaction.atomic():
            for field in ("first_name", "last_name", "email"):
                if field in validated_data:
                    setattr(user, field, validated_data[field])
            user.save(update_fields=["first_name", "last_name", "email"])
            profile = user.profile
            if "department" in validated_data:
                profile.department = validated_data["department"]
            if "employee_code" in validated_data:
                profile.employee_code = validated_data["employee_code"]
            profile.save()  # also bumps updated_at
        return user


def _save_or_duplicate_error(serializer):
    """Save; a unique-constraint race that slipped past validation becomes a 400."""
    try:
        return serializer.save()
    except IntegrityError as error:
        text = str(error).lower()
        if "employee_code" in text:
            raise ValidationError({"employee_code": [DUPLICATE_EMPLOYEE_CODE]}) from error
        if "username" in text:
            raise ValidationError({"username": [DUPLICATE_USERNAME]}) from error
        raise ValidationError({"email": [DUPLICATE_EMAIL]}) from error


class AdminAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]


class EmployeeListView(AdminAPIView):
    STATUSES = {"active", "inactive", "all"}
    ORDERINGS = {"name": ("first_name", "last_name", "username", "id"), "-created_at": ("-date_joined", "-id")}

    def get(self, request: Request) -> Response:
        params = request.query_params
        status_filter = params.get("status") or "all"
        ordering = params.get("ordering") or "name"
        errors = {}
        if status_filter not in self.STATUSES:
            errors["status"] = ["Select a valid choice."]
        if ordering not in self.ORDERINGS:
            errors["ordering"] = ["Select a valid choice."]
        if errors:
            raise ValidationError(errors)

        users = employee_queryset()
        if status_filter != "all":
            users = users.filter(is_active=status_filter == "active")
        query = (params.get("q") or "").strip()
        if query:
            match = (
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(profile__department__icontains=query)
                | Q(profile__employee_code__icontains=query)
            )
            parts = query.split()
            if len(parts) > 1:
                # "Palash Purkait" matches first + last name.
                match |= Q(first_name__icontains=parts[0]) & Q(last_name__icontains=" ".join(parts[1:]))
            users = users.filter(match)
        if ordering == "name":
            users = users.order_by(Lower("first_name"), Lower("last_name"), Lower("username"), "id")
        else:
            users = users.order_by(*self.ORDERINGS[ordering])

        paginator = StandardPagination()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(EmployeeSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = EmployeeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _save_or_duplicate_error(serializer)
        user = employee_queryset().get(pk=user.pk)
        return Response(EmployeeSerializer(user).data, status=status.HTTP_201_CREATED)


class EmployeeDetailView(AdminAPIView):
    def get(self, request: Request, pk: int) -> Response:
        return Response(EmployeeSerializer(get_object_or_404(employee_queryset(), pk=pk)).data)

    def patch(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(employee_queryset(), pk=pk)
        serializer = EmployeeUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_or_duplicate_error(serializer)
        return Response(EmployeeSerializer(employee_queryset().get(pk=pk)).data)


class _SetActiveView(AdminAPIView):
    """Idempotent. Deactivated users are refused on their next request (session auth
    rejects inactive users) and cannot sign in; their leave history is kept."""

    active: bool

    def post(self, request: Request, pk: int) -> Response:
        with transaction.atomic():
            user = get_object_or_404(employee_queryset().select_for_update(of=("self",)), pk=pk)
            if user.is_active != self.active:
                user.is_active = self.active
                user.save(update_fields=["is_active"])
                user.profile.save(update_fields=["updated_at"])
        return Response(EmployeeSerializer(employee_queryset().get(pk=pk)).data)


class EmployeeDeactivateView(_SetActiveView):
    active = False


class EmployeeReactivateView(_SetActiveView):
    active = True
