# Installation Guide

## Prerequisites

- Python 3.8 or higher
- Django 4.2 or higher
- Supabase project with required schema
- JWT token with `client_id` claim

## Step 1: Install Package

```bash
pip install django-brevo-analytics
```

Or from source:

```bash
git clone https://github.com/yourusername/django-brevo-analytics.git
cd django-brevo-analytics
pip install -e .
```

## Step 2: Add to Django Project

Edit your `settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Add brevo_analytics
    'brevo_analytics',

    # Your other apps...
]
```

## Step 3: Configure Supabase Connection

Add to `settings.py`:

```python
BREVO_ANALYTICS = {
    'SUPABASE_URL': 'https://your-project-id.supabase.co',
    'JWT': 'your-jwt-token-here',
}
```

### Getting Your Supabase URL

1. Go to your Supabase project dashboard
2. Click "Settings" → "API"
3. Copy the "Project URL"

### Generating JWT Token

See [Supabase Setup Guide](SUPABASE_SETUP.md#jwt-generation) for instructions on generating a JWT with `client_id` claim.

## Step 4: Configure Django Cache (Recommended)

For production, use Redis or Memcached:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

For development, the default cache is fine:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

## Step 5: Collect Static Files

```bash
python manage.py collectstatic
```

## Step 6: Access Admin Interface

1. Start your Django development server:

```bash
python manage.py runserver
```

2. Navigate to http://localhost:8000/admin/
3. Log in with staff credentials
4. Click "Brevo Analytics" in the sidebar

## Optional Configuration

### Cache Timeout

Default is 5 minutes. To change:

```python
BREVO_ANALYTICS = {
    # ...
    'CACHE_TIMEOUT': 600,  # 10 minutes
}
```

### Data Retention

Default is 60 days. To change:

```python
BREVO_ANALYTICS = {
    # ...
    'RETENTION_DAYS': 90,  # 90 days
}
```

## Verification

To verify installation:

1. Check admin sidebar shows "Brevo Analytics"
2. Click it - should show dashboard or configuration error
3. If configuration error, review Step 3
4. If dashboard shows, installation successful!

## Troubleshooting

### Package not found

```bash
pip list | grep brevo
```

If not listed, reinstall:

```bash
pip install --upgrade --force-reinstall django-brevo-analytics
```

### Module import errors

Clear Python cache:

```bash
find . -type d -name __pycache__ -exec rm -r {} +
python manage.py runserver
```

### Static files not loading

```bash
python manage.py collectstatic --clear --no-input
```

### Admin not showing package

Restart Django:

```bash
# Kill existing server
python manage.py runserver
```

## Next Steps

- [Supabase Setup Guide](SUPABASE_SETUP.md) - Configure database schema
- [Usage Guide](USAGE.md) - Learn how to use the interface
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
