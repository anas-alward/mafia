APPS = [
    'apps.accounts',
    'apps.room',
    'apps.game',
    'apps.friends',
]
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
    'rest_framework_simplejwt.token_blacklist',
] + APPS
