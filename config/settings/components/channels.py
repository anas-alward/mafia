import socket

from ..env import env

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                {
                    'host': env('REDIS_HOST'),
                    'port': env('REDIS_PORT'),
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
