-- ============================================================================
-- Brevo Analytics - Database Schema Setup
-- ============================================================================
-- This script creates the required tables for storing Brevo email analytics
-- Run this in your Supabase SQL Editor AFTER 00_create_schema.sql
-- ============================================================================

-- Use the brevo_analytics schema
SET search_path TO brevo_analytics, public;

-- ============================================================================
-- 1. CLIENTS TABLE
-- ============================================================================
-- Stores client information for multi-tenant access control

CREATE TABLE IF NOT EXISTS brevo_analytics.clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster slug lookups
CREATE INDEX IF NOT EXISTS idx_clients_slug ON brevo_analytics.clients(slug);

COMMENT ON TABLE brevo_analytics.clients IS 'Client organizations with access to email analytics';
COMMENT ON COLUMN brevo_analytics.clients.id IS 'Primary key - used in JWT client_id claim for RLS';
COMMENT ON COLUMN brevo_analytics.clients.slug IS 'URL-friendly identifier for the client';

-- ============================================================================
-- 2. EMAILS TABLE
-- ============================================================================
-- Stores individual transactional emails sent via Brevo

CREATE TABLE IF NOT EXISTS brevo_analytics.emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID REFERENCES brevo_analytics.clients(id) ON DELETE CASCADE NOT NULL,
  brevo_email_id BIGINT UNIQUE,  -- Brevo's message ID
  recipient_email TEXT NOT NULL,
  recipient_name TEXT,
  template_name TEXT,
  template_id BIGINT,
  subject TEXT,
  sent_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_emails_client_id ON brevo_analytics.emails(client_id);
CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON brevo_analytics.emails(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_recipient ON brevo_analytics.emails(recipient_email);
CREATE INDEX IF NOT EXISTS idx_emails_brevo_id ON brevo_analytics.emails(brevo_email_id);
CREATE INDEX IF NOT EXISTS idx_emails_subject ON brevo_analytics.emails USING gin(to_tsvector('simple', subject));

COMMENT ON TABLE brevo_analytics.emails IS 'Transactional emails sent through Brevo';
COMMENT ON COLUMN brevo_analytics.emails.brevo_email_id IS 'Brevo message ID from webhooks';
COMMENT ON COLUMN brevo_analytics.emails.sent_at IS 'Timestamp when email was sent by Brevo';

-- ============================================================================
-- 3. EMAIL EVENTS TABLE
-- ============================================================================
-- Stores events for each email (delivered, opened, bounced, etc.)

CREATE TABLE IF NOT EXISTS brevo_analytics.email_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES brevo_analytics.emails(id) ON DELETE CASCADE NOT NULL,
  event_type TEXT NOT NULL,
  event_timestamp TIMESTAMPTZ NOT NULL,

  -- Bounce information
  bounce_type TEXT,  -- 'hard' or 'soft'
  bounce_reason TEXT,  -- Detailed reason from Brevo

  -- Link click information
  click_url TEXT,

  -- Raw event data from Brevo (optional)
  raw_data JSONB,

  created_at TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT valid_event_type CHECK (
    event_type IN ('sent', 'delivered', 'opened', 'clicked', 'bounced', 'unsubscribed', 'blocked', 'spam')
  )
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_events_email_id ON brevo_analytics.email_events(email_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON brevo_analytics.email_events(event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON brevo_analytics.email_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_bounce_type ON brevo_analytics.email_events(bounce_type) WHERE bounce_type IS NOT NULL;

COMMENT ON TABLE brevo_analytics.email_events IS 'Event timeline for each email';
COMMENT ON COLUMN brevo_analytics.email_events.event_type IS 'Type of event: sent, delivered, opened, clicked, bounced, etc.';
COMMENT ON COLUMN brevo_analytics.email_events.bounce_type IS 'hard or soft bounce';
COMMENT ON COLUMN brevo_analytics.email_events.raw_data IS 'Original webhook payload from Brevo (optional)';

-- ============================================================================
-- 4. UPDATED_AT TRIGGERS
-- ============================================================================
-- Automatically update updated_at timestamps

CREATE OR REPLACE FUNCTION brevo_analytics.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_clients_updated_at BEFORE UPDATE ON brevo_analytics.clients
    FOR EACH ROW EXECUTE FUNCTION brevo_analytics.update_updated_at_column();

CREATE TRIGGER update_emails_updated_at BEFORE UPDATE ON brevo_analytics.emails
    FOR EACH ROW EXECUTE FUNCTION brevo_analytics.update_updated_at_column();

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Tables created in brevo_analytics schema!';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - brevo_analytics.clients';
    RAISE NOTICE '  - brevo_analytics.emails';
    RAISE NOTICE '  - brevo_analytics.email_events';
    RAISE NOTICE '';
    RAISE NOTICE 'Next: Run 02_enable_rls.sql';
    RAISE NOTICE '';
END $$;
