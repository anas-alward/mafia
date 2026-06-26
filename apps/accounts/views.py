"""Account REST endpoints: register, verify, login, reset, change password."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from utils.errors import api_error, api_validation_error

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)
from .services.account import AccountService

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        try:
            result = AccountService().register(**serializer.validated_data)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_409_CONFLICT)

        user: Any = result['user']
        return Response({
            'id': user.id,
            'email': user.email,
            'message': 'Account created. Please verify your email.',
        }, status=status.HTTP_201_CREATED)


class VerifyEmailView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VerifyEmailSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        try:
            AccountService().verify_email(**serializer.validated_data)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {'message': 'Email verified successfully.'},
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ResendVerificationSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        AccountService().resend_verification(**serializer.validated_data)

        return Response({
            'message': 'If an unverified account with this email exists, '
                       'a new verification code has been sent.',
        }, status=status.HTTP_200_OK)


class LoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        try:
            result = AccountService().login(**serializer.validated_data)
        except ValueError:
            return api_error(
                'Invalid credentials.',
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response({
            'access': result['access'],
            'refresh': result['refresh'],
            'user': result['user'],
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        AccountService().request_password_reset(**serializer.validated_data)

        return Response({
            'message': 'If an account with this email exists, '
                       'a password reset email has been sent.',
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        try:
            AccountService().confirm_password_reset(**serializer.validated_data)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Password has been reset successfully.',
        }, status=status.HTTP_200_OK)


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        try:
            AccountService().change_password(
                user=request.user,
                **serializer.validated_data,
            )
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Password changed successfully.',
        }, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return api_error(
                'refresh token is required.',
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            AccountService().logout(refresh_token)
        except Exception:
            return api_error(
                'Invalid or expired token.',
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({}, status=status.HTTP_200_OK)


class TokenRefreshView(SimpleJWTTokenRefreshView):
    pass
