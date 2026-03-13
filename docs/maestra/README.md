# Maestra Build: M&A Convergence

## What This Is

Five Claude Code session prompts that build Maestra as the AI engagement lead for AOS Convergence (M&A). Each session has a defined scope, harness, and pass criteria. Execute them in order.

## Prerequisites

- NLQ repo checked out and running locally
- AOD, AAM, Farm, DCL repos checked out (Sessions 1 touches all four)
- Supabase instance accessible (same one NLQ/DCL use)
- Claude API key configured in NLQ environment
- tests/HARNESS_RULES.md present in every repo

## File Inventory

```
constitution/
  base.md              → Maestra core identity (copy to nlq/src/maestra/constitution/)
  convergence.md       → M&A scenario knowledge (copy to nlq/src/maestra/constitution/)

sql/
  001_maestra_schema.sql  → Run against Supabase before Session 2

sessions/
  session1_module_status.md     → Add GET /maestra/status to AOD, AAM, Farm, DCL
  session2_engagement_api.md    → Create maestra schema + CRUD API in NLQ
  session3_context_assembly.md  → Constitution loading, context assembly, LLM calls
  session4_action_dispatch.md   → Action dispatch (read) + plan mode (write)
  session5_portal_wiring.md     → Wire to report portal, logging, demo/live switch
```

## Execution Order

### Session 1: Module Status Endpoints
**Repos:** AOD, AAM, Farm, DCL (one commit per repo)
**What it does:** Adds GET /maestra/status to each module
**Harness:** Hit each endpoint, assert schema, assert data
**Dependencies:** None

### Session 2: Engagement State
**Repo:** NLQ
**What it does:** Runs SQL migration, builds engagement state CRUD + API routes
**Harness:** CRUD operations against real Supabase
**Dependencies:** Session 1 complete, SQL migration run

### Session 3: Context Assembly
**Repo:** NLQ
**What it does:** Loads constitution, assembles context from 3 sources, calls Claude, parses response
**Harness:** 10 test messages against real LLM, assert semantic properties
**Dependencies:** Sessions 1-2 complete, constitution files in place

### Session 4: Action Dispatch
**Repo:** NLQ
**What it does:** Wires action catalog to module endpoints, builds plan mode
**Harness:** Read/write dispatch tests, plan lifecycle tests
**Dependencies:** Sessions 1-3 complete

### Session 5: Portal Wiring
**Repo:** NLQ
**What it does:** Chat API endpoint, demo/live switch, logging stats
**Harness:** E2E through chat API, demo mode preservation
**Dependencies:** Sessions 1-4 complete

## What Gets Built (NLQ repo structure)

```
nlq/src/maestra/
  constitution/
    base.md
    convergence.md
  context.js          ← prompt assembly + LLM call
  dispatch.js         ← action routing + plan generation
  engagement.js       ← Supabase CRUD for maestra schema
  plan.js             ← plan lifecycle (create/approve/execute)
  router.js           ← Express routes for chat API + engagement API
  log.js              ← interaction logging

nlq/tests/maestra/
  status_endpoints.test.js   ← Session 1
  engagement.test.js         ← Session 2
  context_assembly.test.js   ← Session 3
  dispatch.test.js           ← Session 4
  e2e.test.js                ← Session 5
```

## What Is NOT Touched

- NLQ query pipeline (regex → keyword → ambiguity → LLM resolution)
- DCL extraction rules, concept mappings, pipes
- Convergence multi-entity architecture
- Demo mode (stays as separate code path)
- fact_base.json behavior
- Any existing test suites

## How to Use Each Session Prompt

1. Open Claude Code in the appropriate repo
2. Copy the session prompt into CC
3. CC will read HARNESS_RULES.md, implement the code, and run the harness
4. Session is done when 100% tests pass with zero regressions on existing tests
5. Commit and move to the next session

## Environment Variables (add to NLQ if missing)

```
AOD_URL=https://aos-aod.onrender.com    (or localhost for dev)
AAM_URL=https://aos-aam.onrender.com
FARM_URL=https://aos-farm.onrender.com
DCL_URL=https://aos-dcl.onrender.com
```

## After All 5 Sessions

Maestra is live. Test it:
```
curl -X POST http://localhost:PORT/maestra/chat \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "00000000-0000-0000-0000-000000000001", "message": "Where are we with the deal?"}'
```

Expected: Maestra responds with current Meridian/Cascadia deal status, referencing real module state.
