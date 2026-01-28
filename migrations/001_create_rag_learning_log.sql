-- RAG Learning Log Table
-- Stores persistent logs of RAG cache interactions for observability
-- Run this in Supabase SQL Editor to create the table

-- Create the table
CREATE TABLE IF NOT EXISTS rag_learning_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query TEXT NOT NULL,
    success BOOLEAN NOT NULL DEFAULT true,
    source VARCHAR(20) NOT NULL CHECK (source IN ('cache', 'llm', 'bypass', 'error')),
    learned BOOLEAN NOT NULL DEFAULT false,
    message TEXT,
    persona VARCHAR(20) DEFAULT 'CFO',
    similarity FLOAT DEFAULT 0.0,
    llm_confidence FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes for common queries
    CONSTRAINT valid_similarity CHECK (similarity >= 0 AND similarity <= 1),
    CONSTRAINT valid_confidence CHECK (llm_confidence >= 0 AND llm_confidence <= 1)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_rag_log_created_at ON rag_learning_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_log_persona ON rag_learning_log(persona);
CREATE INDEX IF NOT EXISTS idx_rag_log_source ON rag_learning_log(source);
CREATE INDEX IF NOT EXISTS idx_rag_log_learned ON rag_learning_log(learned);

-- Enable Row Level Security (RLS)
ALTER TABLE rag_learning_log ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations for authenticated users
-- Adjust this based on your security requirements
CREATE POLICY "Allow all operations for authenticated users"
ON rag_learning_log
FOR ALL
USING (true)
WITH CHECK (true);

-- Optional: Create a function to clean up old entries (keep last 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_rag_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM rag_learning_log
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Optional: Create a view for quick statistics
CREATE OR REPLACE VIEW rag_learning_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_queries,
    COUNT(*) FILTER (WHERE success = true) as successful_queries,
    COUNT(*) FILTER (WHERE learned = true) as queries_learned,
    COUNT(*) FILTER (WHERE source = 'cache' AND success = true) as cache_hits,
    COUNT(*) FILTER (WHERE source = 'llm' AND success = true) as llm_calls,
    ROUND(
        COUNT(*) FILTER (WHERE source = 'cache' AND success = true)::numeric /
        NULLIF(COUNT(*), 0)::numeric * 100, 2
    ) as cache_hit_rate_pct
FROM rag_learning_log
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Comment on table
COMMENT ON TABLE rag_learning_log IS 'Persistent log of RAG cache interactions for NLQ module';
COMMENT ON COLUMN rag_learning_log.source IS 'Source of the response: cache (from RAG), llm (from AI), bypass (special handling), error (failed)';
COMMENT ON COLUMN rag_learning_log.learned IS 'Whether this query was added to the RAG cache for future use';
COMMENT ON COLUMN rag_learning_log.similarity IS 'Similarity score from cache lookup (0-1)';
COMMENT ON COLUMN rag_learning_log.llm_confidence IS 'Confidence score from LLM response (0-1)';
