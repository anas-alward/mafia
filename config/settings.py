import socket
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import environ
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, 'django-insecure-&((l==d6wgc@i@-9mavkx^z3(^q0+dl876pddia=j!!5i#7#^2'),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    CORS_ALLOW_CREDENTIALS=(bool, True),
    DB_NAME=(str, 'mafia'),
    DB_USER=(str, 'postgres'),
    DB_PASSWORD=(str, 'postgres'),
    DB_HOST=(str, 'db'),
    DB_PORT=(str, '5432'),
    REDIS_HOST=(str, 'redis'),
    REDIS_PORT=(int, 6379),
    REDIS_PASSWORD=(str, ''),
    REDIS_DB=(int, 2),
    REDIS_URL=(str, ''),
    CELERY_BROKER_URL=(str, ''),
    CELERY_RESULT_BACKEND=(str, ''),
    EMAIL_VERIFICATION_ENABLED=(bool, True),
    EMAIL_VERIFICATION_TIMEOUT_MINUTES=(int, 10),
    FRONTEND_URL=(str, 'http://localhost:5173'),
    DEFAULT_FROM_EMAIL=(str, 'noreply@mafia.game'),
    DJANGO_EMAIL_BACKEND=(str, 'anymail.backends.resend.EmailBackend'),
    RESEND_API_KEY=(str, ''),
    LIVEKIT_URL=(str, 'ws://localhost:7880'),
    LIVEKIT_SERVER_URL=(str, 'http://livekit:7880'),
    LIVEKIT_API_KEY=(str, 'devkey'),
    LIVEKIT_API_SECRET=(str, 'devsecret'),
    SECURE_SSL_REDIRECT=(bool, False),
)

# Load .env file if present. Docker Compose also injects .env via
# `env_file`, which takes precedence (overwrite=False).
environ.Env.read_env(BASE_DIR / '.env', overwrite=False)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = [h.strip() for h in env('ALLOWED_HOSTS') if h.strip()]
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

if not DEBUG and SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('SECRET_KEY must be set to a unique value when DEBUG=False.')


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'channels',
    'anymail',
    'apps.accounts',
    'apps.room',
    'apps.game',
    'apps.friends',
    'rest_framework_simplejwt.token_blacklist',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env.str('DB_NAME', default='mafia'),
        'USER': env.str('DB_USER', default='postgres'),
        'PASSWORD': env.str('DB_PASSWORD', default='postgres'),
        'HOST': env.str('DB_HOST', default='db'),
        'PORT': env.str('DB_PORT', default='5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/
STATIC_URL = 'static/'

# Custom User model
# https://docs.djangoproject.com/en/6.0/topics/auth/customizing/#substituting-a-custom-user-model
AUTH_USER_MODEL = 'accounts.User'

# Django REST Framework
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

# Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
# Channels
# Single source of truth for Redis. REDIS_URL wins when set (e.g. managed
# Redis like Upstash/ElastiCache); otherwise built from host/port/password.
# DB layout: 0 = Celery, 1 = Channels layer, REDIS_DB (default 2) = game
# state + Django cache. Keys are already namespaced (room:, mafia:session:).
REDIS_HOST = env('REDIS_HOST')
REDIS_PORT = env('REDIS_PORT')
REDIS_PASSWORD = env('REDIS_PASSWORD')
REDIS_DB = env('REDIS_DB')


def _redis_url(db: int) -> str:
    override = env('REDIS_URL')
    if override:
        return override.rsplit('/', 1)[0] + f'/{db}' if '/' in override else override
    auth = f':{quote(REDIS_PASSWORD)}@' if REDIS_PASSWORD else ''
    return f'redis://{auth}{REDIS_HOST}:{REDIS_PORT}/{db}'


REDIS_URL = _redis_url(REDIS_DB)

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                {
                    'host': REDIS_HOST,
                    'port': REDIS_PORT,
                    'password': REDIS_PASSWORD or None,
                    'db': 1,
                    'socket_timeout': None,
                    'socket_connect_timeout': 5,
                    'socket_keepalive': True,
                    'socket_keepalive_options': {
                        socket.TCP_KEEPIDLE: 30,
                        socket.TCP_KEEPINTVL: 5,
                        socket.TCP_KEEPCNT: 3,
                    },
                    'retry_on_timeout': True,
                    'health_check_interval': 15,
                }
            ],
        },
    },
}

# Django cache on Redis (shared across app/worker processes, unlike locmem).
# Used by DRF throttling and any cache.get/set call sites.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# CORS — allow frontend origins
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=[
        'http://localhost:5173',
        'http://localhost:4173',
        'http://localhost:3000',
        'https://api-mafia.alward.dev',
        'https://mf.alward.dev',
        'https://mafia.alward.dev',
    ],
)
CORS_ALLOW_CREDENTIALS = env('CORS_ALLOW_CREDENTIALS')

# CSRF + proxy headers (app sits behind nginx handling TLS for alward.dev).
# CSRF_TRUSTED_ORIGINS must be full https:// origins; defaults to the https
# entries of CORS_ALLOWED_ORIGINS when not set explicitly.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env('CSRF_TRUSTED_ORIGINS') if o.strip()]
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [o for o in CORS_ALLOWED_ORIGINS if o.startswith('https://')]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env('SECURE_SSL_REDIRECT')
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# Celery — explicit URL wins, otherwise derived from the same Redis host.
CELERY_BROKER_URL = env('CELERY_BROKER_URL') or _redis_url(0)
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND') or _redis_url(0)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_ALWAYS_EAGER = False

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'apps.accounts.services.account.EmailAuthBackend',
]

# Email verification — when ON, register() generates an OTP code and emails it.
EMAIL_VERIFICATION_ENABLED = env.bool('EMAIL_VERIFICATION_ENABLED', default=True)
EMAIL_VERIFICATION_TIMEOUT = timedelta(
    minutes=env.int('EMAIL_VERIFICATION_TIMEOUT_MINUTES', default=10)
)
PASSWORD_RESET_TIMEOUT = timedelta(hours=1)

# Email (Django-Anymail + Resend)
# https://anymail.dev/en/stable/esps/resend/
EMAIL_BACKEND = env.str('DJANGO_EMAIL_BACKEND', default='anymail.backends.resend.EmailBackend')
ANYMAIL = {
    'RESEND_API_KEY': env.str('RESEND_API_KEY', default=''),
}
DEFAULT_FROM_EMAIL = env.str('DEFAULT_FROM_EMAIL', default='noreply@mafia.game')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Public frontend base URL — used to build links in emails (e.g. password reset).
FRONTEND_URL = env.str('FRONTEND_URL', default='http://localhost:5173').rstrip('/')

## LiveKit (WebRTC media server)
# LIVEKIT_URL is the browser-facing signaling URL, not the backend's.
LIVEKIT_URL = env.str('LIVEKIT_URL', default='ws://localhost:7880')
# Server-side RoomService API (used for voice enforcement); resolves
# inside the compose network.
LIVEKIT_SERVER_URL = env.str('LIVEKIT_SERVER_URL', default='http://livekit:7880')
LIVEKIT_API_KEY = env.str('LIVEKIT_API_KEY', default='devkey')
LIVEKIT_API_SECRET = env.str('LIVEKIT_API_SECRET', default='devsecret')
