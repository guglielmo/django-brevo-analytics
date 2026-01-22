-- ============================================================================
-- Migration: Add 'deferred' to valid_event_type constraint
-- ============================================================================
-- The CSV import includes 'deferred' events (from "Rinviata" in Brevo)
-- but the original schema didn't include it in the constraint
-- ============================================================================

SET search_path TO brevo_analytics, public;

-- Drop old constraint
ALTER TABLE brevo_analytics.email_events
  DROP CONSTRAINT IF EXISTS valid_event_type;

-- Add new constraint with 'deferred' included
ALTER TABLE brevo_analytics.email_events
  ADD CONSTRAINT valid_event_type CHECK (
    event_type IN (
      'sent',
      'delivered',
      'opened',
      'clicked',
      'bounced',
      'unsubscribed',
      'blocked',
      'spam',
      'deferred'
    )
  );

-- Success message
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Added deferred to valid_event_type constraint';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Valid event types:';
    RAISE NOTICE '  - sent';
    RAISE NOTICE '  - delivered';
    RAISE NOTICE '  - opened';
    RAISE NOTICE '  - clicked';
    RAISE NOTICE '  - bounced';
    RAISE NOTICE '  - unsubscribed';
    RAISE NOTICE '  - blocked';
    RAISE NOTICE '  - spam';
    RAISE NOTICE '  - deferred  (NEW)';
    RAISE NOTICE '';
END $$;
