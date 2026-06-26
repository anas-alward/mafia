# API Contracts: Authentication Email Verification

Base URL: `/api/accounts/`

## POST /register/

Register a new account. Creates an unverified user and sends verification email.

**Request**:
```json
{
  "email": "player@example.com",
  "password": "securePassword123"
}
```

**Response 201**:
```json
{
  "id": 1,
  "email": "player@example.com",
  "message": "Account created. Please verify your email."
}
```

**Response 400**:
```json
{
  "error": "Validation failed.",
  "details": {
    "email": ["This field is required."],
    "password": ["Password must be at least 8 characters."]
  }
}
```

**Response 409** (email already verified):
```json
{
  "error": "An account with this email already exists."
}
```

**Re-registration behavior**: If an unverified account with the same email exists, it is overridden (new password, new verification code, new expiry). Response is identical to 201.

---

## POST /verify-email/

Verify an email address with the code sent after registration.

**Request**:
```json
{
  "email": "player@example.com",
  "code": "123456"
}
```

**Response 200**:
```json
{
  "message": "Email verified successfully."
}
```

**Response 400** (expired or invalid):
```json
{
  "error": "Invalid or expired verification code."
}
```

**Response 404** (no registration found):
```json
{
  "error": "No pending verification found for this email."
}
```

---

## POST /resend-verification/

Request a new verification code (resets the 10-minute window).

**Request**:
```json
{
  "email": "player@example.com"
}
```

**Response 200** (always, to avoid revealing account state):
```json
{
  "message": "If an unverified account with this email exists, a new verification code has been sent."
}
```

---

## POST /login/

Authenticate with email and password. Only verified accounts can log in.

**Request**:
```json
{
  "email": "player@example.com",
  "password": "securePassword123"
}
```

**Response 200**:
```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": {
    "id": 1,
    "email": "player@example.com",
    "username": "player"
  }
}
```

**Response 401** (invalid credentials or unverified account):
```json
{
  "error": "Invalid credentials."
}
```

---

## POST /password-reset-request/

Request a password reset link. Only works for verified accounts.

**Request**:
```json
{
  "email": "player@example.com"
}
```

**Response 200** (always, to avoid revealing account state):
```json
{
  "message": "If an account with this email exists, a password reset email has been sent."
}
```

---

## POST /password-reset-confirm/

Set a new password using the reset token.

**Request**:
```json
{
  "email": "player@example.com",
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "new_password": "newSecurePassword456"
}
```

**Response 200**:
```json
{
  "message": "Password has been reset successfully."
}
```

**Response 400** (expired/invalid token):
```json
{
  "error": "Invalid or expired reset token."
}
```

---

## POST /change-password/

Change password while authenticated. Requires current password.

**Authorization**: Bearer \<access_token\>

**Request**:
```json
{
  "current_password": "oldPassword",
  "new_password": "newSecurePassword456"
}
```

**Response 200**:
```json
{
  "message": "Password changed successfully."
}
```

**Response 400** (wrong current password):
```json
{
  "error": "Current password is incorrect."
}
```

**Response 401** (unauthenticated):
```json
{
  "error": "Authentication credentials were not provided."
}
```

---

## POST /token/refresh/

Refresh an expired access token (unchanged from existing SimpleJWT behavior).

**Request**:
```json
{
  "refresh": "eyJ..."
}
```

**Response 200**:
```json
{
  "access": "eyJ..."
}
```

---

## POST /logout/

Blacklist a refresh token (unchanged from existing behavior).

**Authorization**: Bearer \<access_token\>

**Request**:
```json
{
  "refresh": "eyJ..."
}
```

**Response 200**: `{}`
