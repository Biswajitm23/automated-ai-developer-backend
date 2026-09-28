"""Admin endpoints for leave requests: review and decide (ELM-007), list and summary (ELM-009).

Admin-only (IsAdminRole). Requests of deactivated employees stay visible and decidable.
"""

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.employees import AdminAPIView, employee_queryset
from core.pagination import StandardPagination

from . import services
from .models import REMARKS_MAX_LENGTH, LeaveRequest, LeaveType, RequestStatus
from .serializers import LeaveRequestSerializer


def all_requests():
    return LeaveRequest.objects.select_related("employee__profile", "reviewed_by")


RECENT_REQUESTS = 8
INVALID_CHOICE = "Select a valid choice."


def newest_first(requests: QuerySet) -> QuerySet:
    return requests.order_by("-created_at", "-id")


def status_counts(requests: QuerySet) -> dict[str, int]:
    """{PENDING, APPROVED, REJECTED, CANCELLED, total} in one query."""
    counts = requests.aggregate(
        total=Count("id"),
        **{status: Count("id", filter=Q(status=status)) for status in RequestStatus.values},
    )
    return {**{status: counts[status] for status in RequestStatus.values}, "total": counts["total"]}


class AdminRequestFilterSerializer(serializers.Serializer):
    """Query parameters of the admin request list. Blank values count as absent."""

    employee = serializers.IntegerField(
        required=False, error_messages={"invalid": INVALID_CHOICE, "max_string_length": INVALID_CHOICE}
    )
    status = serializers.ChoiceField(
        RequestStatus.choices, required=False, error_messages={"invalid_choice": INVALID_CHOICE}
    )
    leave_type = serializers.ChoiceField(
        LeaveType.choices, required=False, error_messages={"invalid_choice": INVALID_CHOICE}
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate_employee(self, value: int) -> int:
        # Any employee account, active or not; admins and unknown ids are not choices.
        if not employee_queryset().filter(pk=value).exists():
            raise serializers.ValidationError(INVALID_CHOICE)
        return value

    def validate(self, attrs: dict) -> dict:
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and end < start:
            raise serializers.ValidationError({"date_to": ["End of range must be on or after the start."]})
        return attrs

    def apply(self, requests: QuerySet) -> tuple[QuerySet, QuerySet]:
        """(matching every filter, matching every filter except status)."""
        data = self.validated_data
        if "employee" in data:
            requests = requests.filter(employee_id=data["employee"])
        if "leave_type" in data:
            requests = requests.filter(leave_type=data["leave_type"])
        # Overlap with the range: start_date <= date_to AND end_date >= date_from.
        if "date_to" in data:
            requests = requests.filter(start_date__lte=data["date_to"])
        if "date_from" in data:
            requests = requests.filter(end_date__gte=data["date_from"])
        matching = requests.filter(status=data["status"]) if "status" in data else requests
        return matching, requests


class AdminLeaveRequestListView(AdminAPIView):
    """GET /api/admin/leave-requests/ — every employee's requests, newest first, with
    status counts for all filters except `status` (the breakdown the status filter picks from)."""

    FILTERS = ("employee", "status", "leave_type", "date_from", "date_to")

    def get(self, request: Request) -> Response:
        params = {key: request.query_params[key] for key in self.FILTERS if request.query_params.get(key)}
        filters = AdminRequestFilterSerializer(data=params)
        filters.is_valid(raise_exception=True)
        matching, without_status = filters.apply(all_requests())
        paginator = StandardPagination()
        page = paginator.paginate_queryset(newest_first(matching), request, view=self)
        response = paginator.get_paginated_response(LeaveRequestSerializer(page, many=True).data)
        response.data["counts"] = status_counts(without_status)
        return response


class AdminSummaryView(AdminAPIView):
    """GET /api/admin/summary/ — counts over all requests, active employees, newest requests."""

    def get(self, request: Request) -> Response:
        counts = status_counts(LeaveRequest.objects.all())
        recent = newest_first(all_requests())[:RECENT_REQUESTS]
        return Response(
            {
                "counts": counts,
                "pending_count": counts[RequestStatus.PENDING],
                "active_employee_count": employee_queryset().filter(is_active=True).count(),
                "recent_requests": LeaveRequestSerializer(recent, many=True).data,
            }
        )


class ApproveSerializer(serializers.Serializer):
    remarks = serializers.CharField(max_length=REMARKS_MAX_LENGTH, allow_blank=True, required=False, default="")


class RejectSerializer(serializers.Serializer):
    remarks = serializers.CharField(
        max_length=REMARKS_MAX_LENGTH,
        error_messages={
            "required": "Remarks are required when rejecting a request.",
            "blank": "Remarks are required when rejecting a request.",
            "null": "Remarks are required when rejecting a request.",
        },
    )


def detail_body(leave_request: LeaveRequest) -> dict:
    """AdminLeaveRequestDetail: the request plus the employee's balances for its year."""
    balances = services.balances_for(leave_request.employee, leave_request.start_date.year)
    return {**LeaveRequestSerializer(leave_request).data, "balances": [b.as_dict() for b in balances.values()]}


class AdminLeaveRequestDetailView(AdminAPIView):
    def get(self, request: Request, pk: int) -> Response:
        return Response(detail_body(get_object_or_404(all_requests(), pk=pk)))


class _DecisionView(AdminAPIView):
    serializer_class: type[serializers.Serializer]

    def decide(self, pk: int, reviewer, remarks: str) -> LeaveRequest:
        raise NotImplementedError

    def post(self, request: Request, pk: int) -> Response:
        get_object_or_404(LeaveRequest, pk=pk)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.decide(pk, request.user, serializer.validated_data.get("remarks", ""))
        return Response(LeaveRequestSerializer(all_requests().get(pk=pk)).data)


class ApproveView(_DecisionView):
    """PENDING → APPROVED; 409 if already processed or the allowance no longer covers it."""

    serializer_class = ApproveSerializer

    def decide(self, pk, reviewer, remarks):
        return services.approve_request(pk, reviewer, remarks)


class RejectView(_DecisionView):
    """PENDING → REJECTED (remarks required); releases the reservation. 409 if processed."""

    serializer_class = RejectSerializer

    def decide(self, pk, reviewer, remarks):
        return services.reject_request(pk, reviewer, remarks)
