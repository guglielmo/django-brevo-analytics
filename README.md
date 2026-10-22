# Django Brevo Analytics

A reusable Django package that integrates transactional email analytics from Brevo directly into Django admin with an interactive Vue.js interface.

## Features

### Analytics Dashboard
- **KPI Metrics**: Total emails sent, delivery rate, open rate, click rate
- **Real-time Stats**: Bounced and blocked emails count
- **Recent Messages**: Last 20 sent messages with quick access
- **Interactive Vue.js SPA**: Fast, responsive interface with modal-based navigation

### Email Tracking
- **Message-level View**: All emails grouped by message with aggregate statistics
- **Email Detail Modal**: Complete event timeline for each recipient
- **Status Filtering**: Filter by delivered, opened, clicked, bounced, blocked
- **Event Timeline**: Chronological view of all email events with metadata

### Blacklist Management
- **Check Individual Emails**: Verify if an email is in Brevo's blacklist
- **Manage Blacklist**: View and manage all blacklisted emails
- **Brevo API Integration**: Real-time synchronization with Brevo
- **Remove from Blacklist**: Unblock emails directly from the UI

### Internationalization
- **Multi-language Support**: English and Italian translations
- **Localized UI**: All interface elements respect Django's `LANGUAGE_CODE`
- **Date Formatting**: Locale-aware date and time display

### Real-time Webhook Integration
- **Instant Updates**: Process Brevo events as they occur
- **Bearer Token Authentication**: Secure webhook authentication via Authorization header
- **Auto-enrichment**: Bounce reasons automatically fetched from Brevo API

### Historical Data Import
- **CSV Import**: Import historical email data from raw Brevo logs
- **DuckDB Processing**: Efficient bulk data processing
- **Bounce Enrichment**: Automatic bounce reason lookup during import
- **Statistics Verification**: Validate data against Brevo API

## Requirements

- Python 3.8+
- Django 4.2+ (including Django 5.x)
- Django REST Framework 3.14+
- PostgreSQL (for JSONField support)

## Installation

```bash
pip install django-brevo-analytics
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'corsheaders',
    'brevo_analytics',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Add at top
    # ... other middleware
]
```

### 2. Configure Settings

```python
# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
}

# CORS (adjust for production)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

# Brevo Analytics Configuration
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret',  # From Brevo dashboard
    'API_KEY': 'your-brevo-api-key',          # Optional, for bounce enrichment
    'ALLOWED_SENDERS': [                       # Filter emails by sender
        'info@yourproject.com',
        '@yourcompany.com',                    # Domain pattern: matches any sender
    ],
}
```

### 3. Run Migrations

```bash
python manage.py migrate brevo_analytics
```

### 4. Include URLs

```python
# your_project/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('brevo-analytics/', include('brevo_analytics.urls')),  # API endpoints for Vue.js frontend
]
```

**Note:** The API endpoints are mounted at `/brevo-analytics/` to serve the Vue.js SPA. The dashboard itself is accessed through Django admin (see step 6).

### 5. Set Up Brevo Webhook

Configure webhook in Brevo dashboard:
- URL: `https://yourdomain.com/brevo-analytics/webhook/`
- Events: All transactional email events
- Add webhook secret to settings

### 6. Access Dashboard

Navigate to `/admin/brevo_analytics/brevomessage/` (requires staff permissions)

## Management Commands

### Import Historical Data

```bash
python manage.py import_brevo_logs /path/to/brevo_logs.csv
```

Options:
- `--dry-run`: Preview import without saving
- `--clear`: Clear existing data before import

### Verify Statistics

```bash
python manage.py verify_brevo_stats
```

Compares local statistics with Brevo API to ensure data accuracy.

### Recalculate Statistics

```bash
python manage.py recalculate_stats
```

Recalculates the denormalized counters of every `BrevoMessage`.

Options:
- `--message-id ID`: Recalculate a single message
- `--dirty`: Recalculate only the messages marked by the webhook in deferred mode (see [Statistics Update Mode](#statistics-update-mode))

## Architecture

### Django-Native Design
- **Models**: Data stored directly in PostgreSQL via Django ORM
- **JSONField Events**: Email events stored as JSON array for optimal performance
- **Denormalized Stats**: Pre-calculated statistics for fast queries
- **Cached Status**: Current status field for efficient filtering

### REST API
- **Django REST Framework**: 6 API endpoints for dashboard and analytics
- **Admin-Only Access**: All endpoints require Django admin permissions
- **Serialized Data**: Optimized JSON responses for Vue.js frontend

### Vue.js SPA
- **Composition API**: Modern Vue 3 with reactivity
- **Hash-based Routing**: Client-side routing without server config
- **Modal Overlays**: Email details shown in modals, no page reloads
- **Responsive Design**: Mobile-friendly interface

### Security
- **Bearer Token Webhook Authentication**: Verify webhook authenticity via Authorization header
- **Admin Permissions**: All views require Django staff access
- **CORS Protection**: Configurable CORS for API endpoints
- **SQL Injection Safe**: Django ORM prevents SQL injection

## Configuration Options

### Required

- `WEBHOOK_SECRET`: Secret key from Brevo webhook configuration

### Optional

- `API_KEY`: Brevo API key for bounce enrichment and blacklist management
- `ALLOWED_SENDERS`: List of sender emails or domain patterns to filter (for multi-client accounts). Values starting with `@` match any sender from that domain (e.g., `'@yourcompany.com'`)
- `EXCLUDED_RECIPIENT_DOMAINS`: List of email domains to exclude from analytics (e.g., internal/test domains)
- `MESSAGE_GROUP_BY`: Grouping strategy — `'subject'` (default) or `'tag'` (see [Tag-Based Message Grouping](#tag-based-message-grouping))
- `MESSAGE_TAG_PREFIX`: Tag prefix for grouping (default: `'digest'`, only used when `MESSAGE_GROUP_BY = 'tag'`)
- `CLIENT_UID`: UUID for tracking client (defaults to generated UUID)
- `STATS_UPDATE`: When message counters are recalculated — `'sync'` (default, inside the webhook request) or `'deferred'` (see [Statistics Update Mode](#statistics-update-mode))
- `STATS_UPDATE_HANDLER`: Dotted path of a callable that enqueues the recalculation of a message (only used when `STATS_UPDATE = 'deferred'`)

## Tag-Based Message Grouping

By default, emails are grouped into messages by subject line and sent date. For applications where email subjects are personalised per recipient (e.g. `"Report 2024-09-17 - ClientName"`), this causes each unique subject to create a separate message, fragmenting analytics.

Tag-based grouping solves this by using [Brevo tags](https://developers.brevo.com/docs/transactional-webhooks) instead of subjects for grouping.

### Grouping Configuration

```python
BREVO_ANALYTICS = {
    # ... other settings ...
    'MESSAGE_GROUP_BY': 'tag',       # Group by tag instead of subject
    'MESSAGE_TAG_PREFIX': 'digest',  # Match tags starting with this prefix
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `MESSAGE_GROUP_BY` | `'subject'` | Grouping strategy: `'subject'` (default) or `'tag'` |
| `MESSAGE_TAG_PREFIX` | `'digest'` | Prefix to identify the grouping tag (only used when `MESSAGE_GROUP_BY = 'tag'`) |

### Tag Format Convention

The sending application should set tags following a `{prefix}:{id}:{display_title}` convention:

```python
# Example using django-anymail
message = EmailMultiAlternatives(subject="Report - Acme Corp", ...)
message.tags = [
    "digest:42:Weekly Report 2024-09-17",  # Grouping tag
    "customer:15:Acme Corp",                # Optional extra tag
]
message.send()
```

- **`prefix`** — matches `MESSAGE_TAG_PREFIX` (e.g. `digest`)
- **`id`** — unique identifier for the logical send (prevents collisions on same-day sends with identical titles)
- **`display_title`** — human-readable title shown in the dashboard

### How It Works

1. Tags are extracted from the Brevo webhook payload or CSV export
2. All tags are stored on `BrevoEmail.tags` (regardless of grouping mode)
3. When `MESSAGE_GROUP_BY = 'tag'`:
   - The first tag matching the configured prefix is used as the `BrevoMessage.subject`
   - If no matching tag is found, falls back to the email subject (graceful degradation)
4. The API returns both `subject` (raw) and `display_subject` (human-readable, with prefix and ID stripped)

### Backward Compatibility

- Default behaviour is completely unchanged (`MESSAGE_GROUP_BY` defaults to `'subject'`)
- Existing installations require no configuration changes
- The `BrevoMessage` model is unchanged — no new fields, constraints, or migrations on that table
- Tags are always stored on `BrevoEmail` even in subject grouping mode, enabling future analytics

## Statistics Update Mode

Every webhook event changes the counters of its `BrevoMessage` (`total_sent`, `total_delivered`, rates, bounce split…). By default they are recalculated **synchronously**, inside the webhook request: the dashboard is always up to date, but each event recalculates the whole send, so its cost grows with the number of recipients, and the cost of a whole send with their square.

For large sends, switch to **deferred** mode: the webhook only marks the message as dirty and answers at once; the counters are recalculated outside the request, once per burst of events.

### When to Switch

The default is fine for sends of a few hundred recipients. Consider deferred mode when your sends reach thousands of recipients, or when you see any of these during and right after a send:

- webhook latency in the seconds (p90/p99) on `/brevo-analytics/webhook/`;
- `499` responses (Brevo closed the connection before the answer) or `500`/`502` on the webhook;
- web workers saturated, slower pages for the rest of the application.

Dropped calls are retried by Brevo a limited number of times, then lost: open, click and bounce rates end up lower than the real ones.

Indicative cost per webhook event, PostgreSQL 16, one send of 5,000 recipients with ~3.4 events each (raw payloads included), no concurrent load:

| | per event |
|---|---|
| `sync`, up to 0.9.0 | ~240 ms |
| `sync`, from 0.10.0 (counts done by the database) | ~11 ms |
| `deferred` | ~2 ms, independent of the number of recipients |

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `STATS_UPDATE` | `'sync'` | `'sync'`: recalculate inside the webhook request. `'deferred'`: mark the message and recalculate later |
| `STATS_UPDATE_HANDLER` | `None` | Dotted path (or callable) `handler(message_id)`, called after commit when a message becomes dirty. Only used in deferred mode |

### How Deferred Mode Works

1. `add_event()` saves the event and, once the transaction commits, sets `BrevoMessage.stats_dirty = True`: one `UPDATE`, whatever the number of recipients. Raising the flag after the commit keeps events safe with `ATOMIC_REQUESTS` too: a job can never clear the flag before the event it stands for is visible.
2. Only the event that turns the flag from `False` to `True` calls `STATS_UPDATE_HANDLER`. A burst of events on the same send enqueues **one** recalculation, not one per event.
3. The job calls `brevo_analytics.stats.recalculate_message_stats(message_id)`, which clears the flag and recalculates in one transaction, holding the lock on the message row. Two jobs on the same send run one after the other; an event committed meanwhile raises the flag again once the job commits, and enqueues a new job. If the recalculation fails, the transaction is rolled back and the flag stays raised.
4. Until the job runs, dashboard, API and admin show the last calculated counters. Event timelines and statuses of single emails are always current.

If the handler raises (e.g. the queue is unreachable), the error is logged and the webhook still answers `200`: the event is saved and the message stays dirty for the safety net below.

### Enabling Deferred Mode

**1. Apply the migration** (adds `BrevoMessage.stats_dirty`, 0.10.0+):

```bash
python manage.py migrate brevo_analytics
```

**2. Write a handler that only enqueues.** It runs inside the webhook request: do not recalculate there, or you are back to the synchronous cost. The package does not depend on any task queue; use the one your project already has.

With [django-rq](https://github.com/rq/django-rq):

```python
# yourproject/brevo_stats.py
import django_rq
from brevo_analytics.stats import recalculate_message_stats


def enqueue_brevo_stats(message_id):
    django_rq.enqueue(recalculate_message_stats, message_id)
```

To collect more events into one recalculation, delay the job a little — `django_rq.get_queue('default').enqueue_in(timedelta(seconds=30), recalculate_message_stats, message_id)`; RQ runs delayed jobs only on workers started with `--with-scheduler`.

With Celery:

```python
# yourproject/tasks.py
from celery import shared_task
from brevo_analytics.stats import recalculate_message_stats


@shared_task
def recalculate_brevo_stats(message_id):
    recalculate_message_stats(message_id)


def enqueue_brevo_stats(message_id):
    recalculate_brevo_stats.delay(message_id)
```

**3. Configure:**

```python
BREVO_ANALYTICS = {
    # ... other settings ...
    'STATS_UPDATE': 'deferred',
    'STATS_UPDATE_HANDLER': 'yourproject.brevo_stats.enqueue_brevo_stats',
}
```

**4. Schedule the safety net** — required, not optional:

```bash
# crontab: every 5 minutes
*/5 * * * * cd /path/to/project && python manage.py recalculate_stats --dirty
```

Since only the first event of a burst enqueues a job, a job that never runs (worker restarted, queue flushed, handler failure) would leave the counters of that send stale. The command recalculates whatever is still dirty; with nothing dirty it costs a couple of queries. rq-scheduler or Celery beat work as well as cron.

**Without a task queue**, skip step 2 and leave `STATS_UPDATE_HANDLER` unset: the webhook only marks messages, and the command of step 4 does all the recalculation. Counters lag by up to the cron interval.

### Switching Back

Remove `STATS_UPDATE` (or set it to `'sync'`), then run `python manage.py recalculate_stats --dirty` once, to recalculate the messages left dirty.

## Data Flow

```
Brevo → Webhook → Django Model → PostgreSQL
                       ↓
                   DRF API
                       ↓
                  Vue.js SPA
```

## Multi-Client Support

For shared Brevo accounts, use `ALLOWED_SENDERS` to filter:
- **Exact emails** (`'info@yourproject.com'`): match that address only (case-insensitive)
- **Domain patterns** (`'@yourcompany.com'`): match any sender from that domain (case-insensitive)
- Emails without sender info: included only if in local database
- This prevents showing other clients' data

## Development

### Clone Repository

```bash
git clone https://github.com/guglielmo/django-brevo-analytics.git
cd django-brevo-analytics
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Tests

```bash
python runtests.py
```

Runs on SQLite in memory. Some database queries (JSON containment) only run on PostgreSQL or MySQL; to exercise them, point the suite at a PostgreSQL server:

```bash
TEST_DB=postgres PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=... python runtests.py
```

### Build Package

```bash
python -m build
```

## Troubleshooting

### Webhook Not Working

- Verify `WEBHOOK_SECRET` matches Brevo configuration
- Check webhook URL is publicly accessible
- Review Django logs for authentication errors
- Test webhook with `curl` to check connectivity

### Empty Dashboard

- Run `import_brevo_logs` to import historical data
- Verify webhook is configured and receiving events
- Check `ALLOWED_SENDERS` filter isn't too restrictive
- Ensure migrations have been applied

### Blacklist Management Not Working

- Add `API_KEY` to `BREVO_ANALYTICS` settings
- Verify API key has correct permissions on Brevo
- Check network connectivity to Brevo API

## Upgrading

### Upgrade note (0.10.0)

New field `BrevoMessage.stats_dirty` (additive, default `False`) and new opt-in
setting `STATS_UPDATE`. The default behaviour does not change: counters are
still recalculated inside the webhook request, with the same values as before,
but the counts that used to load every email of the send are now done by the
database.

After upgrading the package:

1. `python manage.py migrate brevo_analytics` — adds the new column.

No recalculation is needed. If your sends reach thousands of recipients, see
[Statistics Update Mode](#statistics-update-mode) to enable deferred mode.

### Upgrade note (0.9.0)

New denormalized counters on `BrevoMessage`: `total_bounced_hard`,
`total_bounced_soft`, `total_bounced_undetermined`, `total_deferred`
(additive, default 0 — no breaking changes).

After upgrading the package, you **must**:

1. `python manage.py migrate brevo_analytics` — adds the new columns.
2. `python manage.py recalculate_stats` — recalculates stats for ALL
   messages (calls `update_stats()` on each one) and populates the new
   counters on historical records. Idempotent: re-running it produces the
   same values. New sends populate the counters automatically via webhook,
   so step 2 is only needed for historical data — recommended but not
   blocking.

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

See [AUTHORS.md](AUTHORS.md) for contributors.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- Built with [Django](https://www.djangoproject.com/) and [Django REST Framework](https://www.django-rest-framework.org/)
- Frontend powered by [Vue.js 3](https://vuejs.org/)
- CSV processing with [DuckDB](https://duckdb.org/)

## Links

- [PyPI Package](https://pypi.org/project/django-brevo-analytics/)
- [GitHub Repository](https://github.com/guglielmo/django-brevo-analytics)
- [Issue Tracker](https://github.com/guglielmo/django-brevo-analytics/issues)
- [Changelog](CHANGELOG.md)
