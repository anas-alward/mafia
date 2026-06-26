# Implementation Plan: Authentication Email Verification

**Branch**: `feat/authentication` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-auth-email-verification/spec.md`

## Summary

Update the authentication system to use email instead of username for login, require email verification via a timed verification code sent through Mailjet, add password reset and change-password flows, and return the user object on login. A common email service backed by Celery handles all email sending asynchronously.

## Technical Context

**Language/Version**: Python 3.14+

**Primary Dependencies**: Django 6.0.6, Django REST Framework, SimpleJWT, Celery (new), mailjet-rest (new), Redis (already used for Channels)

**Storage**: PostgreSQL (primary), Redis (Celery broker)

**Testing**: pytest, pytest-django, pytest-asyncio

**Target Platform**: Linux server (Docker)

**Project Type**: Web service (REST API)

**Performance Goals**: Login response under 2 seconds; email sending offloaded to background tasks (non-blocking)

**Constraints**: No blocking calls during HTTP request handling; Celery tasks for all email delivery

**Scale/Scope**: Single-digit thousands of users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TDD | ✅ WILL COMPLY | Tests written first for all new services, endpoints, and model changes |
| II. Reusability | ✅ WILL COMPLY | Common email service in `apps/accounts/services/email.py`; token utilities reused for verify + reset |
| III. Separation of Concerns | ✅ WILL COMPLY | Controllers thin (views.py), business logic in services/ |
| IV. RESTful API Design | ✅ WILL COMPLY | Resource-oriented endpoints under `/api/accounts/` |
| V. Code Styling | ✅ WILL COMPLY | Full type annotations throughout; ruff + mypy strict mode |

## Project Structure

### Documentation (this feature)

```text
specs/002-auth-email-verification/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/accounts/
├── __init__.py
├── admin.py
├── apps.py
├── middleware.py           # JWT WebSocket middleware (existing)
├── models.py               # User model + new token models
├── serializers.py          # Register, Login, Verify, Reset, Change serializers
├── services/
│   ├── __init__.py
│   ├── account.py          # AccountService (refactored from services.py)
│   ├── email.py            # Common email service (Mailjet integration)
│   └── token.py            # Token generation/validation utilities
├── tasks/
│   ├── __init__.py
│   └── email_tasks.py      # Celery tasks for async email sending
├── tests/
│   ├── __init__.py
│   ├── test_account_service.py
│   ├── test_email_service.py
│   ├── test_token_service.py
│   ├── test_views.py
│   └── test_tasks.py
├── urls.py                 # Auth endpoints
└── views.py                # Controllers: Register, Login, Verify, Reset, Change

config/
├── settings.py             # Add Celery, Mailjet, EMAIL_VERIFICATION_TIMEOUT settings
├── celery.py               # Celery app configuration
└── urls.py

tests/
└── test_settings.py         # Celery test config
```

**Structure Decision**: The existing `apps/accounts/services.py` is split into a `services/` package with `account.py`, `email.py`, and `token.py` for better separation. Celery tasks live in `apps/accounts/tasks/` as shared utilities.

## Complexity Tracking

> No constitutional violations — no complexity tracking needed.
