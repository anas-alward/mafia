import redis.asyncio as aioredis
from django.conf import settings


def get_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


redis_client = get_redis()
