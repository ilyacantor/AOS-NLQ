-- 002_drop_legacy_schema.sql — Brain-A Part 4
-- Drop the legacy NLQ `maestra` schema and all its tables.
-- Replaces 001_maestra_schema.sql. Runtime python that depended on
-- these tables is deleted in Brain-B; chat traffic via /maestra/chat
-- already 500s with no day-to-day impact.
--
-- Idempotent via IF EXISTS — safe to run on any environment whether
-- or not 001 was previously applied.

BEGIN;

DROP TABLE IF EXISTS maestra.customer_playbooks CASCADE;
DROP TABLE IF EXISTS maestra.interaction_log    CASCADE;
DROP TABLE IF EXISTS maestra.module_state_cache CASCADE;
DROP TABLE IF EXISTS maestra.plans              CASCADE;
DROP TABLE IF EXISTS maestra.session_memory     CASCADE;
DROP TABLE IF EXISTS maestra.customer_engagements CASCADE;

DROP FUNCTION IF EXISTS maestra.update_timestamp() CASCADE;

DROP SCHEMA IF EXISTS maestra CASCADE;

COMMIT;
