"""Minimal Django settings for running brevo_analytics tests standalone."""

import os

SECRET_KEY = 'test-secret-key-for-brevo-analytics'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# PostgreSQL, to exercise the JSON queries SQLite does not support:
# TEST_DB=postgres PGHOST=localhost PGPORT=5432 PGUSER=... PGPASSWORD=... python runtests.py
if os.environ.get('TEST_DB') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('PGDATABASE', 'brevo_analytics'),
            'USER': os.environ.get('PGUSER', 'postgres'),
            'PASSWORD': os.environ.get('PGPASSWORD', ''),
            'HOST': os.environ.get('PGHOST', 'localhost'),
            'PORT': os.environ.get('PGPORT', '5432'),
        }
    }

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin',
    'rest_framework',
    'corsheaders',
    'brevo_analytics',
]

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ROOT_URLCONF = 'test_urls'

BREVO_ANALYTICS = {
    'ALLOWED_SENDERS': [],
    'EXCLUDED_RECIPIENT_DOMAINS': [],
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Hashing veloce: i test che creano superutenti non devono costare secondi
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
