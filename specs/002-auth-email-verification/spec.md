# Feature Specification: Authentication Email Verification

**Feature Branch**: `feat/authentication`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "complete authentication, we want to update the authentication process, creating account should require email and then require verification, and we will verify it by email, and registering, and login email instead of username, and when login return also user object, and also we need reset password and change password"

## Clarifications

### Session 2026-06-26

- Q: How long should the verification window be, and what happens to unverified accounts after expiry? → A: Verification tokens expire after 10 minutes. Unverified accounts are treated as not registered for login purposes (login always filters out unverified), but the record is kept. Re-registering with the same unverified email overrides the existing unverified record. Once verified, the account is permanent and cannot be re-registered.
- Q: Should email verification be gated by a feature flag? → A: Yes. A configurable flag controls whether real email verification is enforced. When ON, verification codes are validated against stored hashes. When OFF, any submitted code is accepted and the account is verified immediately. This allows development/testing without email infrastructure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register Account with Email Verification (Priority: P1)

A new player wants to join the game. They provide an email address and password to create an account. The system creates the account in an unverified state and sends a verification email with a link valid for 10 minutes. The player must click the link within that window to verify and activate their account. If the window expires, the account is treated as non-existent for login purposes — but the record is kept. If the player registers again with the same email before verifying, the old unverified record is overridden with the new credentials and a fresh 10-minute verification window begins. Once verified, the account is permanent and the email can never be used for another registration.

**Why this priority**: Registration is the entry point for all users. Email verification ensures only valid email owners can create accounts, preventing spam and ensuring password reset can work later. This is the foundational flow upon which all other auth features depend.

**Independent Test**: Can be fully tested by submitting a registration form, receiving a verification email, and clicking the verification link within 10 minutes to activate the account. Can also test re-registration override by registering, ignoring the verification, then re-registering with the same email. Delivers value of a working user onboarding flow.

**Acceptance Scenarios**:

1. **Given** a new player with a valid email address not yet registered, **When** they submit the registration form with email and password, **Then** an account is created in unverified state and a verification email is sent.
2. **Given** a player with an unverified account, **When** they click the verification link within the 10-minute window, **Then** their account is verified and they can log in.
3. **Given** a player with an existing unverified account, **When** they register again with the same email, **Then** the old unverified record is overridden (new password, new verification token) and a fresh verification email is sent.
4. **Given** a player with a verified account, **When** they or anyone else attempts to register with the same email, **Then** the system rejects the registration with a message that the email is already in use.
5. **Given** a player with an unverified account whose verification window has expired, **When** they attempt to log in, **Then** the system treats the account as not registered (generic "invalid credentials" response, no mention of verification).
6. **Given** a player with an expired or invalid verification token, **When** they click the verification link, **Then** the system shows an error indicating the link has expired and directs them to register again.
7. **Given** a player who just registered, **When** they do not receive the verification email, **Then** they can request a new verification email to be sent (which resets the 10-minute window).
8. **Given** email verification is turned OFF (development mode), **When** a player submits any verification code (correct or not), **Then** the account is verified immediately and no email is sent.

---

### User Story 2 - Login with Email (Priority: P2)

A registered and verified player wants to access their account. They provide their email and password. On successful authentication, the system returns an access token along with the user's profile object (email, display name, and other non-sensitive fields).

**Why this priority**: Login is the second half of the auth flow. Moving from username to email simplifies the mental model for users (one less identifier to remember). Returning the user object on login avoids a separate API call to fetch profile data.

**Independent Test**: Can be fully tested by providing valid email+password credentials and receiving an auth token with user object. Delivers value of authenticated access to the application.

**Acceptance Scenarios**:

1. **Given** a verified user with correct credentials, **When** they log in with email and password, **Then** they receive an access token and the user object (email, display name, id, etc.).
2. **Given** a player entering wrong credentials, **When** they submit the login form, **Then** the system rejects the login with a generic error message that does not reveal whether the email exists.
3. **Given** a player logging in with an unverified account, **When** they submit valid credentials, **Then** the system rejects the login with a generic error (same as unknown email), treating the account as not registered.
4. **Given** an authenticated user, **When** they access a protected resource with their token, **Then** the system grants access.

---

### User Story 3 - Reset Forgotten Password (Priority: P3)

A player has forgotten their password and cannot log in. They request a password reset by providing their email address. The system sends a reset link to their email. They click the link, enter a new password, and regain access to their account.

**Why this priority**: Password recovery is essential for user retention but is needed less frequently than registration or login. It depends on the email infrastructure established by the verification flow.

**Independent Test**: Can be fully tested by requesting a password reset for a registered email, receiving the reset email, clicking the link, and setting a new password. Delivers value of account recovery.

**Acceptance Scenarios**:

1. **Given** a player with a verified account, **When** they request a password reset by submitting their email, **Then** a reset email is sent and the system confirms the email was sent (without revealing whether the email exists in the system).
2. **Given** a player who received a valid reset email, **When** they click the reset link and submit a new password, **Then** their password is updated and they can log in with the new password.
3. **Given** a player clicking an expired or invalid reset link, **When** they attempt to set a new password, **Then** the system rejects the attempt and offers to request a new reset link.
4. **Given** a player who requested a reset, **When** they use the same reset link more than once, **Then** the second and subsequent uses are rejected.

---

### User Story 4 - Change Password While Authenticated (Priority: P4)

An authenticated player wants to change their password for security reasons. They provide their current password and a new password. The system verifies the current password and updates to the new one.

**Why this priority**: Password change is a standard account management feature but requires prior authentication, making it dependent on the login flow. It is less critical than core registration, login, and recovery flows.

**Independent Test**: Can be fully tested by an authenticated user submitting their current password and a new password, then verifying the new password works for subsequent logins. Delivers value of account security management.

**Acceptance Scenarios**:

1. **Given** an authenticated player, **When** they submit their correct current password and a valid new password, **Then** their password is updated and they must use the new password for future logins.
2. **Given** an authenticated player, **When** they submit an incorrect current password, **Then** the system rejects the change with an appropriate error.
3. **Given** an unauthenticated user, **When** they attempt to change a password, **Then** the system rejects the request with an authentication error.

---

### Edge Cases

- What happens when a user registers with an email that is already registered but unverified? The old unverified record is overridden (new password, new verification token) and a fresh verification email is sent.
- What happens when a user registers with an email that is already verified? The system rejects the registration — verified accounts are permanent and the email cannot be reclaimed.
- What happens when the email sending service is unavailable during registration? The system should create the account but inform the user that the verification email could not be sent and offer retry.
- What happens when a verification or reset token is used by someone other than the intended recipient? Tokens must be single-use and time-limited.
- What happens during concurrent password change and password reset requests? The most recent valid action should take precedence.
- How does the system handle email addresses with different casing (User@Example.com vs user@example.com)? Email addresses should be treated as case-insensitive and normalized to lowercase.
- What happens when a user's email provider blocks or delays the verification email? The user should request a new verification email, which resends the email and resets the 10-minute window.
- What happens to unverified accounts whose verification window expired? The account record persists, but for all user-facing purposes (login, password reset) it is treated as non-existent. Re-registering with the same email overrides the stale record.
- What happens when the email verification feature flag is OFF? The system skips email sending entirely on registration. The verify-email endpoint accepts any code (valid or not) and immediately activates the account. This mode is intended for development and testing.
- What happens when the email verification feature flag is ON? Full verification is enforced — codes are validated against stored hashes with expiry. Emails are sent via the email service.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST require a valid email address and password for account registration.
- **FR-002**: System MUST validate email format and enforce minimum password strength requirements during registration.
- **FR-003**: System MUST send a verification email containing a unique, single-use verification link upon registration, expiring after 10 minutes.
- **FR-004**: System MUST keep newly registered accounts in an unverified state that prevents login.
- **FR-005**: System MUST support a configurable email verification mode. When verification is ON, the system MUST validate submitted codes against stored hashed codes with expiry. When verification is OFF, the system MUST accept any submitted code and verify the account immediately.
- **FR-006**: System MUST allow users to request a new verification email, which resends the email and resets the 10-minute verification window.
- **FR-007**: System MUST accept email (instead of username) as the login identifier.
- **FR-008**: System MUST return the authenticated user's profile object (non-sensitive fields) alongside the access token on successful login.
- **FR-009**: System MUST treat unverified accounts as non-existent during login — returning the same generic error as for unknown emails, with no indication that the email was registered.
- **FR-010**: System MUST provide a password reset flow: user submits email, system sends a time-limited reset link, user sets a new password via that link. Only verified accounts can complete password reset.
- **FR-011**: System MUST allow authenticated users to change their password by providing their current password and a new password.
- **FR-012**: System MUST treat email addresses as case-insensitive, normalizing them to lowercase for storage and lookup.
- **FR-013**: System MUST make verification and password reset tokens single-use. Verification tokens expire after 10 minutes; password reset tokens expire after 1 hour.
- **FR-014**: System MUST NOT reveal whether an email address is registered in the system during login or password reset flows (consistent generic responses).
- **FR-015**: System MUST override an existing unverified account record (new password, new verification token, new expiry) when a registration is submitted with the same email.
- **FR-016**: System MUST reject registration attempts for emails that belong to verified accounts.

### Key Entities

- **User**: Represents a player account. Key attributes: email (unique, normalized), password hash, verification status (unverified or verified), and profile fields (display name). Lifecycle: created in unverified state on registration; transitions to verified (permanent) upon email confirmation within 10 minutes. Unverified records can be overridden by re-registration; verified records are immutable and cannot be re-registered.
- **Email Verification Token**: A single-use token expiring after 10 minutes, associated with an unverified user. Used to confirm email ownership during registration. Resent on resend-verification request, which replaces the previous token.
- **Password Reset Token**: A single-use token expiring after 1 hour, associated with a verified user. Used to authorize a password change without knowing the current password.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can complete the full registration and email verification flow in under 3 minutes under normal email delivery conditions.
- **SC-002**: A verified user can log in with email and password in under 2 seconds.
- **SC-003**: A user can complete a password reset in under 3 minutes from request to successful login with the new password.
- **SC-004**: 95% of verification and reset emails are delivered within 30 seconds of the triggering action.
- **SC-005**: Account security incidents (unauthorized access due to token reuse or expired token exploitation) are zero.
- **SC-006**: Login with email reduces user confusion compared to username-based login, measured by fewer support inquiries related to forgotten identifiers.

## Assumptions

- Email verification is controlled by a configurable feature flag (`EMAIL_VERIFICATION_ENABLED`). Default is ON in production, OFF in development/testing. When OFF, any code is accepted and no emails are sent.
- Existing email sending infrastructure is available or will be set up as part of this feature (SMTP service or email API provider).
- Verification tokens expire after 10 minutes; password reset tokens expire after 1 hour.
- Password minimum strength: at least 8 characters with a mix of character types.
- The existing authentication system will be extended rather than replaced.
- Users have access to their email inbox and can click web links. Alternative verification methods (SMS, magic links) are out of scope for this feature.
- The user object returned on login excludes sensitive fields (password hash, internal IDs that should not be exposed).
- Unverified accounts that exceed the 10-minute verification window remain in storage but are treated as non-existent for all user-facing operations (login, password reset). Re-registering with the same email overrides the stale unverified record.
- Verified accounts are permanent and cannot be deleted or overridden through the registration flow.
