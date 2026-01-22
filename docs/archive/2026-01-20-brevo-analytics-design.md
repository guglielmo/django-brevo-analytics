# Brevo Analytics Django Package - Design Document

**Date:** 2026-01-20
**Type:** Reusable Django Package
**Purpose:** Read-only admin interface for viewing transactional email analytics from Supabase

---

## Overview

A reusable Django package that integrates with Django admin to display transactional email analytics. Data is stored in Supabase (populated via n8n from Brevo API) and accessed read-only via JWT authentication with RLS-based client isolation.

## Key Characteristics

- **Read-only**: No Django models with database tables, only viewing external data
- **Single-tenant per site**: One Django site = one client = one JWT with client_id claim
- **Admin integration**: Uses virtual model pattern for native admin navigation
- **Delivery-focused**: Initially focused on delivery health metrics (sent, delivered, bounced)
- **Event tracking**: Individual email records with full event timeline

---

## Architecture

### Package Structure

```
brevo_analytics/
├── __init__.py
├── admin.py          # ModelAdmin registration with custom URLs
├── models.py         # Virtual proxy model (managed=False)
├── views.py          # Custom admin views (dashboard, list, detail)
├── supabase.py       # Supabase client wrapper with caching
├── urls.py           # URL routing
├── apps.py           # App configuration
├── templatetags/     # Custom template filters
│   └── brevo_filters.py
├── templates/
│   └── admin/
│       └── brevo_analytics/
│           ├── dashboard.html
│           ├── email_list.html
│           └── email_detail.html
└── static/
    └── brevo_analytics/
        └── css/
            └── admin-overrides.css
```

### Technology Stack

- **Database**: Supabase (PostgreSQL with PostgREST)
- **API Client**: `postgrest-py` (official PostgREST Python client)
- **Caching**: Django cache framework (5 min default timeout)
- **Frontend Libraries**: Chart.js (sparklines), DataTables (interactive tables) - loaded via CDN
- **Authentication**: JWT with `client_id` claim for RLS

---

## Data Model

### Supabase Schema

```sql
-- Clients table
CREATE TABLE clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);

-- Emails table
CREATE TABLE emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID REFERENCES clients(id) NOT NULL,
  brevo_email_id BIGINT,
  recipient_email TEXT NOT NULL,
  template_name TEXT,
  subject TEXT,
  sent_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Email events table
CREATE TABLE email_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(id) NOT NULL,
  event_type TEXT NOT NULL,  -- sent, delivered, opened, clicked, bounced, unsubscribed
  event_timestamp TIMESTAMPTZ NOT NULL,
  bounce_type TEXT,          -- hard, soft (only for bounced events)
  bounce_reason TEXT,        -- detailed reason from Brevo
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS policies
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
CREATE POLICY "client_isolation_emails" ON emails
  FOR SELECT USING (client_id = (auth.jwt() ->> 'client_id')::UUID);

ALTER TABLE email_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "client_isolation_events" ON email_events
  FOR SELECT USING (
    email_id IN (
      SELECT id FROM emails WHERE client_id = (auth.jwt() ->> 'client_id')::UUID
    )
  );
```

### Virtual Django Model

```python
# models.py
from django.db import models

class BrevoEmail(models.Model):
    """Virtual model for admin integration - no database table"""

    class Meta:
        managed = False
        verbose_name = "Brevo Email"
        verbose_name_plural = "Brevo Analytics"
        default_permissions = ('view',)
```

---

## Configuration

### Django Settings

```python
BREVO_ANALYTICS = {
    'SUPABASE_URL': 'https://xxx.supabase.co',
    'JWT': 'eyJ...',  # JWT with client_id claim
    'CACHE_TIMEOUT': 300,  # seconds (default: 5 minutes)
    'RETENTION_DAYS': 60,  # configurable data retention (default: 60)
}

INSTALLED_APPS = [
    # ...
    'brevo_analytics',
]
```

### Configuration Validation

- **Timing**: Validated when views are accessed (fail gracefully, not at startup)
- **Missing config**: Show friendly error page in admin view
- **Invalid JWT/URL**: Display error message, don't break entire Django project

---

## Components

### 1. Supabase Client (`supabase.py`)

```python
from postgrest import Client
from django.core.cache import cache
from django.conf import settings

class SupabaseClient:
    def __init__(self):
        config = getattr(settings, 'BREVO_ANALYTICS', {})
        self.url = config.get('SUPABASE_URL')
        self.jwt = config.get('JWT')
        self.cache_timeout = config.get('CACHE_TIMEOUT', 300)

        if self.url and self.jwt:
            self.client = Client(f"{self.url}/rest/v1")
            self.client.headers = {
                'apikey': self.jwt,
                'Authorization': f'Bearer {self.jwt}'
            }

    def is_configured(self):
        return bool(self.url and self.jwt)

    def get_emails(self, date_range='7d', search=None):
        """Fetch emails with caching"""
        cache_key = f'brevo_emails_{date_range}_{search or ""}'
        data = cache.get(cache_key)

        if data is None:
            try:
                data = self._fetch_emails(date_range, search)
                cache.set(cache_key, data, self.cache_timeout)
            except Exception as e:
                # Return empty data, let view handle error display
                raise

        return data

    def get_dashboard_stats(self, date_range='7d'):
        """Fetch aggregated dashboard metrics"""
        cache_key = f'brevo_dashboard_{date_range}'
        data = cache.get(cache_key)

        if data is None:
            try:
                data = self._fetch_dashboard_stats(date_range)
                cache.set(cache_key, data, self.cache_timeout)
            except Exception:
                raise

        return data

    def get_email_detail(self, email_id):
        """Fetch single email with events"""
        cache_key = f'brevo_email_{email_id}'
        data = cache.get(cache_key)

        if data is None:
            try:
                data = self._fetch_email_detail(email_id)
                cache.set(cache_key, data, self.cache_timeout)
            except Exception:
                raise

        return data
```

**Caching Strategy:**
- Cache keys include all filter parameters
- Failed API calls raise exceptions (views handle gracefully)
- Django cache backend handles storage (Redis, Memcached, or database)

**RLS Security:**
- JWT contains `client_id` claim
- All queries automatically filtered by Supabase RLS
- No explicit client_id filtering needed in queries

### 2. Admin Integration (`admin.py`)

```python
from django.contrib import admin
from django.urls import path
from .models import BrevoEmail
from . import views

@admin.register(BrevoEmail)
class BrevoEmailAdmin(admin.ModelAdmin):
    # Read-only permissions
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    # Custom URL routing
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', views.dashboard_view, name='brevo_analytics_dashboard'),
            path('emails/', views.email_list_view, name='brevo_analytics_email_list'),
            path('emails/<uuid:email_id>/', views.email_detail_view, name='brevo_analytics_email_detail'),
        ]
        return custom_urls + urls
```

**Integration Benefits:**
- Appears in admin sidebar as "Brevo Analytics"
- Uses admin breadcrumbs and navigation
- Respects Django staff permissions
- Custom URLs for all views

### 3. Views (`views.py`)

#### Dashboard View

```python
@staff_member_required
def dashboard_view(request):
    client = SupabaseClient()

    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error',
            'error': 'BREVO_ANALYTICS settings are missing or invalid'
        })

    date_range = request.GET.get('range', '7d')
    context = {
        'title': 'Brevo Analytics Dashboard',
        'date_range': date_range,
    }

    try:
        stats = client.get_dashboard_stats(date_range)
        context.update({
            'stats': stats,
            'api_healthy': True
        })
    except Exception as e:
        # Try to use cached data
        try:
            cached_stats = cache.get(f'brevo_dashboard_{date_range}')
            if cached_stats:
                context['stats'] = cached_stats
                messages.warning(request,
                    'Unable to refresh data from API. Showing cached data. Please try again later.')
            else:
                messages.error(request,
                    'Unable to load analytics data. The API is not responding. Please try again later.')
        except:
            messages.error(request,
                'Unable to load analytics data. The API is not responding. Please try again later.')

        context['api_healthy'] = False

    return render(request, 'admin/brevo_analytics/dashboard.html', context)
```

#### Email List View

```python
@staff_member_required
def email_list_view(request):
    client = SupabaseClient()

    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error'
        })

    date_range = request.GET.get('range', '7d')
    search = request.GET.get('q', '').strip()

    context = {
        'title': 'Email List',
        'date_range': date_range,
        'search': search,
    }

    try:
        emails = client.get_emails(date_range, search)
        context['emails'] = emails
        context['api_healthy'] = True
    except Exception as e:
        # Try cached data
        cache_key = f'brevo_emails_{date_range}_{search}'
        cached_emails = cache.get(cache_key)
        if cached_emails:
            context['emails'] = cached_emails
            messages.warning(request,
                'Unable to refresh data. Showing cached results.')
        else:
            context['emails'] = []
            messages.error(request,
                'Unable to load emails. Please try again later.')

        context['api_healthy'] = False

    return render(request, 'admin/brevo_analytics/email_list.html', context)
```

#### Email Detail View

```python
@staff_member_required
def email_detail_view(request, email_id):
    client = SupabaseClient()

    if not client.is_configured():
        return render(request, 'admin/brevo_analytics/config_error.html', {
            'title': 'Brevo Analytics - Configuration Error'
        })

    context = {'title': 'Email Details'}

    try:
        email_data = client.get_email_detail(email_id)
        context['email'] = email_data['email']
        context['events'] = email_data['events']
        context['api_healthy'] = True
    except Exception as e:
        # Try cached data
        cache_key = f'brevo_email_{email_id}'
        cached_data = cache.get(cache_key)
        if cached_data:
            context['email'] = cached_data['email']
            context['events'] = cached_data['events']
            messages.warning(request,
                'Unable to refresh data. Showing cached details.')
        else:
            messages.error(request,
                'Unable to load email details. Please try again later.')
            return redirect('admin:brevo_analytics_email_list')

        context['api_healthy'] = False

    return render(request, 'admin/brevo_analytics/email_detail.html', context)
```

**Error Handling Pattern:**
1. Try to fetch fresh data from API
2. On exception, check for cached data
3. If cached data exists, show it with warning banner
4. If no cache, show error message
5. Never crash - always render something useful

---

## User Interface

### 1. Dashboard View

**URL:** `/admin/brevo-analytics/`

**Metrics Cards (with sparklines):**
- Total Sent
- Delivery Rate %
- Bounce Rate %
- Average Delivery Time

**Date Range Filter:**
- Last 24 hours
- Last 7 days
- Last 30 days
- Last 90 days

**Layout:**
```
┌─────────────────────────────────────────┐
│  BREVO ANALYTICS DASHBOARD              │
├─────────────────────────────────────────┤
│  [Date Range: Last 7 days ▼]           │
├─────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │ 1,234    │ │ 98.5%    │ │ 1.2%     ││
│  │ Sent     │ │ Delivered│ │ Bounced  ││
│  │ ▁▃▅▇▅▃   │ │ ▇▇▇▅▇▅   │ │ ▁▂▁▃▂▁   ││
│  └──────────┘ └──────────┘ └──────────┘│
│                                         │
│  ┌──────────┐                          │
│  │ 2.3s     │                          │
│  │ Avg Time │                          │
│  │ ▃▅▄▃▂▄   │                          │
│  └──────────┘                          │
├─────────────────────────────────────────┤
│  [View All Emails →]                   │
└─────────────────────────────────────────┘
```

### 2. Email List View

**URL:** `/admin/brevo-analytics/emails/`

**Features:**
- Search by recipient or subject
- Date range filter
- Sortable columns (via DataTables)
- Pagination (25/50/100 per page)
- Click row to view detail

**Columns:**
- Recipient
- Template Name
- Subject
- Sent Date
- Status (badge: delivered/opened/clicked/bounced)

**Layout:**
```
┌────────────────────────────────────────────────┐
│  EMAIL LIST                                    │
├────────────────────────────────────────────────┤
│  [Search: ____________] [Range: Last 7d ▼]   │
├────────────────────────────────────────────────┤
│  Recipient     Template    Subject    Sent   Status │
│  ───────────────────────────────────────────────── │
│  user@ex.com   Welcome     Welcome!   Jan 20  ●delivered │
│  test@ex.com   Reset PW    Reset...   Jan 19  ●clicked   │
│  ...                                                │
├────────────────────────────────────────────────┤
│  Showing 1-25 of 234     [1] 2 3 ... 10 →    │
└────────────────────────────────────────────────┘
```

### 3. Email Detail View

**URL:** `/admin/brevo-analytics/emails/<uuid>/`

**Sections:**
- Email metadata (recipient, template, subject, sent date, Brevo ID)
- Event timeline (chronological)
- Bounce details (if bounced)

**Layout:**
```
┌────────────────────────────────────────────┐
│  EMAIL DETAILS                             │
├────────────────────────────────────────────┤
│  Recipient:  user@example.com              │
│  Template:   password-reset                │
│  Subject:    Reset your password           │
│  Sent:       2026-01-20 14:23:45           │
│  Brevo ID:   123456789                     │
├────────────────────────────────────────────┤
│  EVENT TIMELINE                            │
│                                            │
│  ● Sent                                    │
│    2026-01-20 14:23:45                     │
│                                            │
│  ● Delivered                               │
│    2026-01-20 14:23:47 (2s)                │
│                                            │
│  ● Opened                                  │
│    2026-01-20 14:25:12 (1m 27s)            │
│                                            │
│  ● Clicked                                 │
│    2026-01-20 14:25:34 (1m 49s)            │
└────────────────────────────────────────────┘
```

**Bounce Display (when applicable):**
```
│  ● Bounced                                 │
│    2026-01-20 14:23:47                     │
│    Type: Hard Bounce                       │
│    Reason: Mailbox does not exist          │
│    (550 5.1.1 <user@domain.com>:          │
│     Recipient address rejected)            │
```

---

## Frontend Dependencies

### Chart.js (Sparklines)
- **Source:** CDN (`https://cdn.jsdelivr.net/npm/chart.js`)
- **Usage:** Small line charts in dashboard metric cards
- **Configuration:** Minimal, responsive, no axes/labels

### DataTables (Interactive Tables)
- **Source:** CDN (`https://cdn.datatables.net/`)
- **Usage:** Email list sorting, pagination, search
- **Configuration:** Client-side processing, server handles filtering

### Loading Strategy
```html
<!-- In base template -->
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js"></script>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
```

---

## Implementation Phases

### Phase 1: Core Infrastructure
- Package structure
- Supabase client with JWT auth
- Virtual model and admin registration
- Configuration validation

### Phase 2: Dashboard
- Dashboard view with date filters
- Metric calculations
- Sparklines with Chart.js
- Error handling with cache fallback

### Phase 3: Email List
- List view with search
- DataTables integration
- Date range filtering
- Status badges

### Phase 4: Email Detail
- Detail view with event timeline
- Bounce information display
- Navigation between views

### Phase 5: Polish
- Custom CSS for admin styling
- Template tags for formatting
- Documentation (README, installation guide)
- PyPI packaging

---

## Future Enhancements (Not in Initial Version)

- Engagement metrics (open rate, click rate)
- Advanced search (template name, Brevo ID)
- Bounce analysis page (aggregated bounce patterns)
- Export to CSV
- Email content preview (if stored)
- Custom date range picker
- Real-time updates via WebSocket
- Multi-client support (per-user JWTs)

---

## Testing Considerations

- Mock Supabase responses for unit tests
- Test cache fallback scenarios
- Test configuration validation
- Test RLS enforcement (manual verification)
- Test admin permissions
- Test with various date ranges and search queries

---

## Deployment Requirements

### Python Dependencies
```
Django>=4.2
postgrest-py>=0.10.0
requests>=2.28.0  # dependency of postgrest-py
```

### Django Settings
```python
INSTALLED_APPS = ['brevo_analytics']
BREVO_ANALYTICS = {
    'SUPABASE_URL': env('BREVO_SUPABASE_URL'),
    'JWT': env('BREVO_JWT'),
}
```

### Supabase Setup
1. Create tables (clients, emails, email_events)
2. Enable RLS policies
3. Generate JWT with client_id claim
4. Configure n8n to populate data from Brevo webhooks

---

## Security Considerations

- **JWT Security**: JWT must be kept secret, contains client_id claim
- **RLS Enforcement**: All queries automatically filtered by client_id
- **Read-Only**: No write operations, no risk of data modification
- **Staff Access**: Only Django staff users can access analytics
- **HTTPS Required**: API calls must use HTTPS in production
- **Cache Poisoning**: Cache keys include all filter params to prevent cross-client data leakage

---

## Success Criteria

✅ Django admin shows "Brevo Analytics" in sidebar
✅ Dashboard displays delivery health metrics with sparklines
✅ Email list is searchable and sortable
✅ Email detail shows full event timeline
✅ Bounce reasons are clearly displayed for troubleshooting
✅ Cache fallback works when API is unavailable
✅ Only client-specific data is visible (RLS working)
✅ Package is reusable across multiple Django projects

---

## Open Questions

None - design is complete and ready for implementation.
