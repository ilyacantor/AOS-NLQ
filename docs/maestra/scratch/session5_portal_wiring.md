# CC Session 5: Wire to Report Portal + Interaction Logging

## Context
We are building Maestra, the AI engagement lead for AOS Convergence (M&A). This is the final session. It wires the live Maestra system into the report portal UI surface, replacing the old demo code path entirely.

Sessions 1-4 must be complete.

Read tests/HARNESS_RULES.md before making any changes. All 16 rules apply.

## Important: No Demo/Live Split

There is no separate demo mode. The old Maestra demo code in the report portal is being replaced, not preserved alongside. The demo scenario (Meridian/Cascadia) is handled by the live Maestra system using the seeded demo tenant in the engagement state database.

The old demo code should be removed. Git history preserves it. Do not maintain two code paths.

## What to build

### Step 1: Archive and remove old demo code

Identify the existing Maestra demo code in the report portal. Remove it. The seeded Meridian/Cascadia engagement in maestra.customer_engagements (customer_id: 00000000-0000-0000-0000-000000000001) replaces the demo script. Maestra reads real module state for this tenant and narrates it — that IS the demo.

### Step 2: Chat API endpoint

Create or modify a route in the report portal for the Maestra chat interaction:

```
POST /maestra/chat
Body: { customer_id: string, message: string, session_id?: string }
Response: { 
  text: string,              // Maestra's response (display to customer)
  action_result?: object,    // if a read action was dispatched, its result
  plan_created?: {           // if a write action generated a plan
    plan_id: string,
    title: string,
    status: 'pending'
  },
  session_id: string         // for continuity
}
```

Implementation:
1. Validate customer_id exists in maestra.customer_engagements (return 404 if not)
2. If no session_id provided, generate one (UUID)
3. Call assembleContext(customerId, message, sessionId) from Session 3
4. If response includes an action, call dispatchAction from Session 4
5. If read action: make second LLM call to narrate the result, include in response
6. If write action: include plan info in response
7. Return formatted response

### Step 3: Module state refresh

Create a utility that refreshes the module_state_cache for a customer by calling all module status endpoints:

```javascript
async function refreshModuleState(customerId) {
  // Call GET /maestra/status on each module (AOD, AAM, Farm, DCL)
  // Include tenant_id for this customer
  // Upsert results into maestra.module_state_cache
  // Return summary: which modules responded, which failed, which are stale
}
```

This should be called:
- On the first chat interaction for a customer (to ensure cache is populated)
- When any cached entry is older than the staleness threshold (5 min, from Session 3)

### Step 4: First-interaction onboarding

When a customer's first ever message comes in (session_memory is empty for this customer_id):

1. Before calling assembleContext, call refreshModuleState to ensure all caches are fresh
2. The constitution already handles the first-interaction greeting
3. After the response, update engagement state: last_interaction_at, add session_memory

### Step 5: Interaction logging dashboard data

Add a route for basic Maestra health monitoring:

```
GET /maestra/stats/:customerId
Response: {
  total_interactions: number,
  interactions_today: number,
  avg_latency_ms: number,
  total_input_tokens: number,
  total_output_tokens: number,
  estimated_cost_usd: number,
  plans_pending: number,
  plans_executed: number,
  last_interaction_at: timestamp
}
```

Query from maestra.interaction_log and maestra.plans. Internal monitoring only.

## Harness

Create tests/maestra/e2e.test.js

Tests:

1. **First interaction (demo tenant):** POST /maestra/chat with Meridian/Cascadia customer_id and "Hi, I'm new here"
   - Assert response.text introduces Maestra
   - Assert response.text mentions both "Meridian" and "Cascadia"
   - Assert response.text summarizes deal status from real module state
   - Assert session_id is returned
   - Assert maestra.session_memory has a new entry
   - Assert maestra.interaction_log has a new entry

2. **Status question:** POST with "What's the pipeline health?"
   - Assert response.text references multiple modules
   - Assert response.text is specific (counts, statuses, not vague)

3. **Module-specific question:** POST with "What did AOD find for Cascadia?"
   - Assert response.text mentions "Cascadia"
   - Assert response.text references discovery data

4. **Read action dispatch:** POST with "Show me the overlap report"
   - Assert response includes report data or clear availability message
   - Assert maestra.interaction_log records the dispatch

5. **Write action creates plan:** POST with "Re-run discovery for Cascadia"
   - Assert response.plan_created is present
   - Assert response.text mentions plan needs approval
   - Assert maestra.plans has a new pending entry

6. **Session continuity:** Send two messages with same session_id
   - Assert second response references first message context
   - Assert both logged under same session_id

7. **Entity ambiguity:** POST with "What's the revenue?"
   - Assert response asks which entity
   - Assert Maestra does NOT guess

8. **Invalid customer_id:** POST with non-existent customer_id
   - Assert HTTP 404, clean error message

9. **Stats endpoint:** GET /maestra/stats for demo customer
   - Assert all fields present
   - Assert total_interactions > 0
   - Assert estimated_cost_usd > 0

10. **Module state cache populated:** Query maestra.module_state_cache after interaction
    - Assert at least one module has cached state
    - Assert updated_at is recent

11. **Old demo path gone:** Assert old demo endpoints return 404
    - Assert no hardcoded demo script references in active codebase

Tests MUST NOT:
- Mock the LLM or module endpoints
- Skip or xfail
- Assert exact LLM response text

Run ALL NLQ tests + all Maestra tests (Sessions 1-5). Zero regressions. 100% pass or not done.
