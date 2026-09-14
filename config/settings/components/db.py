from ..env import env

DATABASES = {
    'default': env.db_url('DATABASE_URL'),
}
