# CC Session 2: Maestra Schema + Engagement API

## Context
We are building Maestra, the AI engagement lead for AOS Convergence (M&A). This session creates the Supabase schema for Maestra's persistent state and builds a thin API layer in the NLQ reports service.

Session 1 (module status endpoints) must be complete before this session.

Read tests/HARNESS_RULES.md before making any changes. All 16 rules apply.

## What to build

### Step 1: Run the migration
Execute the SQL migration at `maestra/sql/001_maestra_schema.sql` against the Supabase instance. This creates:
- Schema: `maestra`
- Tables: `customer_engagements`, `session_memory`, `plans`, `module_state_cache`, `interaction_log`, `customer_playbooks`
- Indexes and triggers
- Seed data for Meridian/Cascadia demo engagement

Verify migration succeeds. Verify seed data is present.

### Step 2: Build engagement state CRUD

Create `src/maestra/engagement.js` (or .ts if NLQ uses TypeScript) in the NLQ repo.

This module provides:

```javascript
// Get engagement state for a customer
async function getEngagement(customerId)
// Returns: customer_engagements row joined with customer_playbooks

// Update engagement state
async function updateEngagement(customerId, updates)
// Updates: deal_phase, onboarding_complete, last_interaction_at, etc.

// Add session memory entry
async function addSessionMemory(customerId, sessionId, entry)
// entry: { interaction_type, user_message_summary, maestra_action, module_context }

// Get recent session memory
async function getRecentMemory(customerId, limit = 10)
// Returns: last N session_memory entries for this customer, newest first

// Get/set module state cache
async function getModuleState(module, customerId)
async function setModuleState(module, customerId, stateJson)

// Create a plan
async function createPlan(plan)
// plan: { customer_id, plan_type, title, rationale, affected_modules, plan_body, cc_prompt }
// Returns: created plan with id and status='pending'

// Get pending plans
async function getPendingPlans(customerId)

// Approve/reject plan
async function updatePlanStatus(planId, status, approvedBy, resultSummary)

// Log interaction
async function logInteraction(entry)
// entry: { customer_id, session_id, input_hash, model_used, input_tokens, output_tokens, latency_ms, interaction_type, action_dispatched }
```

Use the existing Supabase client from NLQ (do not create a new connection). All queries should use the `maestra` schema explicitly.

### Step 3: Build API routes

Create `src/maestra/router.js` — Express router (or whatever NLQ uses) exposing:

```
GET  /maestra/engagement/:customerId     → getEngagement
PUT  /maestra/engagement/:customerId     → updateEngagement
GET  /maestra/memory/:customerId         → getRecentMemory
POST /maestra/memory/:customerId         → addSessionMemory
GET  /maestra/plans/:customerId          → getPendingPlans
POST /maestra/plans                      → createPlan
PUT  /maestra/plans/:planId/status       → updatePlanStatus
GET  /maestra/module-state/:module/:customerId  → getModuleState
PUT  /maestra/module-state/:module/:customerId  → setModuleState
```

Mount this router in the NLQ app alongside existing routes. Do NOT modify any existing NLQ routes.

## Harness

Create tests/maestra/engagement.test.js

Tests MUST:
1. Create a new customer engagement via API, assert 200, assert returned data matches input
2. Read the engagement back, assert it matches
3. Update deal_phase, assert update persisted
4. Add 3 session memory entries, read them back, assert order (newest first) and count
5. Set module state cache for 'aod', read it back, assert match
6. Create a plan with status 'pending', assert it appears in getPendingPlans
7. Approve the plan, assert status changed to 'approved', assert approved_by set
8. Log an interaction, query interaction_log table directly, assert row exists with correct fields
9. Read the seed Meridian/Cascadia engagement, assert it exists with correct scenario_type='convergence'
10. Attempt to create engagement with invalid scenario_type, assert rejection

Tests MUST NOT:
- Use mocked database (hit real Supabase)
- Leave test data behind (clean up after each test or use a test-specific customer_id prefix)
- Skip or xfail
- Modify schema after migration

Run ALL existing NLQ tests + new Maestra tests. Zero regressions. 100% pass or not done.
