import redis.asyncio as aioredis
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_redis() -> aioredis.Redis:
    """Game-state client. Reads the centralized Redis config from settings
    (REDIS_HOST/PORT/PASSWORD/DB or REDIS_URL override)."""
    try:
        url = settings.REDIS_URL
    except ImproperlyConfigured, AttributeError:
        # Settings not configured (e.g. bare import) — fall back to env.
        import os

        return aioredis.Redis(
            host=os.environ.get('REDIS_HOST', 'redis'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            password=os.environ.get('REDIS_PASSWORD') or None,
            db=int(os.environ.get('REDIS_DB', 2)),
            decode_responses=True,
        )
    return aioredis.Redis.from_url(url, decode_responses=True)


redis_client = get_redis()
