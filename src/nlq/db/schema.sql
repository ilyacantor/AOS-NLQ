-- =============================================================================
-- RAG Persistence Schema for AOS-NLQ
-- Multi-tenant design with Row-Level Security (RLS)
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- TENANTS TABLE
-- Stores tenant/organization information for multi-tenancy
-- =============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for tenant lookup by slug
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);

-- =============================================================================
-- RAG_SESSIONS TABLE
-- Tracks user sessions with LLM call counts and cache statistics
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    user_id TEXT,
    call_count INTEGER DEFAULT 0,
    queries_cached INTEGER DEFAULT 0,
    queries_learned INTEGER DEFAULT 0,
    first_call_at TIMESTAMPTZ,
    last_call_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, session_id)
);

-- Indexes for session queries
CREATE INDEX IF NOT EXISTS idx_rag_sessions_tenant ON rag_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_sessions_session ON rag_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_rag_sessions_last_call ON rag_sessions(last_call_at);

-- =============================================================================
-- RAG_LEARNING_LOG TABLE
-- Stores query learning history for RAG improvements
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_learning_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT,
    query TEXT NOT NULL,
    normalized_query TEXT,
    success BOOLEAN DEFAULT true,
    source TEXT DEFAULT 'llm',
    learned BOOLEAN DEFAULT false,
    message TEXT,
    persona TEXT,
    similarity FLOAT,
    llm_confidence FLOAT,
    parsed_intent JSONB,
    execution_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for learning log queries
CREATE INDEX IF NOT EXISTS idx_rag_learning_tenant ON rag_learning_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_learning_session ON rag_learning_log(session_id);
CREATE INDEX IF NOT EXISTS idx_rag_learning_created ON rag_learning_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_learning_persona ON rag_learning_log(tenant_id, persona);

-- =============================================================================
-- RAG_CACHE_ENTRIES TABLE
-- Local cache entries (backup to Pinecone, or standalone mode)
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_cache_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    query_hash TEXT NOT NULL,
    original_query TEXT NOT NULL,
    normalized_query TEXT,
    parsed_intent JSONB NOT NULL,
    persona TEXT,
    confidence FLOAT DEFAULT 1.0,
    hit_count INTEGER DEFAULT 0,
    source TEXT DEFAULT 'llm',
    fact_base_version TEXT,
    embedding_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    
    UNIQUE(tenant_id, query_hash)
);

-- Indexes for cache lookups
CREATE INDEX IF NOT EXISTS idx_rag_cache_tenant ON rag_cache_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_cache_hash ON rag_cache_entries(query_hash);
CREATE INDEX IF NOT EXISTS idx_rag_cache_persona ON rag_cache_entries(tenant_id, persona);

-- =============================================================================
-- RAG_FEEDBACK TABLE
-- User feedback on query results for learning
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT,
    query TEXT NOT NULL,
    response_summary TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback_type TEXT,
    feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_feedback_tenant ON rag_feedback(tenant_id);

-- =============================================================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- Ensures tenant isolation at the database level
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE rag_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_learning_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_cache_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_feedback ENABLE ROW LEVEL SECURITY;

-- Create policies for rag_sessions
CREATE POLICY rag_sessions_tenant_isolation ON rag_sessions
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Create policies for rag_learning_log
CREATE POLICY rag_learning_log_tenant_isolation ON rag_learning_log
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Create policies for rag_cache_entries
CREATE POLICY rag_cache_entries_tenant_isolation ON rag_cache_entries
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Create policies for rag_feedback
CREATE POLICY rag_feedback_tenant_isolation ON rag_feedback
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- =============================================================================
-- SERVICE ROLE BYPASS POLICY
-- Allows service role to access all tenant data (for admin operations)
-- =============================================================================
CREATE POLICY rag_sessions_service_role ON rag_sessions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY rag_learning_log_service_role ON rag_learning_log
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY rag_cache_entries_service_role ON rag_cache_entries
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY rag_feedback_service_role ON rag_feedback
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- UPDATED_AT TRIGGER
-- Automatically updates updated_at timestamp on row changes
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_rag_sessions_updated_at
    BEFORE UPDATE ON rag_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_rag_cache_entries_updated_at
    BEFORE UPDATE ON rag_cache_entries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- DEFAULT TENANT
-- Create a default tenant for single-tenant deployments
-- =============================================================================
INSERT INTO tenants (id, name, slug, settings)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Default',
    'default',
    '{"tier": "free", "max_sessions": 1000}'
)
ON CONFLICT (slug) DO NOTHING;

-- =============================================================================
-- OPTIONAL: TABLE PARTITIONING FOR SCALE
-- Uncomment to partition rag_learning_log by month
-- =============================================================================
-- CREATE TABLE rag_learning_log_partitioned (
--     LIKE rag_learning_log INCLUDING ALL
-- ) PARTITION BY RANGE (created_at);
-- 
-- CREATE TABLE rag_learning_log_2025_01 PARTITION OF rag_learning_log_partitioned
--     FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
-- CREATE TABLE rag_learning_log_2025_02 PARTITION OF rag_learning_log_partitioned
--     FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
-- ... add more partitions as needed
