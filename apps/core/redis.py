import os

import redis.asyncio as aioredis


def get_redis() -> aioredis.Redis:
    return aioredis.Redis(
        host=os.environ.get('REDIS_HOST', 'redis'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=2,
        decode_responses=True,
    )



redis_client = get_redis()
