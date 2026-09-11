"""Django test settings - uses SQLite for testing."""

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

# Email verification ON in tests (matches dev default); flag-off cases
# use explicit override_settings in individual tests.
EMAIL_VERIFICATION_ENABLED = True

# Tests assert against the locmem outbox, never the real Resend backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

from datetime import timedelta  # noqa: E402

EMAIL_VERIFICATION_TIMEOUT = timedelta(minutes=10)
PASSWORD_RESET_TIMEOUT = timedelta(hours=1)
