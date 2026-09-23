from django.contrib.auth import get_user_model
from rest_framework import serializers

from .roles import get_role


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "email", "first_name", "last_name", "role"]
        read_only_fields = fields

    def get_role(self, user) -> str:
        return get_role(user).value
