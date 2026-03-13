# CC Session 1: Module Status Endpoints

## Context
We are building Maestra, the AI engagement lead for AOS Convergence (M&A). This session adds a GET /maestra/status endpoint to each of the 4 modules: AOD, AAM, Farm, DCL.

These endpoints return structured JSON describing the current state of each module for a given tenant. They are read-only, thin, and query existing state only. No new business logic. No new capabilities. Just a window into what already exists.

Read tests/HARNESS_RULES.md before making any changes. All 16 rules apply.

## What to build

### AOD: GET /maestra/status
Returns JSON:
```json
{
  "module": "aod",
  "tenant_id": "<from request>",
  "discovery_phase": "pending|running|complete",
  "systems_discovered": { "count": 0, "list": [] },
  "shadows_detected": { "count": 0, "list": [] },
  "governance_items": { "count": 0, "items": [] },
  "fabric_availability": { "identity": false, "collaboration": false, "operations": false, "data": false },
  "last_run_at": null,
  "healthy": true
}
```
Query existing AOD state (database, in-memory, whatever AOD uses) to populate. If AOD has no concept of some fields yet, return sensible defaults with a comment noting the gap. Do not fabricate data.

### AAM: GET /maestra/status
Returns JSON:
```json
{
  "module": "aam",
  "tenant_id": "<from request>",
  "manifests": { "total": 0, "succeeded": 0, "failed": 0, "pending": 0 },
  "sso_pending": { "count": 0, "items": [] },
  "connections": [],
  "last_execution_at": null,
  "healthy": true
}
```

### Farm: GET /maestra/status
Returns JSON:
```json
{
  "module": "farm",
  "tenant_id": "<from request>",
  "active_tenant": null,
  "personas_active": [],
  "generation_progress": { "percent": 0, "status": "idle|running|complete|error" },
  "data_quality_flags": [],
  "last_generation_at": null,
  "healthy": true
}
```

### DCL: GET /maestra/status
Returns JSON:
```json
{
  "module": "dcl",
  "tenant_id": "<from request>",
  "concepts": { "count": 0 },
  "dimensions": { "count": 0 },
  "pairings": { "count": 0 },
  "entities": { "count": 0, "list": [] },
  "extraction_rules": { "count": 0, "active": 0, "errored": 0 },
  "entity_resolution": { "configured": false, "active_entities": [] },
  "last_update_at": null,
  "healthy": true
}
```

## Route registration
Each module should register this route alongside its existing routes. Use whatever routing pattern the module already uses (Express, Fastify, etc). The route should accept tenant_id as a query parameter or from the existing auth/tenant middleware.

## Harness

Create tests/maestra/status_endpoints.test.js (or appropriate test file for each module).

Tests MUST:
1. Call GET /maestra/status for the demo tenant (Meridian/Cascadia)
2. Assert HTTP 200
3. Assert response is valid JSON
4. Assert response matches the schema above (all required fields present)
5. Assert `module` field matches the expected module name
6. Assert `healthy` field is boolean
7. Assert `tenant_id` is present and matches request
8. Assert response time < 500ms
9. Run against the live module (not mocked)

Tests MUST NOT:
- Use hardcoded expected values for counts (query real state)
- Skip or xfail any test
- Modify any existing module code beyond adding the new route
- Create test-only endpoints or backdoors

Run ALL tests (existing + new) after adding the route. Zero regressions. 100% pass or not done.
