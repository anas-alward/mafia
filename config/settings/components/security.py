from ..env import env
from .base import DEBUG

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS')

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env.bool(
    'SECURE_SSL_REDIRECT',
    default=False,
)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
