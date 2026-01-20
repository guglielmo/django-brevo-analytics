-- ============================================================================
-- Brevo Analytics - Sample Email Data
-- ============================================================================
-- This script inserts sample emails and events for testing
-- Run this AFTER creating the test client (03_create_test_data.sql)
-- ============================================================================

-- Use the brevo_analytics schema
SET search_path TO brevo_analytics, public;

-- Get the client ID
DO $$
DECLARE
    v_client_id UUID;
    v_email_id_1 UUID;
    v_email_id_2 UUID;
    v_email_id_3 UUID;
    v_email_id_4 UUID;
    v_email_id_5 UUID;
BEGIN
    -- Get client ID
    SELECT id INTO v_client_id FROM brevo_analytics.clients WHERE slug = 'infoparlamento';

    IF v_client_id IS NULL THEN
        RAISE EXCEPTION 'Client "infoparlamento" not found. Run 03_create_test_data.sql first.';
    END IF;

    RAISE NOTICE 'Using client_id: %', v_client_id;

    -- ========================================================================
    -- 1. INSERT SAMPLE EMAILS
    -- ========================================================================

    -- Email 1: Successfully delivered and opened
    INSERT INTO brevo_analytics.emails (id, client_id, brevo_email_id, recipient_email, recipient_name, template_name, template_id, subject, sent_at)
    VALUES (
        gen_random_uuid(),
        v_client_id,
        10001,
        'mario.rossi@example.com',
        'Mario Rossi',
        'newsletter-weekly',
        101,
        'Weekly Update - January 2026',
        NOW() - INTERVAL '2 hours'
    )
    RETURNING id INTO v_email_id_1;

    -- Email 2: Delivered and clicked link
    INSERT INTO brevo_analytics.emails (id, client_id, brevo_email_id, recipient_email, recipient_name, template_name, template_id, subject, sent_at)
    VALUES (
        gen_random_uuid(),
        v_client_id,
        10002,
        'giulia.bianchi@example.com',
        'Giulia Bianchi',
        'alert-notification',
        102,
        'Important: New Parliamentary Vote',
        NOW() - INTERVAL '5 hours'
    )
    RETURNING id INTO v_email_id_2;

    -- Email 3: Hard bounce
    INSERT INTO brevo_analytics.emails (id, client_id, brevo_email_id, recipient_email, recipient_name, template_name, template_id, subject, sent_at)
    VALUES (
        gen_random_uuid(),
        v_client_id,
        10003,
        'invalid@nonexistent-domain-123456.com',
        'Test User',
        'welcome-email',
        103,
        'Welcome to Infoparlamento',
        NOW() - INTERVAL '1 day'
    )
    RETURNING id INTO v_email_id_3;

    -- Email 4: Soft bounce (mailbox full)
    INSERT INTO brevo_analytics.emails (id, client_id, brevo_email_id, recipient_email, recipient_name, template_name, template_id, subject, sent_at)
    VALUES (
        gen_random_uuid(),
        v_client_id,
        10004,
        'luca.verdi@example.com',
        'Luca Verdi',
        'newsletter-weekly',
        101,
        'Weekly Update - January 2026',
        NOW() - INTERVAL '3 days'
    )
    RETURNING id INTO v_email_id_4;

    -- Email 5: Recently sent, not delivered yet
    INSERT INTO brevo_analytics.emails (id, client_id, brevo_email_id, recipient_email, recipient_name, template_name, template_id, subject, sent_at)
    VALUES (
        gen_random_uuid(),
        v_client_id,
        10005,
        'anna.ferrari@example.com',
        'Anna Ferrari',
        'password-reset',
        104,
        'Reset Your Password',
        NOW() - INTERVAL '10 minutes'
    )
    RETURNING id INTO v_email_id_5;

    -- ========================================================================
    -- 2. INSERT EMAIL EVENTS
    -- ========================================================================

    -- Events for Email 1: Successful delivery and open
    INSERT INTO brevo_analytics.email_events (email_id, event_type, event_timestamp) VALUES
        (v_email_id_1, 'sent', NOW() - INTERVAL '2 hours'),
        (v_email_id_1, 'delivered', NOW() - INTERVAL '1 hour 58 minutes'),
        (v_email_id_1, 'opened', NOW() - INTERVAL '1 hour 30 minutes');

    -- Events for Email 2: Delivery, open, and click
    INSERT INTO brevo_analytics.email_events (email_id, event_type, event_timestamp, click_url) VALUES
        (v_email_id_2, 'sent', NOW() - INTERVAL '5 hours'),
        (v_email_id_2, 'delivered', NOW() - INTERVAL '4 hours 58 minutes'),
        (v_email_id_2, 'opened', NOW() - INTERVAL '4 hours 30 minutes'),
        (v_email_id_2, 'clicked', NOW() - INTERVAL '4 hours 25 minutes', 'https://infoparlamento.it/votes/2026-01-vote-123');

    -- Events for Email 3: Hard bounce
    INSERT INTO brevo_analytics.email_events (email_id, event_type, event_timestamp, bounce_type, bounce_reason) VALUES
        (v_email_id_3, 'sent', NOW() - INTERVAL '1 day'),
        (v_email_id_3, 'bounced', NOW() - INTERVAL '1 day' + INTERVAL '2 minutes', 'hard', 'Domain does not exist (SMTP 550)');

    -- Events for Email 4: Soft bounce
    INSERT INTO brevo_analytics.email_events (email_id, event_type, event_timestamp, bounce_type, bounce_reason) VALUES
        (v_email_id_4, 'sent', NOW() - INTERVAL '3 days'),
        (v_email_id_4, 'bounced', NOW() - INTERVAL '3 days' + INTERVAL '5 minutes', 'soft', 'Mailbox full (SMTP 452)');

    -- Events for Email 5: Just sent
    INSERT INTO brevo_analytics.email_events (email_id, event_type, event_timestamp) VALUES
        (v_email_id_5, 'sent', NOW() - INTERVAL '10 minutes');

    -- ========================================================================
    -- 3. VERIFICATION
    -- ========================================================================

    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Sample data inserted successfully!';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE '📊 Summary:';
    RAISE NOTICE '   - 5 test emails inserted';
    RAISE NOTICE '   - 12 events inserted';
    RAISE NOTICE '';
    RAISE NOTICE '📧 Test scenarios:';
    RAISE NOTICE '   1. mario.rossi@example.com - Delivered and opened';
    RAISE NOTICE '   2. giulia.bianchi@example.com - Delivered, opened, clicked';
    RAISE NOTICE '   3. invalid@nonexistent... - Hard bounce';
    RAISE NOTICE '   4. luca.verdi@example.com - Soft bounce (mailbox full)';
    RAISE NOTICE '   5. anna.ferrari@example.com - Just sent (no delivery yet)';
    RAISE NOTICE '';
    RAISE NOTICE '✅ Ready to test Django admin interface!';
    RAISE NOTICE '';

END $$;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- View all emails
SELECT
    e.brevo_email_id,
    e.recipient_email,
    e.subject,
    e.sent_at,
    COUNT(ev.id) as event_count
FROM brevo_analytics.emails e
LEFT JOIN brevo_analytics.email_events ev ON ev.email_id = e.id
GROUP BY e.id, e.brevo_email_id, e.recipient_email, e.subject, e.sent_at
ORDER BY e.sent_at DESC;

-- View bounced emails
SELECT
    e.recipient_email,
    e.subject,
    ev.bounce_type,
    ev.bounce_reason,
    ev.event_timestamp
FROM brevo_analytics.emails e
JOIN brevo_analytics.email_events ev ON ev.email_id = e.id
WHERE ev.event_type = 'bounced'
ORDER BY ev.event_timestamp DESC;

-- View delivery stats (last 7 days)
SELECT
    COUNT(DISTINCT e.id) FILTER (WHERE ev.event_type = 'sent') as sent,
    COUNT(DISTINCT e.id) FILTER (WHERE ev.event_type = 'delivered') as delivered,
    COUNT(DISTINCT e.id) FILTER (WHERE ev.event_type = 'bounced') as bounced,
    COUNT(DISTINCT e.id) FILTER (WHERE ev.event_type = 'opened') as opened,
    COUNT(DISTINCT e.id) FILTER (WHERE ev.event_type = 'clicked') as clicked
FROM brevo_analytics.emails e
LEFT JOIN brevo_analytics.email_events ev ON ev.email_id = e.id
WHERE e.sent_at >= NOW() - INTERVAL '7 days';
