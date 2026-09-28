from rest_framework import serializers

from .models import MAX_ALLOWANCE_DAYS, MAX_YEAR, MIN_YEAR


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
