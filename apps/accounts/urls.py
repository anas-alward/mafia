"""Account URL routing."""

from __future__ import annotations

from django.urls import path

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    TokenRefreshView,
    VerifyEmailView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path(
        'resend-verification/',
        ResendVerificationView.as_view(),
        name='resend-verification',
    ),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path(
        'password-reset-request/',
        PasswordResetRequestView.as_view(),
        name='password-reset-request',
    ),
    path(
        'password-reset-confirm/',
        PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    path(
        'change-password/',
        ChangePasswordView.as_view(),
        name='change-password',
    ),
]
