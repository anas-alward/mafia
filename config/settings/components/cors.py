from ..env import env

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS')

CORS_ALLOW_CREDENTIALS = env.bool(
    'CORS_ALLOW_CREDENTIALS',
    default=True,
)

