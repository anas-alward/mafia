from ..env import env

CACHES = {
    'default': env.cache_url('REDIS_URL'),
}
