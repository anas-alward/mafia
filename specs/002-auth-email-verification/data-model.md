# Data Model: Authentication Email Verification

## Entity: User (extended)

Extends `django.contrib.auth.models.AbstractUser` (existing `apps.accounts.models.User`).

### New Fields

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `is_verified` | `BooleanField` | `default=False` | Becomes `True` after successful email verification. Once `True`, never reverts. |
| `created_at` | `DateTimeField` | `auto_now_add=True` | For potential cleanup of stale unverified records. |

### Existing Relevant Fields

| Field | Type | Usage |
|-------|------|-------|
| `email` | `EmailField` | Now required; normalized to lowercase; used as login identifier |
| `username` | `CharField` | Kept for Django compat and optional display name; auto-generated from email prefix on registration |
| `password` | `CharField` | Django hashed password |
| `is_active` | `BooleanField` | Default `True` (unused for verification; `is_verified` is the gate) |

### State Transitions

```
[Registration] → UNVERIFIED (is_verified=False)
                    │
                    │ email verified within 10 min window
                    ▼
                 VERIFIED (is_verified=True, permanent)
                    │
                    │ password reset / change password
                    ▼
                 VERIFIED (password updated)

UNVERIFIED + re-register → UNVERIFIED (overridden: new password, new token, new expiry)
UNVERIFIED + expiry → still UNVERIFIED but treated as non-existent for login
```

### Indexes

- `email` (unique): Normalized to lowercase via `EmailField` with unique constraint.
- `is_verified`: Composite index `(email, is_verified)` for efficient login lookups filtering verified accounts.

## Entity: EmailVerificationToken

Stores the hashed verification code with expiry.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `BigAutoField` | PK | |
| `user` | `OneToOneField(User)` | `on_delete=CASCADE` | One token per unverified user |
| `hashed_code` | `CharField(max_length=128)` | | Django password-hasher encoded 6-digit code |
| `expires_at` | `DateTimeField` | | `now() + settings.EMAIL_VERIFICATION_TIMEOUT` |
| `created_at` | `DateTimeField` | `auto_now_add=True` | |

**Lifecycle**:
1. Created on registration or re-registration (replaces previous token if exists)
2. Validated on `POST /verify-email/`
3. Deleted on successful verification
4. Re-created if user requests resend
5. Expired tokens remain until garbage-collected or overridden by re-registration

## Entity: PasswordResetToken

Stores the hashed reset code with expiry.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `BigAutoField` | PK | |
| `user` | `OneToOneField(User)` | `on_delete=CASCADE` | Only for verified users |
| `hashed_token` | `CharField(max_length=128)` | | Django password-hasher encoded UUID token |
| `expires_at` | `DateTimeField` | | `now() + timedelta(hours=1)` |
| `created_at` | `DateTimeField` | `auto_now_add=True` | |

**Lifecycle**:
1. Created when a verified user requests password reset
2. Sent via email (Celery task)
3. Validated on password reset endpoint
4. Deleted after successful password change
5. Single-use: deleted immediately after use

## Relationships

```
User (1) ←→ (1) EmailVerificationToken  [unverified users only]
User (1) ←→ (1) PasswordResetToken       [verified users only]
```

Not enforced as DB FK constraints via `OneToOneField` — this prevents orphan issues and simplifies cleanup.
