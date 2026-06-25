"""Account business logic: register, login, logout."""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AccountService:
    def register(self, username: str, email: str, password: str) -> dict[str, object]:
        if User.objects.filter(username=username).exists():
            raise ValueError(f'Username "{username}" is already taken.')
        if User.objects.filter(email=email).exists():
            raise ValueError(f'Email "{email}" is already taken.')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        refresh = RefreshToken.for_user(user)
        return {
            'user': user,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }

    def login(self, username: str, password: str) -> dict[str, str]:
        user = authenticate(username=username, password=password)
        if user is None:
            raise ValueError('Invalid credentials.')
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }

    def logout(self, refresh_token: str) -> None:
        token = RefreshToken(refresh_token)
        token.blacklist()
