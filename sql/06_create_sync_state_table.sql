-- Create sync_state table to track last synchronization from Brevo API
-- This enables differential/incremental sync instead of full sync every time

CREATE TABLE IF NOT EXISTS brevo_analytics.sync_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,

    -- Sync tracking
    sync_type VARCHAR(50) NOT NULL, -- 'emails' or 'events'
    last_sync_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_successful_sync_at TIMESTAMPTZ,

    -- Range tracking (for incremental sync)
    last_synced_start_date TIMESTAMPTZ,
    last_synced_end_date TIMESTAMPTZ,

    -- Status and metrics
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'running', 'success', 'error'
    records_synced INTEGER DEFAULT 0,
    error_message TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure unique sync_type per client
    UNIQUE(client_id, sync_type)
);

-- Add RLS policies for sync_state
ALTER TABLE brevo_analytics.sync_state ENABLE ROW LEVEL SECURITY;

-- Service role can do everything
CREATE POLICY "Service role has full access to sync_state"
    ON brevo_analytics.sync_state
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Authenticated users can only see their client's sync state
CREATE POLICY "Users can view their client sync_state"
    ON brevo_analytics.sync_state
    FOR SELECT
    TO authenticated
    USING (client_id::text = current_setting('request.jwt.claims', true)::json->>'client_id');

-- Create index for faster lookups
CREATE INDEX idx_sync_state_client_type ON brevo_analytics.sync_state(client_id, sync_type);
CREATE INDEX idx_sync_state_status ON brevo_analytics.sync_state(status);
CREATE INDEX idx_sync_state_last_sync ON brevo_analytics.sync_state(last_sync_at DESC);

-- Add trigger to update updated_at
CREATE OR REPLACE FUNCTION brevo_analytics.update_sync_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_state_updated_at
    BEFORE UPDATE ON brevo_analytics.sync_state
    FOR EACH ROW
    EXECUTE FUNCTION brevo_analytics.update_sync_state_updated_at();

-- Grant permissions
GRANT SELECT ON brevo_analytics.sync_state TO authenticated, anon;
GRANT ALL ON brevo_analytics.sync_state TO service_role;

COMMENT ON TABLE brevo_analytics.sync_state IS 'Tracks last synchronization state from Brevo API for incremental updates';
COMMENT ON COLUMN brevo_analytics.sync_state.sync_type IS 'Type of sync: emails or events';
COMMENT ON COLUMN brevo_analytics.sync_state.last_sync_at IS 'When sync was last attempted';
COMMENT ON COLUMN brevo_analytics.sync_state.last_successful_sync_at IS 'When sync last completed successfully';
COMMENT ON COLUMN brevo_analytics.sync_state.last_synced_start_date IS 'Start date of last successful sync range';
COMMENT ON COLUMN brevo_analytics.sync_state.last_synced_end_date IS 'End date of last successful sync range';
