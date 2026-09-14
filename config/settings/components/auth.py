from datetime import timedelta

from ..env import env

AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.services.account.EmailAuthBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

PASSWORD_RESET_TIMEOUT = timedelta(hours=1)

# Email verification — when ON, register() generates an OTP code and emails it.
EMAIL_VERIFICATION_ENABLED = env.bool('EMAIL_VERIFICATION_ENABLED', default=True)
EMAIL_VERIFICATION_TIMEOUT = timedelta(
    minutes=env.int('EMAIL_VERIFICATION_TIMEOUT_MINUTES', default=10)
)

FRONTEND_URL = env.str('FRONTEND_URL', default='http://localhost:5173').rstrip('/')
