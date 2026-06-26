# Quickstart: Authentication Email Verification

## Prerequisites

1. Running PostgreSQL database (`docker-compose up -d db`)
2. Running Redis instance (`docker-compose up -d redis`)
3. Mailjet API credentials in `.env`:
   ```
   MAILJET_API_KEY=your_api_key
   MAILJET_API_SECRET=your_api_secret
   MAILJET_SENDER_EMAIL=noreply@yourdomain.com
   ```
4. Optional: Configure `EMAIL_VERIFICATION_TIMEOUT` in minutes (default: 10)

## Setup

```bash
# Install dependencies
uv sync

# Run migrations
python manage.py migrate

# Start Celery worker (separate terminal)
celery -A config worker -l info

# Start dev server (separate terminal)
python manage.py runserver
```

## End-to-End Validation

### 1. Register a new account

```bash
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "TestPass123"}'
```

Expected: 201 Created with user id, email, and message.

### 2. Login before verification (should fail)

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "TestPass123"}'
```

Expected: 401 Unauthorized ("Invalid credentials.")

### 3. Verify email

Check the Celery worker output for the verification code (printed to stdout in dev mode), or retrieve it from the database:

```bash
python manage.py shell -c "
from apps.accounts.models import EmailVerificationToken
token = EmailVerificationToken.objects.latest('created_at')
print(f'Code for {token.user.email}: {token.plaintext_code}')
"
```

```bash
curl -X POST http://localhost:8000/api/accounts/verify-email/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "code": "123456"}'
```

Expected: 200 OK ("Email verified successfully.")

### 4. Login after verification

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "TestPass123"}'
```

Expected: 200 OK with `access`, `refresh`, and `user` object.

### 5. Change password while authenticated

```bash
curl -X POST http://localhost:8000/api/accounts/change-password/ \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access_token>' \
  -d '{"current_password": "TestPass123", "new_password": "NewPass456"}'
```

Expected: 200 OK.

### 6. Login with new password

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "NewPass456"}'
```

Expected: 200 OK.

### 7. Request password reset

```bash
curl -X POST http://localhost:8000/api/accounts/password-reset-request/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com"}'
```

Expected: 200 OK (message says email sent if account exists).

### 8. Re-register verified account (should fail)

```bash
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "SomePass123"}'
```

Expected: 409 Conflict ("An account with this email already exists.")

### 9. Re-register unverified account (should override)

```bash
# Register new unverified account
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "override@example.com", "password": "FirstPass1"}'

# Re-register same email (overrides)
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email": "override@example.com", "password": "SecondPass2"}'
```

Expected: Both return 201. The second call overrides the first. Only the second password and verification code work.

## Running Tests

```bash
# Run all tests
pytest apps/accounts/tests/ -v

# Run just account service tests
pytest apps/accounts/tests/test_account_service.py -v

# Run with type checking
mypy apps/accounts/ --strict
ruff check apps/accounts/
```
