-- 005_drop_legacy_maestra_schema.sql — Brain-A Part 4 / Brain-BC Part 4
-- Drop the legacy NLQ `maestra` schema and all its tables.
-- Replaces the former sql/maestra/001_maestra_schema.sql. Runtime python that
-- depended on these tables is deleted in Brain-BC Part 4; chat traffic via
-- /maestra/chat already 500s with no day-to-day impact.
--
-- Relocated from sql/maestra/002_drop_legacy_schema.sql during Brain-BC Part 4
-- when the legacy sql/maestra/ directory was removed. Renumbered to 005 to
-- fit the canonical migrations/ numbering scheme.
--
-- Idempotent via IF EXISTS — safe to run on any environment whether
-- or not the legacy schema was previously created.

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
