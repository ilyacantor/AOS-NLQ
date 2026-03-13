-- Maestra tables for engagement lifecycle, scoping sessions, messages, and contour maps.
-- Run against Supabase PostgreSQL.

-- ═══════════════════════════════════════════════════════════════════════════
-- ENGAGEMENTS — top-level container (one per deal)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS maestra_engagements (
    engagement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_name TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT 'scoping' CHECK (phase IN ('scoping', 'execution', 'ongoing_management')),
    entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    objects_in_scope JSONB NOT NULL DEFAULT '["Financial Statements","Customers","Vendors","People","IT"]'::jsonb,
    session_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    stakeholder_map JSONB NOT NULL DEFAULT '{}'::jsonb,
    timeline JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════
-- SESSIONS — per-entity scoping sessions
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS maestra_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID REFERENCES maestra_engagements(engagement_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'READY' CHECK (status IN (
        'INTEL_GATHERING', 'PREMEET_SENT', 'READY', 'IN_PROGRESS', 'PAUSED', 'COMPLETE'
    )),
    current_section TEXT NOT NULL DEFAULT '1',
    section_statuses JSONB NOT NULL DEFAULT '{
        "0A": "NOT_STARTED",
        "0B": "NOT_STARTED",
        "1": "NOT_STARTED",
        "2": "NOT_STARTED",
        "3": "NOT_STARTED",
        "4": "NOT_STARTED",
        "5": "NOT_STARTED"
    }'::jsonb,
    contour_map JSONB NOT NULL DEFAULT '{}'::jsonb,
    intel_brief JSONB,
    demo_phase TEXT,
    customer_name TEXT NOT NULL DEFAULT '',
    stakeholder_name TEXT NOT NULL DEFAULT '',
    stakeholder_role TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maestra_sessions_engagement
    ON maestra_sessions(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- MESSAGES — conversation history
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS maestra_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES maestra_sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('agent', 'stakeholder', 'system')),
    content TEXT NOT NULL DEFAULT '',
    rich_content JSONB NOT NULL DEFAULT '[]'::jsonb,
    section TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maestra_messages_session
    ON maestra_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_maestra_messages_created
    ON maestra_messages(session_id, created_at);

-- ═══════════════════════════════════════════════════════════════════════════
-- CONTOUR MAPS — enterprise contour maps (one per entity per engagement)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS contour_maps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES maestra_engagements(engagement_id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    contour_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    completeness_score FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(engagement_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_contour_maps_engagement
    ON contour_maps(engagement_id);
