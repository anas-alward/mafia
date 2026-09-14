

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Rate limiting — every endpoint is covered by the anon/user ceilings;
    # auth endpoints get stricter per-scope limits (brute-force / spam /
    # email-bombing protection). Scopes are attached via throttle_scope.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/min',
        'user': '600/min',
        'login': '10/min',
        'register': '20/hour',
        'verify': '30/hour',
        'resend-verification': '5/hour',
        'password-reset-request': '5/hour',
        'password-reset-confirm': '20/hour',
        'token-refresh': '60/hour',
    },
}
