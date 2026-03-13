-- Maestra Schema Migration
-- Creates dedicated schema and tables for Maestra engagement state
-- Run against existing Supabase instance used by DCL/NLQ

-- Schema
CREATE SCHEMA IF NOT EXISTS maestra;

-- Customer Engagements: one row per customer
CREATE TABLE maestra.customer_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    scenario_type TEXT NOT NULL CHECK (scenario_type IN ('single', 'multi', 'convergence', 'portfolio')),
    deal_phase TEXT NOT NULL DEFAULT 'discovery' CHECK (deal_phase IN ('discovery', 'connection', 'semantic_mapping', 'analysis', 'integration_monitoring')),
    onboarding_complete BOOLEAN NOT NULL DEFAULT false,
    acquirer_entity TEXT,           -- for convergence: acquirer name
    target_entity TEXT,             -- for convergence: target name
    last_interaction_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Session Memory: structured interaction records, not raw conversation
CREATE TABLE maestra.session_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES maestra.customer_engagements(customer_id),
    session_id UUID NOT NULL,       -- groups interactions within one session
    interaction_type TEXT NOT NULL CHECK (interaction_type IN ('status_check', 'action_request', 'analysis', 'onboarding', 'escalation', 'general')),
    user_message_summary TEXT NOT NULL,  -- what the user asked (summarized, not verbatim)
    maestra_action TEXT,            -- what Maestra did (action dispatched, if any)
    module_context TEXT[],          -- which modules were referenced
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_session_memory_customer ON maestra.session_memory(customer_id, created_at DESC);
CREATE INDEX idx_session_memory_session ON maestra.session_memory(session_id);

-- Maestra Plans: plan mode for write actions
CREATE TABLE maestra.plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES maestra.customer_engagements(customer_id),
    plan_type TEXT NOT NULL CHECK (plan_type IN ('action_dispatch', 'code_change', 'configuration')),
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    affected_modules TEXT[] NOT NULL,
    plan_body JSONB NOT NULL,        -- structured specification of the action
    cc_prompt TEXT,                   -- if code_change: the Claude Code prompt
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'executed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    result_summary TEXT
);

CREATE INDEX idx_plans_customer_status ON maestra.plans(customer_id, status);

-- Module State Cache: cached module status, pushed by modules
CREATE TABLE maestra.module_state_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module TEXT NOT NULL CHECK (module IN ('aod', 'aam', 'farm', 'dcl', 'nlq')),
    customer_id UUID NOT NULL,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(module, customer_id)
);

CREATE INDEX idx_module_state_module ON maestra.module_state_cache(module, customer_id);

-- Interaction Log: every Maestra LLM call logged for cost/quality monitoring
CREATE TABLE maestra.interaction_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    session_id UUID,
    input_hash TEXT NOT NULL,         -- hash of assembled prompt for cache matching
    model_used TEXT NOT NULL,          -- e.g. 'claude-sonnet-4-6'
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    interaction_type TEXT,
    action_dispatched TEXT,            -- which action was triggered, if any
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_interaction_log_customer ON maestra.interaction_log(customer_id, created_at DESC);
CREATE INDEX idx_interaction_log_cost ON maestra.interaction_log(model_used, created_at);

-- Customer Playbook: customer-specific context
CREATE TABLE maestra.customer_playbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE REFERENCES maestra.customer_engagements(customer_id),
    systems JSONB DEFAULT '[]'::jsonb,       -- their systems and data sources
    vocabulary JSONB DEFAULT '{}'::jsonb,     -- their term -> platform concept mappings
    priorities TEXT[] DEFAULT '{}',            -- what they care about most
    notes TEXT,                                -- free-form context
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION maestra.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_engagements_updated
    BEFORE UPDATE ON maestra.customer_engagements
    FOR EACH ROW EXECUTE FUNCTION maestra.update_timestamp();

CREATE TRIGGER trg_playbooks_updated
    BEFORE UPDATE ON maestra.customer_playbooks
    FOR EACH ROW EXECUTE FUNCTION maestra.update_timestamp();

CREATE TRIGGER trg_module_state_updated
    BEFORE UPDATE ON maestra.module_state_cache
    FOR EACH ROW EXECUTE FUNCTION maestra.update_timestamp();

-- Seed data for Meridian/Cascadia demo engagement
INSERT INTO maestra.customer_engagements (
    customer_id, customer_name, scenario_type, deal_phase,
    acquirer_entity, target_entity
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Demo: Meridian/Cascadia',
    'convergence',
    'analysis',
    'Meridian Holdings',
    'Cascadia Partners'
);

INSERT INTO maestra.customer_playbooks (
    customer_id, systems, vocabulary, priorities
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    '[{"name": "Salesforce", "entity": "meridian", "status": "connected"}, {"name": "NetSuite", "entity": "meridian", "status": "connected"}, {"name": "QuickBooks", "entity": "cascadia", "status": "connected"}]',
    '{"ARR": "annual_recurring_revenue", "MRR": "monthly_recurring_revenue", "EBITDA": "ebitda_adjusted"}',
    ARRAY['Revenue reconciliation', 'Customer overlap identification', 'COFA generation']
);
