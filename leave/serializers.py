from rest_framework import serializers

from .models import MAX_ALLOWANCE_DAYS, MAX_YEAR, MIN_YEAR, REASON_MAX_LENGTH, LeaveRequest, LeaveType


class StrictIntegerField(serializers.IntegerField):
    """Accepts JSON integers only: not "12", 12.5 or true."""

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class AllowanceInputSerializer(serializers.Serializer):
    days = StrictIntegerField(min_value=0, max_value=MAX_ALLOWANCE_DAYS)


class AllowanceYearSerializer(serializers.Serializer):
    """`?year=` query parameter: four digits, 2000–2100."""

    year = serializers.CharField()

    def validate_year(self, value: str) -> int:
        if not (value.isdigit() and len(value) == 4 and MIN_YEAR <= int(value) <= MAX_YEAR):
            raise serializers.ValidationError("Enter a valid year.")
        return int(value)


def person_name(user) -> str:
    return user.get_full_name().strip() or user.get_username()


class EmployeeRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField()
    department = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()

    def get_full_name(self, user) -> str:
        return person_name(user)

    def get_department(self, user) -> str:
        profile = getattr(user, "profile", None)
        return profile.department if profile else ""


class PersonRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, user) -> str:
        return person_name(user)


class LeaveRequestSerializer(serializers.ModelSerializer):
    """The LeaveRequest wire type (frontend lib/services/types.ts)."""

    employee = EmployeeRefSerializer(read_only=True)
    reviewed_by = PersonRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "employee",
            "leave_type",
            "start_date",
            "end_date",
            "working_days",
            "reason",
            "status",
            "created_at",
            "updated_at",
            "reviewed_by",
            "reviewed_at",
            "review_remarks",
            "cancelled_at",
        ]
        read_only_fields = fields


class LeaveRequestCreateSerializer(serializers.Serializer):
    leave_type = serializers.ChoiceField(choices=LeaveType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(max_length=REASON_MAX_LENGTH)
    client_request_id = serializers.UUIDField()


class LeavePreviewSerializer(serializers.Serializer):
    leave_type = serializers.ChoiceField(choices=LeaveType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
