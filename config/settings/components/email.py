from ..env import env

EMAIL_BACKEND = env.str('DJANGO_EMAIL_BACKEND', default='anymail.backends.resend.EmailBackend')
ANYMAIL = {
    'RESEND_API_KEY': env.str('RESEND_API_KEY', default=''),
}
DEFAULT_FROM_EMAIL = env.str('DEFAULT_FROM_EMAIL', default='noreply@mafia.game')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
