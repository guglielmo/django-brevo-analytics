# Supabase Setup Scripts

This directory contains SQL scripts to set up the Brevo Analytics database schema in Supabase.

## Prerequisites

- Supabase project created at: https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy
- Access to the SQL Editor in Supabase dashboard

## Execution Order

Run these scripts in the Supabase SQL Editor **in order**:

### 1. Create Schema
```bash
00_create_schema.sql
```
Creates the `brevo_analytics` schema and sets up permissions.

### 2. Create Tables
```bash
01_create_tables.sql
```
Creates the database tables:
- `brevo_analytics.clients`
- `brevo_analytics.emails`
- `brevo_analytics.email_events`

### 3. Enable Row Level Security
```bash
02_enable_rls.sql
```
Enables RLS policies for multi-tenant isolation.

### 4. Create Test Client
```bash
03_create_test_data.sql
```
Creates a test client for "infoparlamento".

**IMPORTANT:** Save the `client_id` UUID from the output! You'll need it for JWT generation.

### 5. Generate JWT Token
```bash
python 04_generate_jwt.py
```

Run this Python script in your terminal (not in SQL Editor):
1. Install pyjwt: `pip install pyjwt`
2. Get your Supabase service_role secret from: https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy/settings/api
3. Run the script and follow the prompts
4. Save the generated JWT token

### 6. Insert Sample Data (Optional)
```bash
05_insert_sample_emails.sql
```
Inserts 5 test emails with events for testing the Django admin interface.

## After Setup

### Update Django Configuration

Edit `/home/gu/Workspace/infoparlamento/.env`:

```bash
BREVO_SUPABASE_URL=https://fvuhpocdeckmbdgiebfy.supabase.co
BREVO_JWT=<your-generated-jwt-token>
```

### Test the Connection

```bash
# Test with curl
curl "https://fvuhpocdeckmbdgiebfy.supabase.co/rest/v1/brevo_analytics.emails?select=*&limit=1" \
  -H "apikey: YOUR_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Restart Django

```bash
cd ~/Workspace/infoparlamento
python manage.py runserver
```

Then visit: http://localhost:8000/admin/brevo_analytics/brevoemail/

## Schema Overview

```
brevo_analytics/
├── clients            # Client organizations
│   ├── id (UUID, PK)
│   ├── slug (TEXT)
│   └── name (TEXT)
│
├── emails             # Transactional emails
│   ├── id (UUID, PK)
│   ├── client_id (UUID, FK → clients.id)
│   ├── brevo_email_id (BIGINT)
│   ├── recipient_email (TEXT)
│   ├── subject (TEXT)
│   └── sent_at (TIMESTAMPTZ)
│
└── email_events       # Email events timeline
    ├── id (UUID, PK)
    ├── email_id (UUID, FK → emails.id)
    ├── event_type (TEXT)
    ├── event_timestamp (TIMESTAMPTZ)
    ├── bounce_type (TEXT, nullable)
    └── bounce_reason (TEXT, nullable)
```

## Row Level Security (RLS)

All tables have RLS policies that filter by `client_id` from the JWT token:
- Clients can only see their own emails and events
- `service_role` (used by n8n) can insert data for any client

## Troubleshooting

### "Permission denied" errors
- Verify RLS policies are created (`02_enable_rls.sql`)
- Check JWT includes `client_id` claim
- Verify `client_id` UUID matches the clients table

### "Table not found" errors
- Ensure you ran `00_create_schema.sql` first
- Check the schema name is `brevo_analytics`

### Empty results in Django admin
- Verify test data was inserted (`05_insert_sample_emails.sql`)
- Check JWT `client_id` matches test data
- Review date range filters

## Next Steps

- Set up n8n workflow to populate data from Brevo webhooks
- Configure Brevo to send webhooks to n8n
- Test with real email data
