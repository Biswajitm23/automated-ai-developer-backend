from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.employees import AdminAPIView, employee_queryset

from .models import MAX_YEAR, MIN_YEAR, Allowance, LeaveType
from .serializers import AllowanceInputSerializer, AllowanceYearSerializer
from .usage import usage_for


class LeaveTypeListView(APIView):
    """Any signed-in user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response([{"code": code, "name": name} for code, name in LeaveType.choices])


def allowance_rows(employee, year: int, only: str | None = None) -> list[dict]:
    stored = {a.leave_type: a for a in Allowance.objects.filter(employee=employee, year=year)}
    usage = usage_for(employee, year)
    rows = []
    for code in LeaveType.values:
        if only is not None and code != only:
            continue
        allowance = stored.get(code)
        days = allowance.days if allowance else 0
        used = usage[code]
        rows.append(
            {
                "employee_id": employee.pk,
                "year": year,
                "leave_type": code,
                "days": days,
                "approved": used.approved,
                "pending": used.pending,
                "available": days - used.committed,
                "minimum_allowed": used.committed,
                "updated_at": allowance.updated_at if allowance else None,
            }
        )
    return rows


def _serialize(rows: list[dict]) -> list[dict]:
    """Render updated_at like every other datetime in the API (ISO 8601, Asia/Kolkata)."""
    field = DateTimeField()
    return [
        {**row, "updated_at": field.to_representation(row["updated_at"]) if row["updated_at"] else None}
        for row in rows
    ]


class EmployeeAllowancesView(AdminAPIView):
    """GET /api/admin/employees/{id}/allowances/?year= — one row per leave type."""

    def get(self, request: Request, pk: int) -> Response:
        employee = get_object_or_404(employee_queryset(), pk=pk)
        if not request.query_params.get("year"):
            raise ValidationError({"year": ["This field is required."]})
        params = AllowanceYearSerializer(data={"year": request.query_params["year"]})
        params.is_valid(raise_exception=True)
        year = params.validated_data["year"]
        return Response(
            {"employee_id": employee.pk, "year": year, "allowances": _serialize(allowance_rows(employee, year))}
        )


class AllowanceDetailView(AdminAPIView):
    """PUT /api/admin/employees/{id}/allowances/{year}/{leave_type}/ {"days": n} — upsert."""

    def put(self, request: Request, pk: int, year: int, leave_type: str) -> Response:
        if not (MIN_YEAR <= year <= MAX_YEAR) or leave_type not in LeaveType.values:
            raise NotFound()
        serializer = AllowanceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        days = serializer.validated_data["days"]

        with transaction.atomic():
            # Lock the employee row: allowance changes and (from ELM-005) leave requests for
            # this employee are serialised, so usage cannot change between check and write.
            employee = get_object_or_404(employee_queryset().select_for_update(of=("self",)), pk=pk)
            minimum = usage_for(employee, year)[leave_type].committed
            if days < minimum:
                unit = "day" if minimum == 1 else "days"
                raise ValidationError(
                    {"days": [f"Allowance cannot be less than approved plus pending leave ({minimum} {unit})."]}
                )
            Allowance.objects.update_or_create(
                employee=employee, year=year, leave_type=leave_type, defaults={"days": days}
            )
        return Response(_serialize(allowance_rows(employee, year, only=leave_type))[0])
