"""Serializers for account auth endpoints."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.core.utils.validators import username_validator

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=False,
        min_length=3,
        max_length=30,
        validators=[username_validator],
    )
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        user = User.objects.filter(email=value).first()
        if user and user.is_verified:
            raise serializers.ValidationError(
                'A verified account with this email already exists.'
            )
        return value

    def validate(self, attrs):
        username = attrs.get('username')
        if username:
            email = attrs.get('email', '').lower().strip()
            taken = (
                User.objects.filter(username__iexact=username.strip())
                .exclude(email__iexact=email)
                .exists()
            )
            if taken:
                raise serializers.ValidationError({'username': 'This username is already taken.'})
        return attrs

class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(required=True, min_length=1)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'username')


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
