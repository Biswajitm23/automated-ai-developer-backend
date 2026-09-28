"""Employee endpoints: own balances and leave requests (ELM-005/006/008).

Every endpoint requires the EMPLOYEE role and only ever touches the caller's own
records: another user's request is a 404, so its existence does not leak.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsEmployeeRole
from core.pagination import StandardPagination

from . import services
from .models import LeaveRequest, RequestStatus
from .rules import count_working_days, today_in_app_zone
from .serializers import (
    AllowanceYearSerializer,
    LeavePreviewSerializer,
    LeaveRequestCreateSerializer,
    LeaveRequestSerializer,
)


class EmployeeAPIView(APIView):
    permission_classes = [IsAuthenticated, IsEmployeeRole]


def own_requests(user):
    return LeaveRequest.objects.filter(employee=user).select_related(
        "employee__profile", "reviewed_by"
    )


def year_param(request: Request, default: int | None = None) -> int | None:
    raw = request.query_params.get("year")
    if not raw:
        return default
    params = AllowanceYearSerializer(data={"year": raw})
    params.is_valid(raise_exception=True)
    return params.validated_data["year"]


def plain_errors(detail) -> dict[str, list[str]]:
    """DRF error detail → {field: [str, …]} (the 400 body shape)."""
    if isinstance(detail, dict):
        return {key: [str(m) for m in (value if isinstance(value, list) else [value])] for key, value in detail.items()}
    return {"non_field_errors": [str(m) for m in (detail if isinstance(detail, list) else [detail])]}


class MyBalancesView(EmployeeAPIView):
    """GET /api/me/balances/?year= (default: the current Asia/Kolkata year)."""

    def get(self, request: Request) -> Response:
        year = year_param(request, default=today_in_app_zone().year)
        balances = services.balances_for(request.user, year)
        return Response({"year": year, "balances": [b.as_dict() for b in balances.values()]})


def status_param(request: Request) -> str | None:
    raw = request.query_params.get("status")
    if not raw:
        return None
    if raw not in RequestStatus.values:
        raise ValidationError({"status": ["Select a valid choice."]})
    return raw


class LeaveRequestCollectionView(EmployeeAPIView):
    def get(self, request: Request) -> Response:
        """The caller's own requests, newest first. `year` = year of the start date
        (requests never span years); `status` = one status code."""
        requests = own_requests(request.user)
        year = year_param(request)
        if year is not None:
            requests = requests.filter(start_date__year=year)
        wanted = status_param(request)
        if wanted is not None:
            requests = requests.filter(status=wanted)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(requests.order_by("-created_at", "-id"), request, view=self)
        return paginator.get_paginated_response(LeaveRequestSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        """Create a PENDING request for the caller. Any `employee` field is ignored.
        The same client_request_id again returns 200 with the original request."""
        serializer = LeaveRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave_request = services.create_request(
            request.user,
            data["leave_type"],
            data["start_date"],
            data["end_date"],
            data["reason"],
            client_request_id=data["client_request_id"],
        )
        created = leave_request.created_now
        body = LeaveRequestSerializer(own_requests(request.user).get(pk=leave_request.pk)).data
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class LeaveRequestDetailView(EmployeeAPIView):
    def get(self, request: Request, pk: int) -> Response:
        return Response(LeaveRequestSerializer(get_object_or_404(own_requests(request.user), pk=pk)).data)


class LeavePreviewView(EmployeeAPIView):
    """GET /api/leave-requests/preview/?leave_type=&start_date=&end_date= — the create
    checks without saving. Always 200: {valid, working_days, balance} or {valid, working_days, errors}."""

    def get(self, request: Request) -> Response:
        serializer = LeavePreviewSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response({"valid": False, "working_days": 0, "errors": plain_errors(serializer.errors)})
        data = serializer.validated_data
        working_days = count_working_days(data["start_date"], data["end_date"])
        try:
            working_days, balance = services.check_request(
                request.user, data["leave_type"], data["start_date"], data["end_date"]
            )
        except ValidationError as error:
            return Response({"valid": False, "working_days": working_days, "errors": plain_errors(error.detail)})
        return Response({"valid": True, "working_days": working_days, "balance": balance.as_dict()})
