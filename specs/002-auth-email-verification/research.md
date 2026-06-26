# Research: Authentication Email Verification

## 1. Celery Integration with Django 6.0

**Decision**: Use Celery 5.x with Redis as both broker and result backend.

**Rationale**: Redis is already in the stack for Django Channels. Celery is the most mature task queue for Django. Using Redis as broker eliminates the need for a separate RabbitMQ deployment.

**Alternatives considered**:
- **Django Q2**: Less mature, smaller community.
- **Huey**: Lighter weight but lacks the monitoring/observability tools Celery provides.
- **RQ**: Simpler but Celery has better Django integration and periodic task support.

**Key config**:
```python
# config/celery.py
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "redis://redis:6379/0"
```

## 2. Mailjet Email Provider Integration

**Decision**: Use `mailjet-rest` Python package (Mailjet's official v3 API wrapper) for transactional email.

**Rationale**: The user specified Mailjet as the provider. The `mailjet-rest` package provides a clean Python interface. All email sending is wrapped in a common `EmailService` class so the underlying provider can be swapped without changing business logic.

**Alternatives considered**:
- **SMTP relay**: Simpler setup but slower (synchronous SMTP handshake) and lacks Mailjet's deliverability analytics.
- **django-anymail**: Provides a unified interface for multiple ESPs but adds an unnecessary abstraction layer when we're committed to Mailjet.

**Configuration**:
```python
MAILJET_API_KEY = env("MAILJET_API_KEY")
MAILJET_API_SECRET = env("MAILJET_API_SECRET")
MAILJET_SENDER_EMAIL = env("MAILJET_SENDER_EMAIL", "noreply@mafia.game")
```

## 3. Email Verification Feature Flag

**Decision**: Add a configurable setting `EMAIL_VERIFICATION_ENABLED` (default `True`). When `True`, real verification is enforced: codes are validated against stored hashes with expiry, and verification emails are sent via Celery tasks. When `False` (development/testing mode), any submitted code is accepted and the account is verified immediately with no email sent.

**Rationale**: Per user instruction. This allows development and testing without requiring working email infrastructure (Mailjet credentials, Celery worker). The feature flag is a Django setting, so it can be set per environment.

**Implementation**: In `EmailVerificationService.validate_code()`, check `settings.EMAIL_VERIFICATION_ENABLED` first. If `False`, return success immediately. In `EmailService.send_verification_email()`, if verification is disabled, return immediately without calling Mailjet/Celery. The verify-email endpoint and register flow reference these service methods, so the flag gates behavior transparently.

**Edge cases**: When OFF, no verification token is created/stored in the database (the code is never needed). Registration can skip the Celery task dispatch entirely.

## 4. Email Verification Token Strategy

**Decision**: Generate a cryptographically random 6-digit numeric code, hash it with Django's password hasher for storage, and send it via email. Token expiry is configurable via `settings.EMAIL_VERIFICATION_TIMEOUT` (default: 10 minutes / 600 seconds).

**Rationale**: The user requested a code-based verification endpoint (`/verify-email/` receives email + code) with configurable expiry. A short numeric code is user-friendly for manual entry if needed. Hashing the code prevents database exposure risks. The expiry is a `timedelta` in settings so it can be changed without code changes.

**Alternatives considered**:
- **JWT-based verification links**: More common for "click link to verify" flows, but the user explicitly wants a code-based endpoint.
- **UUID tokens**: Harder for users to copy/paste or transcribe; the code approach supports both link and manual entry flows.

**Token lifecycle**:
1. On registration → generate code, hash it, store with user + expiry
2. Send code via email (Celery task)
3. On re-registration of unverified account → delete old hashed code, generate new one, send new email
4. POST `/verify-email/` with email + code → validate against stored hash + expiry
5. On success → set user as verified, delete token

## 5. Login by Email Instead of Username

**Decision**: Use Django `authenticate()` with `username=email` by configuring a custom authentication backend that authenticates against the email field.

**Rationale**: SimpleJWT and Django's `authenticate()` rely on `username` as the identifier. A custom authentication backend that maps `username` → email lookup is the idiomatic Django approach. This avoids modifying SimpleJWT internals.

**Implementation**:
```python
# apps/accounts/services/account.py
class EmailAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(email__iexact=username.lower())
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
```

Add `AUTHENTICATION_BACKENDS = ['apps.accounts.services.account.EmailAuthBackend']` to settings.

## 6. Unverified Account Handling

**Decision**: Login query filters to verified-only users. Unverified accounts are skipped entirely. Re-registration with an existing unverified email updates the existing row (new password, new token, new expiry).

**Rationale**: Per spec: unverified accounts are "treated as not registered" during login. The simplest approach is to filter `is_verified=True` in the auth backend and to do an `update_or_create` in the register flow based on email.

**Edge cases handled**:
- Expired unverified account → re-register → old record updated
- Login with unverified credentials → same generic error as invalid credentials
- Verified account re-registration → rejected with "email already in use"

## 7. User Object Returned on Login

**Decision**: Extend the existing login response to include a serialized user object under a `user` key alongside `access` and `refresh`.

**Rationale**: Spec FR-008 requires this. The user object includes `id`, `email`, `display_name` (or `username` fallback), and excludes sensitive fields (password hash, is_staff, etc.). This is handled in the serializer layer per Constitution §III.

## 8. Celery Task for Email Sending

**Decision**: All calls to `EmailService.send_*()` are wrapped in Celery tasks defined in `apps/accounts/tasks/email_tasks.py`. HTTP endpoints call `send_verification_email.delay(user_id)` and return immediately.

**Rationale**: Per user instruction: email sending must be a background task. This prevents slow or failing SMTP calls from blocking HTTP responses. Celery tasks include automatic retry with exponential backoff (max 3 retries, starting at 10s).

**Task definitions**:
- `send_verification_email(user_id: int) → None`
- `send_password_reset_email(user_id: int) → None`
