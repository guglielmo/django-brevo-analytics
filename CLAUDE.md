# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`django-brevo-analytics` is a reusable Django package that integrates transactional email analytics from Brevo (via Supabase) into Django admin. It uses a "virtual model" pattern where Django models are unmanaged (`managed=False`) and all data is fetched from an external Supabase database via the PostgREST API.

## Build and Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Building Package
```bash
python setup.py sdist bdist_wheel
```

### Running Tests
```bash
pytest
```

## Architecture

### Virtual Model Pattern

The core architectural pattern of this package:

1. **Virtual Model** (`brevo_analytics/models.py`):
   - Django model with `managed=False` (no database table created)
   - Exists solely for Django admin registration and navigation
   - No actual database operations

2. **Custom Admin Views** (`brevo_analytics/admin.py`, `brevo_analytics/views.py`):
   - Admin URLs overridden to point to custom views
   - Views fetch data from Supabase using `SupabaseClient`
   - Three main views: dashboard, email list, email detail

3. **Supabase Client** (`brevo_analytics/supabase.py`):
   - Wrapper around Supabase PostgREST API
   - Handles JWT authentication with `client_id` claim for RLS
   - Implements caching via Django's cache framework
   - Graceful fallback to cached data on API failure

### Data Flow

```
Brevo API → n8n Webhook/Polling → Supabase → SupabaseClient → Django Views → Admin Interface
```

### Security Model

- **Row Level Security (RLS)**: All Supabase tables use RLS policies to filter by `client_id` from JWT
- **JWT Authentication**: Custom JWT with `client_id` claim enables multi-tenant isolation
- **Read-Only Access**: Admin interface has all write permissions disabled
- **Staff Permissions**: Requires `request.user.is_staff` for access

### Caching Strategy

- All Supabase API calls are cached using Django's cache framework
- Cache keys include all filter parameters to ensure proper isolation
- Failed API calls automatically fall back to cached data with user warnings
- Default cache timeout: 5 minutes (configurable via `CACHE_TIMEOUT`)

## Supabase Schema

Located in `sql/` directory, executed in order:

1. `00_create_schema.sql` - Creates `brevo_analytics` schema
2. `01_create_tables.sql` - Creates `clients`, `emails`, `email_events` tables
3. `02_enable_rls.sql` - Enables Row Level Security policies
4. `03_create_test_data.sql` - Creates test client (saves client_id UUID)
5. `04_generate_jwt.py` - Python script to generate JWT with `client_id` claim
6. `05_insert_sample_emails.sql` - Optional sample data
7. `06_create_sync_state_table.sql` - Tracks synchronization state for n8n workflows
8. `07_import_from_csv.sql` - Bulk CSV import for historical data

**Important Schema Note**: The schema reference is `public.clients` but the analytics tables are in `brevo_analytics` schema. Always use `Accept-Profile: brevo_analytics` header when making PostgREST API calls.

## Data Synchronization

Email data must be synced from Brevo to Supabase before appearing in the dashboard. Two strategies documented in `docs/n8n-workflow-design.md`:

1. **Webhook Strategy (Recommended)**: Real-time event processing via Brevo webhooks
2. **Polling Strategy**: Periodic API fetching with incremental sync using `sync_state` table

The `sync_state` table tracks last synchronization timestamps to enable differential/incremental sync.

## Configuration

Required Django settings:

```python
BREVO_ANALYTICS = {
    'SUPABASE_URL': 'https://your-project.supabase.co',
    'ANON_KEY': 'your-anon-key',  # From Supabase dashboard
    'JWT': 'your-jwt-token',      # Generated with 04_generate_jwt.py
    'CACHE_TIMEOUT': 300,         # Optional, default 5 minutes
    'RETENTION_DAYS': 60,         # Optional, default 60 days
}
```

**JWT Requirements**: Must include `client_id` claim matching a record in `brevo_analytics.clients` table. Generate using `sql/04_generate_jwt.py`.

## File Structure

```
brevo_analytics/
├── admin.py              # Django admin registration with URL overrides
├── views.py              # Custom views (dashboard, email list, detail)
├── models.py             # Virtual model (managed=False)
├── supabase.py           # Supabase API client wrapper
├── exceptions.py         # Custom exceptions
├── templates/            # Django templates for admin UI
│   └── admin/brevo_analytics/
│       ├── dashboard.html
│       ├── email_list.html
│       ├── email_detail.html
│       └── config_error.html
├── templatetags/         # Custom template filters
│   └── brevo_filters.py  # Formatters for bounce types, statuses
└── static/               # CSS, JS for charts and tables

sql/
├── 00-07_*.sql           # Supabase schema setup scripts (run in order)
├── 04_generate_jwt.py    # JWT generation with client_id claim
└── transform_csv_to_supabase.py  # CSV data import utility

docs/
├── n8n-workflow-design.md      # Complete n8n sync implementation guide
├── csv-import-guide.md         # Historical data import guide
├── INSTALLATION.md             # Installation instructions
└── SUPABASE_SETUP.md          # Database setup guide
```

## Custom Template Tags

`brevo_analytics/templatetags/brevo_filters.py` provides formatters:
- Bounce type/reason display formatting
- Event type humanization
- Date/time formatting

## Key Design Decisions

1. **No Django Migrations**: Virtual model with `managed=False` means no database tables are created by Django. Schema is entirely managed in Supabase via SQL scripts.

2. **API-First**: All data access goes through Supabase PostgREST API, never direct database connections.

3. **Cache Resilience**: Every Supabase API call has a cache fallback to ensure the dashboard remains functional even during API outages.

4. **RLS Enforcement**: Multi-tenant isolation is enforced at the database level via Supabase RLS, not application level.

5. **Read-Only**: The package intentionally provides no write operations for security and data integrity.

## CSV Import Workflow

For importing historical data (documented in `docs/csv-import-guide.md`):

1. Export data from Brevo API or logs to CSV
2. Transform using `sql/transform_csv_to_supabase.py`
3. Import via `sql/07_import_from_csv.sql`
4. Located in root: `emails_import.csv`, `email_events_import.csv`

## Common Development Tasks

### Testing JWT Configuration
```bash
curl "https://YOUR-PROJECT.supabase.co/rest/v1/emails?select=*&limit=1" \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Accept-Profile: brevo_analytics"
```

### Generating New JWT
```bash
cd sql/
python 04_generate_jwt.py
# Follow prompts for JWT secret, anon key, client_id
```

### Viewing Cached Data
Django cache keys follow pattern:
- Dashboard: `brevo_dashboard_{date_range}`
- Email list: `brevo_emails_{date_range}_{search}`
- Email detail: `brevo_email_{email_id}`
