"""Unit tests for TokenService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase, override_settings

from apps.accounts.services.token import TokenService


class TokenServiceTests(SimpleTestCase):
    """Tests for TokenService token generation and validation."""

    def test_generate_verification_code_produces_6_digit_code(self) -> None:
        """Generated verification code is a 6-digit string."""
        code = TokenService.generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_verification_code_is_random(self) -> None:
        """Consecutive calls produce different codes."""
        codes = {TokenService.generate_verification_code() for _ in range(10)}
        assert len(codes) > 1

    def test_hash_and_validate_verification_code(self) -> None:
        """Hashing a code and validating the plaintext against the hash works."""
        code = '123456'
        hashed = TokenService.hash_verification_code(code)
        assert hashed != code
        assert TokenService.validate_verification_code(code, hashed) is True

    def test_validate_verification_code_rejects_wrong_code(self) -> None:
        """Wrong plaintext code fails validation against hash."""
        hashed = TokenService.hash_verification_code('123456')
        assert TokenService.validate_verification_code('999999', hashed) is False

    def test_verification_code_is_expired_after_timeout(self) -> None:
        """Code created >10 min ago is expired."""
        now = datetime.now(UTC)
        expires_at = now - timedelta(seconds=1)  # just past
        assert TokenService.is_code_expired(expires_at) is True

    def test_verification_code_is_not_expired_within_window(self) -> None:
        """Code created <10 min ago is NOT expired."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=5)
        assert TokenService.is_code_expired(expires_at) is False

    @override_settings(EMAIL_VERIFICATION_TIMEOUT=timedelta(minutes=5))
    def test_expiry_respects_configured_timeout(self) -> None:
        """Expiry check uses EMAIL_VERIFICATION_TIMEOUT from settings."""
        now = datetime.now(UTC)
        # With 5-min timeout: 6 min old = expired
        expires_at = now - timedelta(seconds=1)
        assert TokenService.is_code_expired(expires_at) is True

    def test_generate_password_reset_token_is_uuid_format(self) -> None:
        """Reset token is a UUID-formatted string."""
        token = TokenService.generate_password_reset_token()
        parts = token.split('-')
        assert len(parts) == 5
        assert len(parts[0]) == 8

    def test_hash_and_validate_password_reset_token(self) -> None:
        """Hashing a reset token and validating plaintext works."""
        token = TokenService.generate_password_reset_token()
        hashed = TokenService.hash_password_reset_token(token)
        assert TokenService.validate_password_reset_token(token, hashed) is True

    def test_password_reset_token_is_expired_after_timeout(self) -> None:
        """Reset token >1 hour old is expired."""
        now = datetime.now(UTC)
        expires_at = now - timedelta(seconds=1)
        assert TokenService.is_reset_expired(expires_at) is True

    def test_password_reset_token_is_not_expired_within_window(self) -> None:
        """Reset token <1 hour old is NOT expired."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=30)
        assert TokenService.is_reset_expired(expires_at) is False
