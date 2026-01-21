-- Import email and event data from CSV files into Supabase
-- Prerequisites:
--   1. Run transform_csv_to_supabase.py with correct client_id
--   2. Upload CSV files to accessible location

-- Note: This script uses COPY which requires superuser or specific grants.
-- For Supabase dashboard, use the "Import data from CSV" feature instead.

-- ============================================================
-- Option 1: Using PostgreSQL COPY (requires file system access)
-- ============================================================

-- Import emails
COPY brevo_analytics.emails(
    id,
    client_id,
    brevo_email_id,
    recipient_email,
    template_id,
    template_name,
    subject,
    sent_at,
    tags
)
FROM '/path/to/emails_import.csv'
WITH (
    FORMAT CSV,
    HEADER true,
    NULL '',
    ENCODING 'UTF8'
);

-- Import events
COPY brevo_analytics.email_events(
    id,
    email_id,
    event_type,
    event_timestamp,
    bounce_type,
    bounce_reason,
    click_url
)
FROM '/path/to/email_events_import.csv'
WITH (
    FORMAT CSV,
    HEADER true,
    NULL '',
    ENCODING 'UTF8'
);

-- ============================================================
-- Option 2: Using \copy (psql client-side copy)
-- ============================================================

-- From psql command line:
-- \copy brevo_analytics.emails(id, client_id, brevo_email_id, recipient_email, template_id, template_name, subject, sent_at, tags) FROM 'emails_import.csv' WITH (FORMAT CSV, HEADER true, NULL '', ENCODING 'UTF8');
-- \copy brevo_analytics.email_events(id, email_id, event_type, event_timestamp, bounce_type, bounce_reason, click_url) FROM 'email_events_import.csv' WITH (FORMAT CSV, HEADER true, NULL '', ENCODING 'UTF8');

-- ============================================================
-- Option 3: Supabase Dashboard Import (Recommended)
-- ============================================================

/*
1. Go to Supabase Dashboard → Table Editor
2. Select brevo_analytics.emails table
3. Click "Insert" → "Import data from CSV"
4. Upload emails_import.csv
5. Map columns (should auto-detect)
6. Import

7. Select brevo_analytics.email_events table
8. Click "Insert" → "Import data from CSV"
9. Upload email_events_import.csv
10. Map columns (should auto-detect)
11. Import
*/

-- ============================================================
-- Verification Queries
-- ============================================================

-- Check email count
SELECT COUNT(*) as email_count
FROM brevo_analytics.emails;

-- Check event count
SELECT COUNT(*) as event_count
FROM brevo_analytics.email_events;

-- Check event distribution
SELECT
    event_type,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM brevo_analytics.email_events
GROUP BY event_type
ORDER BY count DESC;

-- Check date range
SELECT
    MIN(sent_at) as oldest_email,
    MAX(sent_at) as newest_email,
    COUNT(*) as total_emails
FROM brevo_analytics.emails;

-- Check for orphaned events (events without email)
SELECT COUNT(*)
FROM brevo_analytics.email_events e
LEFT JOIN brevo_analytics.emails em ON e.email_id = em.id
WHERE em.id IS NULL;

-- Top 10 recipients by email count
SELECT
    recipient_email,
    COUNT(*) as email_count
FROM brevo_analytics.emails
GROUP BY recipient_email
ORDER BY email_count DESC
LIMIT 10;

-- Events per email statistics
SELECT
    AVG(event_count) as avg_events_per_email,
    MIN(event_count) as min_events,
    MAX(event_count) as max_events
FROM (
    SELECT
        email_id,
        COUNT(*) as event_count
    FROM brevo_analytics.email_events
    GROUP BY email_id
) stats;

-- ============================================================
-- Cleanup (if needed to re-import)
-- ============================================================

-- WARNING: This will delete all data!
-- DELETE FROM brevo_analytics.email_events;
-- DELETE FROM brevo_analytics.emails;
