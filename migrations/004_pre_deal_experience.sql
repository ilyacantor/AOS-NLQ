-- Pre-Deal Experience migration.
-- Adds mode, pre_deal_context to engagements.
-- Relaxes phase CHECK to include pre-deal phases.
-- Relaxes current_section to accept PDx section IDs.

-- ═══════════════════════════════════════════════════════════════════════════
-- ENGAGEMENTS: add mode and pre_deal_context columns, update phase CHECK
-- ═══════════════════════════════════════════════════════════════════════════

-- Add mode column
ALTER TABLE maestra_engagements
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'pre_deal';

-- Add pre_deal_context column
ALTER TABLE maestra_engagements
    ADD COLUMN IF NOT EXISTS pre_deal_context JSONB;

-- Drop old phase CHECK and add expanded one
ALTER TABLE maestra_engagements
    DROP CONSTRAINT IF EXISTS maestra_engagements_phase_check;

ALTER TABLE maestra_engagements
    ADD CONSTRAINT maestra_engagements_phase_check
    CHECK (phase IN (
        'prework_running', 'prework_complete',
        'scoping',
        'analysis_running', 'analysis_complete',
        'findings',
        'execution', 'ongoing_management'
    ));
