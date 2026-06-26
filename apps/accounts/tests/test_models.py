"""Unit tests for User model changes."""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User


class UserModelTests(TestCase):
    """Tests for User model verification-related fields."""

    def test_new_user_is_not_verified(self) -> None:
        """Newly created user has is_verified=False."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123',
        )
        assert user.is_verified is False

    def test_verified_user_has_is_verified_true(self) -> None:
        """Setting is_verified=True persists correctly."""
        user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='TestPass123',
            is_verified=True,
        )
        user.refresh_from_db()
        assert user.is_verified is True

    def test_created_at_is_set_automatically(self) -> None:
        """created_at is auto-set on user creation."""
        user = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='TestPass123',
        )
        assert user.created_at is not None

    def test_email_is_unique(self) -> None:
        """Duplicate emails raise integrity error."""
        User.objects.create_user(
            username='user1',
            email='duplicate@example.com',
            password='TestPass123',
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                username='user2',
                email='duplicate@example.com',
                password='TestPass456',
            )
