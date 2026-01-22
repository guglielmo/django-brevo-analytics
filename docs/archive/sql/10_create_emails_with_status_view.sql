-- ============================================================================
-- Migration: Create emails_with_status view for efficient status calculation
-- ============================================================================
-- This view pre-calculates the current_status for each email using a single
-- JOIN and GROUP BY, eliminating the need for multiple API calls from Django.
-- The view respects RLS policies since it's based on the emails table.
-- ============================================================================

SET search_path TO brevo_analytics, public;

-- Drop view if exists
DROP VIEW IF EXISTS brevo_analytics.emails_with_status;

-- Create view with status calculation
-- Status hierarchy (highest to lowest priority):
--   clicked > opened > delivered > bounced > blocked > deferred > unsubscribed > sent
CREATE OR REPLACE VIEW brevo_analytics.emails_with_status AS
SELECT
  e.id,
  e.client_id,
  e.brevo_email_id,
  e.recipient_email,
  e.subject,
  e.sent_at,
  e.created_at,
  e.updated_at,
  -- Calculate current_status using event type hierarchy
  CASE
    WHEN MAX(CASE WHEN ev.event_type = 'clicked' THEN 1 ELSE 0 END) = 1 THEN 'clicked'
    WHEN MAX(CASE WHEN ev.event_type = 'opened' THEN 1 ELSE 0 END) = 1 THEN 'opened'
    WHEN MAX(CASE WHEN ev.event_type = 'delivered' THEN 1 ELSE 0 END) = 1 THEN 'delivered'
    WHEN MAX(CASE WHEN ev.event_type = 'bounced' THEN 1 ELSE 0 END) = 1 THEN 'bounced'
    WHEN MAX(CASE WHEN ev.event_type = 'blocked' THEN 1 ELSE 0 END) = 1 THEN 'blocked'
    WHEN MAX(CASE WHEN ev.event_type = 'deferred' THEN 1 ELSE 0 END) = 1 THEN 'deferred'
    WHEN MAX(CASE WHEN ev.event_type = 'unsubscribed' THEN 1 ELSE 0 END) = 1 THEN 'unsubscribed'
    ELSE 'sent'
  END AS current_status
FROM brevo_analytics.emails e
LEFT JOIN brevo_analytics.email_events ev ON ev.email_id = e.id
GROUP BY e.id, e.client_id, e.brevo_email_id, e.recipient_email, e.subject, e.sent_at, e.created_at, e.updated_at;

-- Add comment
COMMENT ON VIEW brevo_analytics.emails_with_status IS
  'Emails with pre-calculated current_status. Much more efficient than calculating status in application code.';

-- Grant select permissions (views inherit base table RLS policies)
-- RLS will still be enforced based on client_id from the emails table

-- Success message
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Created emails_with_status view';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'View includes:';
    RAISE NOTICE '  - All columns from emails table';
    RAISE NOTICE '  - current_status (calculated from events)';
    RAISE NOTICE '';
    RAISE NOTICE 'Status hierarchy:';
    RAISE NOTICE '  1. clicked (highest priority)';
    RAISE NOTICE '  2. opened';
    RAISE NOTICE '  3. delivered';
    RAISE NOTICE '  4. bounced';
    RAISE NOTICE '  5. blocked';
    RAISE NOTICE '  6. deferred';
    RAISE NOTICE '  7. unsubscribed';
    RAISE NOTICE '  8. sent (default)';
    RAISE NOTICE '';
    RAISE NOTICE 'Benefits:';
    RAISE NOTICE '  - Single query instead of emails + events';
    RAISE NOTICE '  - Status calculated by PostgreSQL (fast!)';
    RAISE NOTICE '  - Easy to cache in Django';
    RAISE NOTICE '  - RLS still enforced via base table';
    RAISE NOTICE '';
END $$;
