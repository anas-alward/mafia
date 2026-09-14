"""Django test settings - uses SQLite for testing."""

from config import settings as _base_settings
from config.settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Celery test config — run tasks synchronously, no broker needed
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'

# Cache test config — locmem, no Redis needed (prod uses RedisCache so
# throttles are shared across app/worker processes).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Email verification ON in tests (matches dev default); flag-off cases
# use explicit override_settings in individual tests.
EMAIL_VERIFICATION_ENABLED = True

# Tests assert against the locmem outbox, never the real Resend backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Generous throttle rates in tests — the whole suite shares one process-wide
# cache keyed by IP, so production limits would 429 unrelated tests.
# Dedicated throttle tests override these with tiny rates per-test.
REST_FRAMEWORK = {
    **_base_settings.REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10000/min',
        'user': '10000/min',
        'login': '1000/min',
        'register': '1000/min',
        'verify': '1000/min',
        'resend-verification': '1000/min',
        'password-reset-request': '1000/min',
        'password-reset-confirm': '1000/min',
        'token-refresh': '1000/min',
    },
}

from datetime import timedelta  # noqa: E402

EMAIL_VERIFICATION_TIMEOUT = timedelta(minutes=10)
PASSWORD_RESET_TIMEOUT = timedelta(hours=1)
