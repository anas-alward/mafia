# Tasks: Authentication Email Verification

**Input**: Design documents from `/specs/002-auth-email-verification/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: REQUIRED per constitution §I (TDD is non-negotiable). All production code must have tests written first.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new dependencies and configure project-level settings

- [x] T001 Install Celery and mailjet-rest dependencies via `uv add celery mailjet-rest`
- [x] T002 [P] Add Celery configuration in `config/celery.py` (app definition, broker URL from env, autodiscover tasks)
- [x] T003 [P] Add Mailjet and email verification settings to `config/settings.py` (MAILJET_API_KEY, MAILJET_API_SECRET, MAILJET_SENDER_EMAIL, EMAIL_VERIFICATION_TIMEOUT, EMAIL_VERIFICATION_ENABLED)
- [x] T004 [P] Update `config/settings.py` to add Celery broker/result backend, email auth backend, and apps.accounts task autodiscovery
- [x] T005 [P] Update `tests/test_settings.py` to add Celery test config (memory broker, EMAIL_VERIFICATION_ENABLED=False)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, services, and infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational (write FIRST, confirm FAIL)

- [x] T006 [P] Unit tests for EmailService in `apps/accounts/tests/test_email_service.py` (stub Mailjet client, test send_verification_email and send_password_reset_email)
- [x] T007 [P] Unit tests for TokenService in `apps/accounts/tests/test_token_service.py` (generate/validate verification code, generate/validate reset token, expiry)
- [x] T008 [P] Unit tests for User model changes in `apps/accounts/tests/test_models.py` (is_verified field, email uniqueness/normalization)

### Implementation for Foundational

- [x] T009 Create `apps/accounts/services/__init__.py` package init
- [x] T010 Add `is_verified` and `created_at` fields to User model in `apps/accounts/models.py` and generate migration
- [x] T011 [P] Implement TokenService (verification code generation/hash/validate, reset token UUID gen/hash/validate, expiry checks) in `apps/accounts/services/token.py`
- [x] T012 [P] Implement EmailService (Mailjet client wrapper, send_verification_email, send_password_reset_email, respects EMAIL_VERIFICATION_ENABLED flag) in `apps/accounts/services/email.py`
- [x] T013 Create `apps/accounts/tasks/__init__.py` package init
- [x] T014 Implement Celery email tasks (send_verification_email_task, send_password_reset_email_task with retry) in `apps/accounts/tasks/email_tasks.py`
- [x] T015 Implement custom EmailAuthBackend (authenticate by email, filter verified-only) in `apps/accounts/services/account.py` (refactor existing services.py into services/account.py)

**Checkpoint**: Foundation ready - all models, services, and infrastructure in place. User story implementation can now begin.

---

## Phase 3: User Story 1 - Register Account with Email Verification (Priority: P1) 🎯 MVP

**Goal**: Users can register with email+password, receive a verification code, and verify their email to activate the account. Unverified re-registration overrides the old record. Feature flag gates real vs development verification mode.

**Independent Test**: Register → receive code → verify email → account is active. Re-register unverified same email → old record overridden. Verified email re-registration → rejected.

### Tests for User Story 1 (write FIRST, confirm FAIL) ⚠️

- [x] T016 [P] [US1] Integration test for register + verify flow in `apps/accounts/tests/test_views.py` (register creates unverified user, verify activates it, verify with wrong/expired code fails)
- [x] T017 [P] [US1] Integration test for re-registration override in `apps/accounts/tests/test_views.py` (unverified re-register overrides, verified re-register rejected)
- [x] T018 [P] [US1] Integration test for feature flag OFF mode in `apps/accounts/tests/test_views.py` (any code accepted, no email sent)
- [x] T019 [P] [US1] Unit test for registration service in `apps/accounts/tests/test_account_service.py` (email normalization, unverified override, verified rejection)

### Implementation for User Story 1

- [x] T020 [P] [US1] Create RegisterSerializer (email required, no username field, password validation) in `apps/accounts/serializers.py`
- [x] T021 [P] [US1] Create VerifyEmailSerializer (email + code fields) in `apps/accounts/serializers.py`
- [x] T022 [US1] Implement register method in AccountService (email normalization, unified register-or-override logic, dispatch verification email task) in `apps/accounts/services/account.py`
- [x] T023 [US1] Implement verify_email method in AccountService (check EMAIL_VERIFICATION_ENABLED flag, validate code via TokenService, set is_verified=True, delete token) in `apps/accounts/services/account.py`
- [x] T024 [US1] Implement resend_verification method in AccountService (generate new code, update token, dispatch email task) in `apps/accounts/services/account.py`
- [x] T025 [US1] Update RegisterView in `apps/accounts/views.py` (use RegisterSerializer, call AccountService.register, return 201 with user data)
- [x] T026 [US1] Implement VerifyEmailView in `apps/accounts/views.py` (use VerifyEmailSerializer, call AccountService.verify_email, return 200 or appropriate error)
- [x] T027 [US1] Implement ResendVerificationView in `apps/accounts/views.py` (accept email, call AccountService.resend_verification, generic success response)
- [x] T028 [US1] Add US1 URL routes (verify-email/, resend-verification/) in `apps/accounts/urls.py`

**Checkpoint**: User Story 1 fully functional — registration with email verification works end-to-end, feature flag gates real vs. dev mode

---

## Phase 4: User Story 2 - Login with Email (Priority: P2)

**Goal**: Users log in with email (not username). Successful login returns user object alongside access/refresh tokens. Unverified accounts get the same generic error as invalid credentials.

**Independent Test**: Login with verified email+password → get access token + user object. Login with wrong email/password → 401 generic error. Login with unverified account → 401 generic error.

### Tests for User Story 2 (write FIRST, confirm FAIL) ⚠️

- [x] T029 [P] [US2] Integration test for login with email in `apps/accounts/tests/test_views.py` (verified user logs in, returns token + user object)
- [x] T030 [P] [US2] Integration test for login failure cases in `apps/accounts/tests/test_views.py` (wrong password → generic 401, unverified account → generic 401, unknown email → generic 401, no info leak)
- [x] T031 [P] [US2] Unit test for EmailAuthBackend in `apps/accounts/tests/test_account_service.py` (authenticate by email, reject unverified, case-insensitive lookup)

### Implementation for User Story 2

- [x] T032 [P] [US2] Create LoginSerializer (email + password fields, rename from username) in `apps/accounts/serializers.py`
- [x] T033 [P] [US2] Create UserSerializer (id, email, username non-sensitive fields) in `apps/accounts/serializers.py`
- [x] T034 [US2] Update login method in AccountService (use EmailAuthBackend, return tokens + serialized user) in `apps/accounts/services/account.py`
- [x] T035 [US2] Update LoginView in `apps/accounts/views.py` (use LoginSerializer, call AccountService.login, include user object in response)

**Checkpoint**: User Story 2 fully functional — email-based login with user object in response

---

## Phase 5: User Story 3 - Reset Forgotten Password (Priority: P3)

**Goal**: Users can request a password reset by email, receive a reset token, and set a new password. Only verified accounts can complete the reset flow.

**Independent Test**: Request reset for verified email → receive token → submit new password → can login with new password. Request reset for unknown email → generic success response (no info leak).

### Tests for User Story 3 (write FIRST, confirm FAIL) ⚠️

- [x] T036 [P] [US3] Integration test for password reset flow in `apps/accounts/tests/test_views.py` (request reset, confirm with valid token, login with new password)
- [x] T037 [P] [US3] Integration test for password reset failures in `apps/accounts/tests/test_views.py` (expired token rejected, single-use token rejected, unknown email generic response, unverified account generic response)

### Implementation for User Story 3

- [x] T038 [P] [US3] Create PasswordResetRequestSerializer (email field) in `apps/accounts/serializers.py`
- [x] T039 [P] [US3] Create PasswordResetConfirmSerializer (email, token, new_password fields) in `apps/accounts/serializers.py`
- [x] T040 [US3] Implement request_password_reset method in AccountService (find verified user by email, generate reset token, dispatch email task, generic response) in `apps/accounts/services/account.py`
- [x] T041 [US3] Implement confirm_password_reset method in AccountService (validate token, set new password, delete token, mark token single-use) in `apps/accounts/services/account.py`
- [x] T042 [US3] Implement PasswordResetRequestView in `apps/accounts/views.py` (accept email, generic success response always)
- [x] T043 [US3] Implement PasswordResetConfirmView in `apps/accounts/views.py` (validate email+token+new_password, update password)
- [x] T044 [US3] Add US3 URL routes (password-reset-request/, password-reset-confirm/) in `apps/accounts/urls.py`

**Checkpoint**: User Story 3 fully functional — password reset flow complete

---

## Phase 6: User Story 4 - Change Password While Authenticated (Priority: P4)

**Goal**: Authenticated users can change their password by providing their current password and a new password.

**Independent Test**: Authenticated user submits correct current password + new password → password updated, can login with new password. Wrong current password → 400 error. Unauthenticated → 401 error.

### Tests for User Story 4 (write FIRST, confirm FAIL) ⚠️

- [x] T045 [P] [US4] Integration test for change password in `apps/accounts/tests/test_views.py` (authenticated change succeeds, new password works for login)
- [x] T046 [P] [US4] Integration test for change password failures in `apps/accounts/tests/test_views.py` (wrong current password → 400, unauthenticated → 401, weak new password → 400)

### Implementation for User Story 4

- [x] T047 [P] [US4] Create ChangePasswordSerializer (current_password, new_password fields) in `apps/accounts/serializers.py`
- [x] T048 [US4] Implement change_password method in AccountService (verify current password, validate new password, save new password) in `apps/accounts/services/account.py`
- [x] T049 [US4] Implement ChangePasswordView in `apps/accounts/views.py` (requires authentication, use ChangePasswordSerializer, call AccountService.change_password)
- [x] T050 [US4] Add US4 URL route (change-password/) in `apps/accounts/urls.py`

**Checkpoint**: All four user stories independently functional — complete authentication system

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refactoring, cleanup, type compliance, and end-to-end validation

- [x] T051 Move remaining code from `apps/accounts/services.py` into `apps/accounts/services/account.py` if not already done, then remove `apps/accounts/services.py`
- [x] T052 [P] Run `ruff check apps/accounts/` and fix all violations
- [x] T053 [P] Run `mypy apps/accounts/` and fix all type errors (pre-existing errors in game/room excluded)
- [x] T054 [P] Run `ruff format apps/accounts/` for consistent formatting
- [x] T055 Run full test suite `pytest apps/accounts/tests/ -v` and ensure all pass (44/44 passing)
- [x] T056 Validate quickstart.md scenarios end-to-end (manual or scripted)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion (T001 dependencies installed) - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2)
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2). Uses EmailAuthBackend from US1 but can be tested independently with verified users
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2). Uses TokenService + EmailService from Phase 2, but independent of US1/US2
- **User Story 4 (Phase 6)**: Depends on Foundational (Phase 2). Requires authentication from US2
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Uses EmailAuthBackend defined in Phase 2, but independently testable with pre-verified users
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Uses TokenService + EmailService from Phase 2
- **User Story 4 (P4)**: Can start after US2 completes (needs authentication + login flow)

### Within Each User Story

- Tests MUST be written and confirmed FAILING before implementation (constitution §I)
- Models before services
- Services before endpoints
- Core implementation before integration

### Parallel Opportunities

- Phase 1: T002, T003, T004, T005 can all run in parallel (different sections of settings)
- Phase 2: T006, T007, T008 can run in parallel (different test files). T011, T012 can run in parallel (different service files)
- Phase 3: T016-T019 (all tests) can run in parallel. T020, T021 can run in parallel. T025-T028 are sequential
- Phase 4: T029-T031 (all tests) can run in parallel. T032, T033 can run in parallel
- Phase 5: T036, T037 can run in parallel. T038, T039 can run in parallel. T042, T043 can run in parallel
- Phase 6: T045, T046 can run in parallel
- Phase 7: T052, T053, T054 can run in parallel
- Cross-story: US1, US2, and US3 can all begin in parallel once Foundational completes

---

## Parallel Example: User Story 1

```bash
# Step 1: Write ALL failing tests in parallel
Task T016: "Integration test for register + verify flow in apps/accounts/tests/test_views.py"
Task T017: "Integration test for re-registration override in apps/accounts/tests/test_views.py"
Task T018: "Integration test for feature flag OFF mode in apps/accounts/tests/test_views.py"
Task T019: "Unit test for registration service in apps/accounts/tests/test_account_service.py"

# Step 2: Confirm all tests FAIL (red)

# Step 3: Create serializers in parallel
Task T020: "Create RegisterSerializer in apps/accounts/serializers.py"
Task T021: "Create VerifyEmailSerializer in apps/accounts/serializers.py"

# Step 4: Implement services (T022-T024 must be sequential - same file)
Task T022 → T023 → T024: AccountService register, verify_email, resend_verification

# Step 5: Implement views (T025-T027 can run in parallel)
Task T025: "Update RegisterView in apps/accounts/views.py"
Task T026: "Implement VerifyEmailView in apps/accounts/views.py"
Task T027: "Implement ResendVerificationView in apps/accounts/views.py"

# Step 6: Add URL routes
Task T028: "Add US1 URL routes in apps/accounts/urls.py"

# Step 7: Run tests — all green
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T015)
3. Complete Phase 3: User Story 1 (T016-T028)
4. **STOP and VALIDATE**: Test registration + verification independently
5. Deploy/demo if ready — users can register and verify accounts

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Register + Verify) → Test independently → MVP: users can onboard
3. Add US2 (Login with Email) → Test independently → Users can authenticate
4. Add US3 (Reset Password) → Test independently → Users can recover accounts
5. Add US4 (Change Password) → Test independently → Users can manage security
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Register + Verify)
   - Developer B: User Story 2 (Login with Email) - prepare verified test users
   - Developer C: User Story 3 (Reset Password) - uses Phase 2 token/email infra
3. US4 (Change Password) after US2 is complete
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies on incomplete [P] tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests FAIL before implementing (TDD red-green-refactor per constitution §I)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Type annotations mandatory on all functions/methods (constitution §V)
- Email verification codes are 6-digit numeric, hashed with Django password hasher
- Password reset tokens are UUID-based, hashed with Django password hasher
- `EMAIL_VERIFICATION_TIMEOUT` is a `timedelta` in settings (default: 10 minutes)
- `EMAIL_VERIFICATION_ENABLED` is a `bool` (default: True, False in test settings)
