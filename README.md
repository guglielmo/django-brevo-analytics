# Django Brevo Analytics

A reusable Django package that integrates transactional email analytics from Brevo (via Supabase) into Django admin.

![Dashboard Preview](docs/images/dashboard.png)

## Features

- **Dashboard**: Delivery health metrics with sparklines (total sent, delivery rate, bounce rate, avg delivery time)
- **Email List**: Searchable, sortable table with date filtering
- **Email Detail**: Full event timeline with bounce reason analysis
- **Read-Only**: Secure, read-only access to external Supabase data
- **Cache-Resilient**: Graceful fallback to cached data when API is unavailable
- **RLS Security**: Client isolation via Supabase Row Level Security
- **Admin Integration**: Native Django admin navigation and permissions

## Requirements

- Python 3.8+
- Django 4.2+
- Supabase project with required schema
- JWT token with `client_id` claim

## Installation

```bash
pip install django-brevo-analytics
```

See [Installation Guide](docs/INSTALLATION.md) for detailed setup instructions.

## Quick Start

1. Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'brevo_analytics',
]
```

2. Configure Supabase connection:

```python
BREVO_ANALYTICS = {
    'SUPABASE_URL': 'https://your-project.supabase.co',
    'JWT': 'your-jwt-token',  # Must include client_id claim
    'CACHE_TIMEOUT': 300,     # Optional, defaults to 5 minutes
    'RETENTION_DAYS': 60,      # Optional, defaults to 60 days
}
```

3. Access analytics at `/admin/brevo-analytics/` (requires staff permissions)

## Supabase Setup

See [Supabase Setup Guide](docs/SUPABASE_SETUP.md) for:
- Database schema (tables, RLS policies)
- JWT generation with client_id claim

## Data Synchronization

Brevo email and event data must be synced to Supabase before it appears in the dashboard. See [n8n Workflow Design](docs/n8n-workflow-design.md) for complete implementation guide covering:

**Webhook Strategy (Recommended):**
- Real-time event processing via Brevo webhooks
- Lower API usage and minimal latency
- Automatic event capture as they occur

**Polling Strategy (Alternative):**
- Periodic fetching from Brevo API
- Historical data recovery support
- Incremental sync with state tracking

The workflow handles:
- Email record creation from Brevo transactional emails
- Event capture (sent, delivered, opened, clicked, bounced, etc.)
- Field mapping and transformation
- Duplicate prevention and upserts

## Configuration

### Required Settings

- `SUPABASE_URL`: Your Supabase project URL
- `JWT`: JWT token with `client_id` claim for RLS

### Optional Settings

- `CACHE_TIMEOUT`: Cache duration in seconds (default: 300)
- `RETENTION_DAYS`: Data retention period (default: 60)

### Django Cache

This package uses Django's cache framework. Configure a cache backend in settings:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

See [Django cache documentation](https://docs.djangoproject.com/en/4.2/topics/cache/) for other backends.

## Usage

### Dashboard

Access `/admin/brevo-analytics/` to view:
- Total emails sent
- Delivery rate percentage
- Bounce rate percentage
- Average delivery time
- Sparkline trends for each metric

Filter by date range: Last 24 hours, 7 days, 30 days, or 90 days.

### Email List

Click "View All Emails" or navigate to `/admin/brevo-analytics/emails/` to:
- Search by recipient email or subject
- Sort by any column
- Filter by date range
- View current status (sent/delivered/opened/clicked/bounced)

### Email Detail

Click any email row to view:
- Full email metadata
- Chronological event timeline
- Bounce details (type and reason) for troubleshooting

## Architecture

### Virtual Model Pattern

This package uses a "virtual model" approach:
- Django model with `managed=False` (no database table)
- Registers with Django admin for navigation
- All data fetched from Supabase via postgrest-py

### Security

- **JWT Authentication**: All API calls use JWT with `client_id` claim
- **Row Level Security**: Supabase RLS policies enforce client isolation
- **Read-Only**: No write operations, safe for production use
- **Staff Permissions**: Django admin permissions required

### Caching Strategy

- All Supabase queries cached via Django cache framework
- Cache keys include all filter parameters
- Failed API calls fall back to cached data with warning
- Configurable cache timeout (default: 5 minutes)

## Development

### Setup

```bash
git clone https://github.com/yourusername/django-brevo-analytics.git
cd django-brevo-analytics
pip install -r requirements.txt
```

### Running Tests

```bash
pytest
```

### Building Package

```bash
python setup.py sdist bdist_wheel
```

## Troubleshooting

### "Configuration Error" message

- Verify `BREVO_ANALYTICS` settings in Django settings
- Check that `SUPABASE_URL` is valid
- Verify JWT is not expired

### "Unable to load analytics data"

- Check Supabase project is accessible
- Verify JWT has read permissions on tables
- Check RLS policies allow access
- Review Django cache configuration

### Empty dashboard

- Verify data exists in Supabase tables
- Check JWT `client_id` claim matches data
- Review date range filter (may be too restrictive)

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- Built with [Django](https://www.djangoproject.com/)
- Uses [postgrest-py](https://github.com/supabase-community/postgrest-py) for Supabase API
- Charts powered by [Chart.js](https://www.chartjs.org/)
- Tables powered by [DataTables](https://datatables.net/)

## Support

- [Documentation](docs/)
- [Issue Tracker](https://github.com/yourusername/django-brevo-analytics/issues)
- [Changelog](CHANGELOG.md)
