-- Migration 002: Add normalized_query + execution_time_ms columns, indexes, and RLS fix
-- Purpose: Support server-side dedup for History tab and execution timing
-- Run this in Supabase SQL Editor after 001_create_rag_learning_log.sql
--
-- STATUS: Applied 2026-03-03 against yuxrdoamtjmodjzqpeds
--   - Columns already existed (created with table); backfilled 832 rows
--   - 2 indexes created; RLS permissive policy added for anon role

-- Add normalized_query column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rag_learning_log' AND column_name = 'normalized_query'
    ) THEN
        ALTER TABLE rag_learning_log ADD COLUMN normalized_query TEXT;
        RAISE NOTICE 'Added normalized_query column';
    END IF;
END $$;

-- Add execution_time_ms column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rag_learning_log' AND column_name = 'execution_time_ms'
    ) THEN
        ALTER TABLE rag_learning_log ADD COLUMN execution_time_ms INTEGER;
        RAISE NOTICE 'Added execution_time_ms column';
    END IF;
END $$;

-- Add tenant_id column if it doesn't exist (older deployments may lack this)
-- NOTE: actual column type is UUID (matches existing schema), not TEXT
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rag_learning_log' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE rag_learning_log ADD COLUMN tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001';
        RAISE NOTICE 'Added tenant_id column';
    END IF;
END $$;

-- Backfill normalized_query for existing rows that don't have it
UPDATE rag_learning_log
SET normalized_query = LOWER(TRIM(REGEXP_REPLACE(query, '\s+', ' ', 'g')))
WHERE normalized_query IS NULL;

-- Composite index for efficient history queries:
-- Supports GROUP BY normalized_query with tenant_id filter, ordered by recency
CREATE INDEX IF NOT EXISTS idx_rag_log_tenant_normalized_created
ON rag_learning_log (tenant_id, normalized_query, created_at DESC);

-- Index for retention cleanup (DELETE WHERE created_at < cutoff)
CREATE INDEX IF NOT EXISTS idx_rag_log_created_at_asc
ON rag_learning_log (created_at ASC);

-- Fix RLS: ensure anon role can read/write (the app uses anon key, not service_role)
-- Without this, all Supabase REST API writes via anon key are silently rejected
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policy
        WHERE polname = 'Allow all operations'
        AND polrelid = 'rag_learning_log'::regclass
    ) THEN
        CREATE POLICY "Allow all operations" ON rag_learning_log
        FOR ALL USING (true) WITH CHECK (true);
        RAISE NOTICE 'Created permissive RLS policy for all roles';
    END IF;
END $$;

-- Comment updates
COMMENT ON COLUMN rag_learning_log.normalized_query IS 'Lowercased, whitespace-collapsed query for deduplication grouping';
COMMENT ON COLUMN rag_learning_log.execution_time_ms IS 'Wall-clock query execution time in milliseconds';
