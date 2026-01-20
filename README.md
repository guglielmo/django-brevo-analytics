# Django Brevo Analytics

A reusable Django package that integrates transactional email analytics from Brevo (via Supabase) into Django admin.

## Features

- Read-only admin interface for transactional email analytics
- Dashboard with delivery health metrics (sent, delivered, bounced, avg delivery time)
- Searchable email list with event timeline
- Detailed email view with full event history and bounce reasons
- Supabase integration with JWT authentication and RLS
- Django cache framework for resilience

## Installation

```bash
pip install django-brevo-analytics
```

## Configuration

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'brevo_analytics',
]
```

Configure Supabase connection:

```python
BREVO_ANALYTICS = {
    'SUPABASE_URL': 'https://xxx.supabase.co',
    'JWT': 'your-jwt-token',  # JWT with client_id claim
    'CACHE_TIMEOUT': 300,  # seconds (default: 5 minutes)
    'RETENTION_DAYS': 60,  # configurable data retention
}
```

## Usage

Access the analytics dashboard at `/admin/brevo-analytics/` (requires staff permissions).

## Requirements

- Django 4.2+
- Python 3.8+
- Supabase database with required schema (see documentation)

## License

MIT
