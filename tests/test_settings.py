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

# Email verification disabled in test environment
EMAIL_VERIFICATION_ENABLED = False

from datetime import timedelta  # noqa: E402

EMAIL_VERIFICATION_TIMEOUT = timedelta(minutes=10)
PASSWORD_RESET_TIMEOUT = timedelta(hours=1)
