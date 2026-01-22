# Supabase Setup Guide

## Overview

This guide covers setting up the required Supabase database schema and JWT authentication for django-brevo-analytics.

## Prerequisites

- Supabase account (free tier works)
- Supabase project created
- Basic SQL knowledge

## Step 1: Create Tables

### 1.1 Create Clients Table

```sql
CREATE TABLE clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster lookups
CREATE INDEX idx_clients_slug ON clients(slug);
```

### 1.2 Create Emails Table

```sql
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

-- Create indexes for faster queries
CREATE INDEX idx_emails_client_id ON emails(client_id);
CREATE INDEX idx_emails_sent_at ON emails(sent_at DESC);
CREATE INDEX idx_emails_recipient ON emails(recipient_email);
CREATE INDEX idx_emails_brevo_id ON emails(brevo_email_id);
```

### 1.3 Create Email Events Table

```sql
CREATE TABLE email_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE NOT NULL,
  event_type TEXT NOT NULL,
  event_timestamp TIMESTAMPTZ NOT NULL,
  bounce_type TEXT,
  bounce_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT valid_event_type CHECK (
    event_type IN ('sent', 'delivered', 'opened', 'clicked', 'bounced', 'unsubscribed')
  )
);

-- Create indexes for faster queries
CREATE INDEX idx_events_email_id ON email_events(email_id);
CREATE INDEX idx_events_timestamp ON email_events(event_timestamp);
CREATE INDEX idx_events_type ON email_events(event_type);
```

## Step 2: Enable Row Level Security

### 2.1 Enable RLS on Tables

```sql
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_events ENABLE ROW LEVEL SECURITY;
```

### 2.2 Create RLS Policies

```sql
-- Policy for emails table
CREATE POLICY "client_isolation_emails" ON emails
  FOR SELECT
  USING (client_id = (auth.jwt() ->> 'client_id')::UUID);

-- Policy for email_events table
CREATE POLICY "client_isolation_events" ON email_events
  FOR SELECT
  USING (
    email_id IN (
      SELECT id FROM emails
      WHERE client_id = (auth.jwt() ->> 'client_id')::UUID
    )
  );

-- Optional: Policy for clients table (if needed)
CREATE POLICY "client_own_record" ON clients
  FOR SELECT
  USING (id = (auth.jwt() ->> 'client_id')::UUID);
```

## Step 3: Create Sample Client

Insert a test client:

```sql
INSERT INTO clients (id, slug, name)
VALUES (
  'a1b2c3d4-e5f6-7890-abcd-ef1234567890'::UUID,  -- Use a real UUID
  'test-client',
  'Test Client'
);
```

Make note of the UUID - you'll need it for JWT generation.

## Step 4: Generate JWT Token

### 4.1 Get Project Secret

1. Go to Supabase dashboard → Settings → API
2. Copy "service_role" secret (NOT "anon" key)

### 4.2 Generate JWT with client_id Claim

Use [jwt.io](https://jwt.io/) or Python:

```python
import jwt
from datetime import datetime, timedelta

# Your Supabase project secret
secret = "your-service-role-secret-here"

# Your client UUID from Step 3
client_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Generate JWT
payload = {
    "role": "service_role",
    "client_id": client_id,
    "iat": datetime.utcnow(),
    "exp": datetime.utcnow() + timedelta(days=365)  # 1 year expiry
}

token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
```

Save this JWT - you'll use it in Django settings.

## Step 5: Test Connection

Test your setup with curl:

```bash
curl "https://your-project.supabase.co/rest/v1/emails?select=*&limit=10" \
  -H "apikey: YOUR_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Should return empty array `[]` (no data yet) or existing emails.

## Step 6: Populate Sample Data (Optional)

For testing:

```sql
-- Insert a test email
INSERT INTO emails (client_id, recipient_email, template_name, subject, sent_at, brevo_email_id)
VALUES (
  'a1b2c3d4-e5f6-7890-abcd-ef1234567890'::UUID,
  'test@example.com',
  'welcome-email',
  'Welcome to our platform!',
  NOW() - INTERVAL '1 hour',
  12345678
);

-- Get the email ID
SELECT id FROM emails WHERE recipient_email = 'test@example.com';

-- Insert events for that email
INSERT INTO email_events (email_id, event_type, event_timestamp)
VALUES
  ('email-uuid-here', 'sent', NOW() - INTERVAL '1 hour'),
  ('email-uuid-here', 'delivered', NOW() - INTERVAL '59 minutes'),
  ('email-uuid-here', 'opened', NOW() - INTERVAL '45 minutes');
```

## Step 7: Configure n8n (Optional)

To populate data from Brevo webhooks via n8n:

1. Create n8n workflow triggered by Brevo webhook
2. Parse webhook payload
3. Insert into Supabase tables using credentials
4. Map Brevo event types to our schema

Example n8n node configuration:
- Webhook: Listen for Brevo events
- Function: Transform payload
- Supabase: Insert into emails/email_events

## Verification

1. Check RLS is working:

```sql
-- This should return only your client's emails
SELECT * FROM emails;
```

2. Test JWT claim:

```sql
SELECT auth.jwt() ->> 'client_id';
```

Should return your client UUID.

## Troubleshooting

### "Permission denied" errors

- Verify RLS policies are created
- Check JWT includes `client_id` claim
- Verify `client_id` UUID matches clients table

### "JWT expired" errors

- Generate new JWT with longer expiry
- Update Django settings with new token

### Empty results

- Verify data exists: `SELECT count(*) FROM emails;`
- Check `client_id` in JWT matches data
- Review date range filters

## Security Notes

- Keep service_role secret secure
- JWT should only be in server-side Django settings
- Never expose JWT in frontend code
- Use HTTPS in production
- Rotate JWTs periodically

## Next Steps

- [Installation Guide](INSTALLATION.md) - Install Django package
- [Usage Guide](USAGE.md) - Learn the interface
