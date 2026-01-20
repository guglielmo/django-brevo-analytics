-- ============================================================================
-- Brevo Analytics - Test Client Creation
-- ============================================================================
-- This script creates a test client for infoparlamento
-- ============================================================================

-- Use the brevo_analytics schema
SET search_path TO brevo_analytics, public;

-- ============================================================================
-- 1. INSERT TEST CLIENT
-- ============================================================================
-- IMPORTANT: Note the UUID generated - you'll need it for JWT generation!

INSERT INTO brevo_analytics.clients (id, slug, name)
VALUES (
  gen_random_uuid(),
  'infoparlamento',
  'Infoparlamento'
)
ON CONFLICT (slug) DO UPDATE
  SET name = EXCLUDED.name,
      updated_at = NOW()
RETURNING
  id AS client_id,
  slug,
  name,
  '⚠️  SAVE THIS UUID - needed for JWT generation!' AS note;

-- Get the client ID for use in next steps
DO $$
DECLARE
    v_client_id UUID;
BEGIN
    SELECT id INTO v_client_id FROM brevo_analytics.clients WHERE slug = 'infoparlamento';
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Client created successfully!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Client ID: %', v_client_id;
    RAISE NOTICE 'Slug: infoparlamento';
    RAISE NOTICE '';
    RAISE NOTICE '🔑 IMPORTANT: Save this Client ID!';
    RAISE NOTICE 'You will need it to generate the JWT token.';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  1. Copy the Client ID above';
    RAISE NOTICE '  2. Run: python 04_generate_jwt.py';
    RAISE NOTICE '  3. (Optional) Run 05_insert_sample_emails.sql for test data';
    RAISE NOTICE '';
END $$;

-- ============================================================================
-- 2. VERIFICATION QUERY
-- ============================================================================
-- Run this to verify the client was created

SELECT
    id,
    slug,
    name,
    created_at
FROM brevo_analytics.clients
WHERE slug = 'infoparlamento';
