"""Celery tasks for async email sending."""

from __future__ import annotations

from celery import shared_task

from apps.accounts.services.email import EmailService


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
)
def send_verification_email_task(
    self: object, to_email: str, code: str
) -> None:
    """Send verification email asynchronously via Celery."""
    EmailService().send_verification_email(to_email=to_email, code=code)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(Exception,),
)
def send_password_reset_email_task(
    self: object, to_email: str, reset_token: str
) -> None:
    """Send password reset email asynchronously via Celery."""
    EmailService().send_password_reset_email(
        to_email=to_email, reset_token=reset_token
    )
