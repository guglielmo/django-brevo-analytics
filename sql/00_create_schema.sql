-- ============================================================================
-- Brevo Analytics - Schema Creation
-- ============================================================================
-- Create a dedicated schema to keep Brevo Analytics tables separate
-- Project: https://supabase.com/dashboard/project/fvuhpocdeckmbdgiebfy
-- ============================================================================

-- Create the schema
CREATE SCHEMA IF NOT EXISTS brevo_analytics;

-- Grant usage to authenticated and service_role
GRANT USAGE ON SCHEMA brevo_analytics TO authenticated, service_role, anon;

-- Grant all privileges on future tables in this schema
ALTER DEFAULT PRIVILEGES IN SCHEMA brevo_analytics
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA brevo_analytics
    GRANT SELECT ON TABLES TO authenticated;

-- Set search path to include the new schema
-- Note: This only affects the current session
SET search_path TO brevo_analytics, public;

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Schema "brevo_analytics" created!';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Permissions granted:';
    RAISE NOTICE '  - service_role: Full access (for n8n writes)';
    RAISE NOTICE '  - authenticated: SELECT only (for Django reads)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next: Run 01_create_tables.sql';
    RAISE NOTICE '';
END $$;
