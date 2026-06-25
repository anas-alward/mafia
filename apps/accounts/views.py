"""Account REST endpoints: register, login, logout, token refresh."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from utils.errors import api_error, api_validation_error

from .serializers import RegisterSerializer
from .services import AccountService

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
                details={k: v for k, v in serializer.errors.items()},
            )

        try:
            result = AccountService().register(**serializer.validated_data)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': result['user'].id,
            'username': result['user'].username,
            'email': result['user'].email,
            'access': result['access'],
            'refresh': result['refresh'],
        }, status=status.HTTP_201_CREATED)


class LoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        try:
            tokens = AccountService().login(username=username, password=password)
        except ValueError:
            return api_error('Invalid credentials.', status=status.HTTP_401_UNAUTHORIZED)

        return Response(tokens, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return api_error('refresh token is required.', status=status.HTTP_400_BAD_REQUEST)

        try:
            AccountService().logout(refresh_token)
        except Exception:
            return api_error('Invalid or expired token.', status=status.HTTP_400_BAD_REQUEST)

        return Response({}, status=status.HTTP_200_OK)


class TokenRefreshView(SimpleJWTTokenRefreshView):
    pass
