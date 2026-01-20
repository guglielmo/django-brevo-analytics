-- ============================================================================
-- Brevo Analytics - Row Level Security (RLS) Setup
-- ============================================================================
-- This script enables RLS and creates policies for multi-tenant isolation
-- Each client can only see their own emails and events
-- ============================================================================

-- Use the brevo_analytics schema
SET search_path TO brevo_analytics, public;

-- ============================================================================
-- 1. ENABLE RLS ON ALL TABLES
-- ============================================================================

ALTER TABLE brevo_analytics.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE brevo_analytics.emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE brevo_analytics.email_events ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 2. DROP EXISTING POLICIES (if re-running)
-- ============================================================================

DROP POLICY IF EXISTS "client_isolation_emails" ON brevo_analytics.emails;
DROP POLICY IF EXISTS "client_isolation_events" ON brevo_analytics.email_events;
DROP POLICY IF EXISTS "client_own_record" ON brevo_analytics.clients;

-- ============================================================================
-- 3. CREATE RLS POLICIES
-- ============================================================================

-- Policy: Clients can only see their own emails
CREATE POLICY "client_isolation_emails" ON brevo_analytics.emails
  FOR SELECT
  USING (client_id = (auth.jwt() ->> 'client_id')::UUID);

COMMENT ON POLICY "client_isolation_emails" ON brevo_analytics.emails IS
  'Clients can only SELECT emails where client_id matches JWT claim';

-- Policy: Clients can only see events for their own emails
CREATE POLICY "client_isolation_events" ON brevo_analytics.email_events
  FOR SELECT
  USING (
    email_id IN (
      SELECT id FROM brevo_analytics.emails
      WHERE client_id = (auth.jwt() ->> 'client_id')::UUID
    )
  );

COMMENT ON POLICY "client_isolation_events" ON brevo_analytics.email_events IS
  'Clients can only SELECT events for emails they own';

-- Policy: Clients can see their own client record (optional)
CREATE POLICY "client_own_record" ON brevo_analytics.clients
  FOR SELECT
  USING (id = (auth.jwt() ->> 'client_id')::UUID);

COMMENT ON POLICY "client_own_record" ON brevo_analytics.clients IS
  'Clients can SELECT their own client record';

-- ============================================================================
-- 4. GRANT PERMISSIONS FOR SERVICE ROLE
-- ============================================================================
-- service_role bypasses RLS (for n8n inserts)

-- ============================================================================
-- 5. VERIFY RLS IS ENABLED
-- ============================================================================

DO $$
DECLARE
    rls_enabled_count INT;
BEGIN
    SELECT COUNT(*) INTO rls_enabled_count
    FROM pg_tables
    WHERE schemaname = 'brevo_analytics'
      AND tablename IN ('clients', 'emails', 'email_events')
      AND rowsecurity = true;

    IF rls_enabled_count = 3 THEN
        RAISE NOTICE '';
        RAISE NOTICE '========================================';
        RAISE NOTICE '✅ Row Level Security enabled on all tables!';
        RAISE NOTICE '========================================';
        RAISE NOTICE '';
        RAISE NOTICE 'Schema: brevo_analytics';
        RAISE NOTICE 'Policies created:';
        RAISE NOTICE '  - client_isolation_emails';
        RAISE NOTICE '  - client_isolation_events';
        RAISE NOTICE '  - client_own_record';
        RAISE NOTICE '';
        RAISE NOTICE 'Next: Run 03_create_test_data.sql';
        RAISE NOTICE '';
    ELSE
        RAISE WARNING '❌ RLS not enabled on all tables. Count: %', rls_enabled_count;
    END IF;
END $$;
