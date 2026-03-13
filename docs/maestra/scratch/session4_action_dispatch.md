# CC Session 4: Action Dispatch + Plan Mode

## Context
We are building Maestra, the AI engagement lead for AOS Convergence (M&A). This session wires up action dispatch: when Maestra's LLM response includes an action block, the system executes it (read actions) or creates a plan (write actions).

Sessions 1-3 must be complete.

Read tests/HARNESS_RULES.md before making any changes. All 16 rules apply.

## What to build

### Step 1: Action dispatch

Create `src/maestra/dispatch.js`:

```javascript
// Action catalog: maps action identifiers to module endpoints
const ACTION_CATALOG = {
  // Read actions - execute immediately
  read: {
    'aod:status':        { method: 'GET',  url: '<AOD_URL>/maestra/status' },
    'aam:status':        { method: 'GET',  url: '<AAM_URL>/maestra/status' },
    'farm:status':       { method: 'GET',  url: '<FARM_URL>/maestra/status' },
    'dcl:status':        { method: 'GET',  url: '<DCL_URL>/maestra/status' },
    'nlq:report:overlap':    { method: 'POST', url: '<NLQ_URL>/maestra/report', body: { type: 'overlap' } },
    'nlq:report:conflicts':  { method: 'POST', url: '<NLQ_URL>/maestra/report', body: { type: 'conflicts' } },
    'nlq:report:cofa':       { method: 'POST', url: '<NLQ_URL>/maestra/report', body: { type: 'cofa' } },
  },
  // Write actions - create plan, do not execute
  write: {
    'aod:run-discovery':     { method: 'POST', url: '<AOD_URL>/maestra/run-discovery' },
    'aam:retry-manifest':    { method: 'POST', url: '<AAM_URL>/maestra/retry-manifest' },
  }
};

async function dispatchAction(action, customerId, sessionId) {
  // action = { type: 'read'|'write', module: string, endpoint: string, params: object, rationale: string }
  
  // 1. Map the action to the catalog
  //    Construct the catalog key from action.module + action.endpoint
  //    If not found in catalog, return error: "Unknown action"
  
  // 2. If read action:
  //    - Make the HTTP request to the module endpoint
  //    - Include tenant_id from engagement state
  //    - Return the result
  //    - Log the dispatch in session_memory
  
  // 3. If write action:
  //    - Do NOT execute
  //    - Create a plan via engagement.createPlan():
  //      {
  //        customer_id: customerId,
  //        plan_type: 'action_dispatch',
  //        title: action.rationale,
  //        rationale: action.rationale,
  //        affected_modules: [action.module],
  //        plan_body: { catalog_key, params: action.params, endpoint_config: catalogEntry },
  //        status: 'pending'
  //      }
  //    - Return: { planned: true, plan_id: <id>, message: "I've created a plan for this. It needs approval before I can execute." }
  //    - Log the plan creation in session_memory

  // 4. If the module endpoint is unreachable:
  //    - Return error with clear message: "[Module] is currently unreachable. I'll note this for the team."
  //    - Log the failure
}

// Execute an approved plan
async function executePlan(planId) {
  // 1. Load the plan from database
  // 2. Assert status === 'approved' (refuse to execute pending/rejected/executed plans)
  // 3. Extract the endpoint config from plan_body
  // 4. Make the HTTP request
  // 5. Update plan status to 'executed' or 'failed'
  // 6. Store result_summary
  // 7. Return result
}
```

**Module URLs:** Use environment variables for module URLs (AOD_URL, AAM_URL, FARM_URL, DCL_URL, NLQ_URL). These should already exist in the NLQ environment config for Render. If not, add them.

### Step 2: Wire dispatch into context assembly

Modify `src/maestra/context.js` (from Session 3):

After assembleContext returns a response with an action block, the calling code should:
1. Call `dispatchAction(response.action, customerId, sessionId)`
2. If the dispatch returned data (read action), feed the data back into a second LLM call:
   - System prompt: "You are Maestra. The user asked: [original question]. You dispatched an action and received this result: [dispatch result]. Summarize this for the customer."
   - This second call uses the same model but a shorter prompt (just the result narration)
3. If the dispatch returned a plan (write action), append Maestra's plan message to the response text

### Step 3: Plan approval API

Add to `src/maestra/router.js`:
```
POST /maestra/plans/:planId/approve   → approvePlan (sets status='approved', calls executePlan)
POST /maestra/plans/:planId/reject    → rejectPlan (sets status='rejected')
GET  /maestra/plans/:customerId/pending → list pending plans
```

The approve endpoint should:
1. Update status to 'approved'
2. Immediately call executePlan()
3. Return the execution result

## Harness

Create tests/maestra/dispatch.test.js

Tests:

1. **Read action dispatch (status):** Dispatch a read action for aod:status
   - Assert HTTP request was made to the AOD status endpoint
   - Assert result contains valid module state JSON
   - Assert session_memory was updated

2. **Read action dispatch (report):** Dispatch nlq:report:overlap
   - Assert request was made to the NLQ report endpoint
   - If the endpoint doesn't exist yet, assert a clean error (not a crash)

3. **Write action creates plan:** Dispatch a write action for aod:run-discovery
   - Assert no HTTP request was made to AOD
   - Assert a plan was created in maestra.plans with status='pending'
   - Assert plan_body contains the correct catalog key and params

4. **Unknown action rejected:** Dispatch an action with module='fake' endpoint='nonexistent'
   - Assert clean error returned, not a crash
   
5. **Plan approval + execution:** Create a plan, approve it via API
   - Assert plan status changes to 'approved' then 'executed'
   - Assert the module endpoint was actually called on execution
   - Assert result_summary is populated

6. **Plan rejection:** Create a plan, reject it via API
   - Assert plan status changes to 'rejected'
   - Assert no module endpoint was called

7. **Cannot execute pending plan:** Attempt to call executePlan on a pending plan
   - Assert rejection (must be approved first)

8. **Cannot execute twice:** Approve and execute a plan, then try to execute again
   - Assert rejection (already executed)

9. **Module unreachable:** Dispatch a read action with a bad module URL
   - Assert clean error message returned
   - Assert no crash
   - Assert failure was logged

10. **Full round trip:** Call assembleContext with "Re-run discovery for Cascadia"
    - Assert Maestra's response mentions creating a plan
    - Assert a plan exists in the database
    - Approve the plan via API
    - Assert execution result is returned

Tests MUST NOT:
- Mock module endpoints (hit real endpoints from Session 1, or handle graceful failure if endpoint is not available)
- Skip or xfail
- Leave test plans in the database (clean up)

Run ALL existing NLQ tests + Sessions 1-4 Maestra tests. Zero regressions. 100% pass or not done.
