from django.contrib.auth import get_user_model
from rest_framework import serializers

from .password_reset import CODE_LENGTH
from .roles import get_role


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
    remember_me = serializers.BooleanField(default=False)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "email", "first_name", "last_name", "role"]
        read_only_fields = fields

    def get_role(self, user) -> str:
        return get_role(user).value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetVerifySerializer(PasswordResetRequestSerializer):
    code = serializers.RegexField(
        rf"^\d{{{CODE_LENGTH}}}$",
        error_messages={"invalid": f"Enter the {CODE_LENGTH}-digit code from the email."},
    )


class PasswordResetConfirmSerializer(PasswordResetVerifySerializer):
    new_password = serializers.CharField(
        trim_whitespace=False, max_length=128, style={"input_type": "password"}
    )
