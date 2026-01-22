# Archived Documentation

This directory contains obsolete documentation from the **Supabase-based architecture** (pre-2026-01-21).

## Why Archived?

On 2026-01-21, the project architecture was completely refactored from:
- **OLD:** Django → Supabase (PostgREST API) → n8n → Brevo webhooks
- **NEW:** Django native models → Direct Brevo webhooks → Vue.js SPA

The new architecture eliminates:
- ❌ Supabase dependency
- ❌ Multi-tenant (clients table)
- ❌ n8n workflows
- ❌ JWT authentication
- ❌ RLS policies

## Archived Files

### Design Documents (Supabase-based)
- `2026-01-20-brevo-analytics-design.md` - Original Supabase architecture design
- `2026-01-20-brevo-analytics-implementation.md` - Supabase implementation plan
- `2026-01-21-django-native-refactoring.md` - Intermediate refactoring plan

### Setup Guides (Supabase-based)
- `SUPABASE_SETUP.md` - Supabase database setup instructions
- `csv-import-guide.md` - CSV import for Supabase tables
- `n8n-workflow-design.md` - n8n workflow for webhook → Supabase sync

### SQL Scripts (Supabase-based)
- `sql/` - Complete Supabase database schema
  - `00_create_schema.sql` - Schema creation
  - `01_create_tables.sql` - Tables (clients, emails, email_events)
  - `02_enable_rls.sql` - Row Level Security policies
  - `03-08_*.sql` - Test data, JWT generation, migrations
  - `09_add_deferred_event_type.sql` - Last migration
  - `10_create_emails_with_status_view.sql` - Materialized view (never used)
  - `transform_csv_to_supabase.py` - CSV transformation script
  - `enrich_bounce_reasons.py` - Bounce reason enrichment via Brevo API

## Current Documentation

See `docs/` root directory for current documentation:
- **`docs/plans/2026-01-21-spa-implementation-plan.md`** - Current implementation plan (Django native + Vue.js SPA)
- **`docs/INSTALLATION.md`** - Updated installation guide

## Historical Context

The Supabase approach was initially chosen for:
1. External database isolation
2. Built-in RLS for multi-tenant
3. PostgREST API convenience

It was abandoned because:
1. Added unnecessary complexity
2. Increased costs (Supabase storage + API calls)
3. Required n8n for webhook processing
4. Single-tenant per Django instance is simpler

The new Django-native approach is:
- ✅ Simpler (standard Django patterns)
- ✅ Cheaper (no external costs)
- ✅ Faster (direct ORM queries)
- ✅ Real-time (direct webhooks)
