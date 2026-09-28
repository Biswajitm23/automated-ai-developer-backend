"""Admin endpoints for leave requests: review and decide (ELM-007), list and summary (ELM-009).

Admin-only (IsAdminRole). Requests of deactivated employees stay visible and decidable.
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.employees import AdminAPIView

from . import services
from .models import REMARKS_MAX_LENGTH, LeaveRequest
from .serializers import LeaveRequestSerializer


def all_requests():
    return LeaveRequest.objects.select_related("employee__profile", "reviewed_by")


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
