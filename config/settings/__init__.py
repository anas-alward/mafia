from split_settings.tools import include

include(
    "components/base.py",
    "components/apps.py",
    "components/middleware.py",
    "components/templates.py",
    "components/i18n.py",
    "components/security.py",
    "components/auth.py",
    "components/db.py",
    "components/redis.py",
    "components/cache.py",
    "components/celery.py",
    "components/channels.py",
    "components/drf.py",
    "components/jwt.py",
    "components/cors.py",
    "components/email.py",
    "components/livekit.py",
    "components/static.py",
)