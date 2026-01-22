# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`django-brevo-analytics` is a reusable Django package that integrates transactional email analytics from Brevo directly into Django admin. It uses Django-native models with events stored as JSONField for optimal performance.

**Architecture:** Django Models + DRF API + Vue.js SPA + Direct Brevo Webhooks

**Date:** 2026-01-21 (Complete refactoring from Supabase to Django-native)

## Development Setup

This is a **Django package** (not a standalone project). Development is done against the `infoparlamento` project located at `~/Workspace/infoparlamento`.

### Running the Development Project

To execute any Django management command for testing:

```bash
# 1. Ensure docker-compose stack is running
cd ~/Workspace/infoparlamento
docker compose -f local.yml up -d

# 2. Activate virtualenv and run commands
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py <command>
```

**Required services (local.yml):**
- PostgreSQL (port 5432)
- Redis (port 6379)
- MailHog (ports 1025, 8025)

### Common Development Commands

```bash
# Create migrations
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py makemigrations brevo_analytics

# Apply migrations
DJANGO_READ_DOT_ENV_FILE=1 python manage.py migrate brevo_analytics

# Run tests
DJANGO_READ_DOT_ENV_FILE=1 python manage.py test brevo_analytics

# Import historical data from raw Brevo logs
# (automatically enriches bounces if API key is configured)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /path/to/logs_infoparlamento_202512_today.csv

# Verify statistics against Brevo API (reads API key from settings if not provided)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py verify_brevo_stats

# Run development server (from infoparlamento project)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py runserver
```

### Building Package

```bash
cd /home/gu/Workspace/lab.prototypes/brevo-analytics
python setup.py sdist bdist_wheel
```

## Architecture

### Django-Native Architecture (2026-01-21+)

**Data Flow:**
```
Brevo Webhooks → Django Webhook Endpoint → Django Models (PostgreSQL) → DRF API → Vue.js SPA
```

**Key Components:**

1. **Django Models** (`brevo_analytics/models.py`):
   - `BrevoMessage`: Identified by `subject` + `sent_date` (unique together)
   - `Email`: Contains events as JSONField array, with cached `current_status`
   - Direct database access via Django ORM
   - Denormalized statistics for performance

2. **REST API** (`brevo_analytics/api_views.py`, `brevo_analytics/serializers.py`):
   - Django REST Framework endpoints
   - 6 API endpoints for dashboard, messages, emails
   - Admin-only access via `IsAdminUser` permission

3. **Vue.js SPA** (`brevo_analytics/static/brevo_analytics/js/app.js`):
   - Served within Django admin interface
   - Hash-based routing (Vue Router)
   - Modal overlays for email details (no page reloads)
   - Reactive KPI filters and search

4. **Brevo Webhook** (`brevo_analytics/webhooks.py`):
   - Real-time event processing
   - HMAC signature validation
   - Automatic status updates and statistics recalculation

### Data Models

**BrevoMessage:**
```python
subject = TextField()                    # Email subject
sent_date = DateField()                  # Date of sending
# Denormalized statistics
total_sent, total_delivered, total_opened, total_clicked
total_bounced, total_blocked
delivery_rate, open_rate, click_rate

unique_together = [['subject', 'sent_date']]
```

**Email:**
```python
brevo_message_id = CharField()           # Brevo's unique ID
recipient_email = EmailField()
sent_at = DateTimeField()
events = JSONField(default=list)         # Array of event objects
current_status = CharField()             # Cached for fast queries

# Events structure:
# [
#   {"type": "sent", "timestamp": "2026-01-21T10:00:00Z"},
#   {"type": "delivered", "timestamp": "2026-01-21T10:01:23Z"},
#   {"type": "opened", "timestamp": "2026-01-21T11:30:00Z", "ip": "..."}
# ]
```

### API Endpoints

```
GET /admin/brevo_analytics/api/dashboard/
    → KPI + last 20 messages

GET /admin/brevo_analytics/api/messages/
    → All messages (for "show all")

GET /admin/brevo_analytics/api/messages/:id/emails/?status=bounced
    → Emails for specific message (with optional status filter)

GET /admin/brevo_analytics/api/emails/bounced/
    → All bounced emails (cross-message)

GET /admin/brevo_analytics/api/emails/blocked/
    → All blocked emails (cross-message)

GET /admin/brevo_analytics/api/emails/:id/
    → Single email detail with full event timeline

POST /admin/brevo_analytics/webhook/
    → Brevo webhook endpoint (HMAC validated)
```

### SPA Routes (Hash-based)

```
#/                                      → Dashboard
#/messages/:id/emails                   → Emails for message
#/messages/:id/emails?status=bounced    → Filtered emails
#/emails/bounced                        → Global bounced emails
#/emails/blocked                        → Global blocked emails

(Modal overlay, no route change)       → Email detail timeline
```

## Configuration

### Required Django Settings

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

# DRF settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
}

# CORS (development)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
]

# Brevo Analytics configuration
BREVO_ANALYTICS = {
    'WEBHOOK_SECRET': 'your-webhook-secret-here',  # From Brevo dashboard
    'CLIENT_UID': 'your-client-uuid',              # For tracking
}
```

### Include URLs

```python
# your_project/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin/brevo_analytics/', include('brevo_analytics.urls')),
]
```

## File Structure

```
brevo_analytics/
├── models.py                    # Django models (BrevoMessage, Email)
├── admin.py                     # Django admin registration + SPA view
├── serializers.py               # DRF serializers
├── api_views.py                 # DRF API endpoints
├── webhooks.py                  # Brevo webhook handler
├── urls.py                      # URL configuration
├── tests.py                     # Unit tests
├── migrations/                  # Django migrations
│   └── 0001_initial.py
├── management/                  # Management commands
│   └── commands/
│       ├── import_brevo_logs.py # Main import command (DuckDB-based)
│       ├── verify_brevo_stats.py # Statistics verification tool
│       └── archive/             # Archived obsolete commands
├── templates/                   # Django templates
│   └── brevo_analytics/
│       └── spa.html             # SPA entry point
├── static/                      # Frontend assets
│   └── brevo_analytics/
│       ├── css/
│       │   └── app.css          # SPA styles
│       └── js/
│           └── app.js           # Vue.js SPA
└── templatetags/
    └── brevo_filters.py         # Template filters (legacy)

docs/
├── README.md                    # Main documentation
├── INSTALLATION.md              # Installation guide
├── plans/
│   └── 2026-01-21-spa-implementation-plan.md
└── archive/                     # Obsolete Supabase docs
    ├── README.md
    ├── sql/                     # Old Supabase schema
    └── [archived docs]

Root files:
├── emails_import.csv            # Historical data for import
├── email_events_import.csv
└── requirements.txt
```

## Key Design Decisions

1. **Django-Native vs Supabase**: Complete refactoring to eliminate external dependencies and reduce costs. All data stored directly in Django database.

2. **Events as JSONField**: Denormalized approach stores events as JSON array in Email model. Enables single-query access to complete email history.

3. **Cached Status**: `current_status` field pre-calculated and indexed for fast filtering without parsing JSON.

4. **No Temporal Filters**: SPA shows all historical data (no date range filters). Simplifies UX and ensures complete visibility.

5. **Modal-Based Details**: Email event timeline displayed in modal overlay to avoid page navigation and maintain context.

6. **Single-Tenant**: One client per Django instance (no multi-tenant complexity). Client ID stored in settings.

## Common Development Tasks

### Running Tests in Development Project

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py test brevo_analytics
```

### Importing Historical Data from Raw Logs

```bash
cd ~/Workspace/infoparlamento
source venv/bin/activate

# Test import with dry-run (no data changes)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv \
  --dry-run

# Actual import (automatically enriches bounces if API key is configured)
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv

# Clear existing data and reimport
DJANGO_READ_DOT_ENV_FILE=1 python manage.py import_brevo_logs \
  /home/gu/Workspace/lab.prototypes/brevo-analytics/logs_infoparlamento_202512_today.csv \
  --clear
```

### Testing Webhook Locally

```bash
# Terminal 1: Start Django dev server
cd ~/Workspace/infoparlamento
source venv/bin/activate
DJANGO_READ_DOT_ENV_FILE=1 python manage.py runserver

# Terminal 2: Use ngrok for external access
ngrok http 8000

# Configure ngrok URL in Brevo dashboard:
# https://abc123.ngrok.io/admin/brevo_analytics/webhook/
```

### Testing Webhook with curl

```bash
curl -X POST http://localhost:8000/admin/brevo_analytics/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "event": "delivered",
    "message-id": "<test123@smtp-relay.mailin.fr>",
    "email": "test@example.com",
    "subject": "Test Email",
    "ts_event": 1737468000
  }'
```

### Accessing the SPA

Once the development server is running:
```
http://localhost:8000/admin/brevo_analytics/brevomessage/
```

## Historical Note

This project was completely refactored on 2026-01-21 from a Supabase-based architecture to Django-native. Old documentation is archived in `docs/archive/`.

## Status Hierarchy

Events determine email status based on this hierarchy (highest wins):
```
clicked > opened > delivered > bounced > blocked > deferred > unsubscribed > sent
```

## Event Types

Mapped from Brevo webhook events:
- `request` → `sent`
- `delivered` → `delivered`
- `hard_bounce`, `soft_bounce` → `bounced`
- `blocked` → `blocked`
- `spam` → `spam`
- `unsubscribe` → `unsubscribed`
- `opened` → `opened`
- `click` → `clicked`
- `deferred` → `deferred`
