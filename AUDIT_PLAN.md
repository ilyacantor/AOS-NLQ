# AOS-NLQ Code Quality Audit & Remediation Plan

> **Date**: 2026-02-17
> **Auditor**: Claude Code
> **Branch**: `claude/improve-code-quality-a9F32`
> **Scope**: Full codebase audit of AOS-NLQ module

---

## Audit Findings Summary

| Severity | Count | Category |
|----------|-------|----------|
| CRITICAL | 3 | Monolith, Silent Fallbacks, No Auth |
| HIGH | 8 | Hardcoded config, Bare exceptions, In-memory sessions, No timeouts |
| MEDIUM | 10 | Duplicate logic, Regex sprawl, Missing validation, Test data coupling |
| LOW | 5 | Magic numbers, Naming, Missing type hints |

**Total Python LOC (backend)**: ~16,600 lines across 52 files
**Frontend LOC**: ~4,500 lines (React/TS)
**Largest file**: `src/nlq/api/routes.py` at **4,377 lines** (critical monolith)

---

## CRITICAL Findings

### C1. `routes.py` is a 4,377-line monolith

**File**: `src/nlq/api/routes.py`
**Problem**: Single file contains:
- 5 route handlers (`/query`, `/query/galaxy`, `/health`, `/schema`, `/eval/run`, `/pipeline/status`)
- ~30 private helper functions (response formatting, metric queries, breakdown logic, dashboard detection)
- In-memory session management (lines 95-174)
- Insufficient data tracking helpers (lines 190-312)
- Cache integration (lines 314-377)
- Dashboard query detection & handling (lines 379-750)
- Text response formatting (lines 768-1042)
- Core query pipeline (lines 1043-2756) - the actual business logic
- Galaxy query pipeline (lines 3204-3910)
- Utility functions (lines 3912-4290)
- Eval runner (lines 4290-4377)

**Impact**: Unmaintainable, untestable, impossible to review changes safely. A single merge conflict in this file can break everything.

**Fix**: Split into focused modules:
- `api/query_text.py` - `/query` endpoint + text pipeline helpers
- `api/query_galaxy.py` - `/query/galaxy` endpoint + galaxy pipeline helpers
- `api/health.py` - `/health`, `/schema`, `/pipeline/status`
- `api/eval.py` - `/eval/run`
- `api/session.py` - Session management (extracted from module-level globals)
- `api/formatters.py` - Value/response formatting utilities
- `api/dashboard_detect.py` - Dashboard query detection (already partially in `dashboard_routes.py`)

### C2. 93 bare `except Exception` handlers — Silent Killer Fallbacks

**Files**: All service and API files (93 occurrences across 22 files)
**Worst offenders**:
- `dcl_semantic_client.py`: 9 bare catches, silently falls back to local test data
- `supabase_persistence.py`: 11 bare catches, returns None/empty on DB errors
- `routes.py`: 15 bare catches, swallows errors in query pipeline
- `dcl/routes.py`: 16 bare catches, every endpoint wraps everything

**Pattern**:
```python
except Exception as e:
    logger.warning(f"Something failed: {e}")
    return []  # or None, or {} — silent death
```

**Impact**: Errors are swallowed. Users see stale/wrong data with no indication of failure. Debugging is impossible because errors don't propagate. Violates "Fail Loudly" principle from AOS Core Philosophy.

**Fix**:
- Categorize each catch: Is it protecting against transient failure (OK) or hiding bugs (NOT OK)?
- Replace with specific exception types where possible
- Ensure error state propagates to the user (show "data unavailable" not fake data)
- Add structured error logging with request context

### C3. CORS allows all origins with credentials

**File**: `src/nlq/main.py:42-48`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # Dangerous with wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Impact**: Any website can make authenticated requests to the API. Combined with no rate limiting, this is exploitable.

**Fix**: Configure allowed origins from environment variable. In dev, allow localhost. In prod, restrict to actual frontend domain.

---

## HIGH Findings

### H1. In-memory session storage (routes.py:95-174)

**Problem**: Dashboard sessions stored in Python dict with threading Lock. Lost on restart. Not shared across workers. The comment even says "In production, this would use Redis".

**Fix**: Move to Supabase-backed sessions (persistence service already exists) or add Redis.

### H2. No timeouts on Claude API calls (llm/client.py:74-79)

**Problem**: `client.messages.create()` called with no timeout. If Claude API is slow/hanging, the entire request thread blocks indefinitely.

**Fix**: Add `timeout=30` parameter. Add circuit breaker pattern for repeated failures.

### H3. Hardcoded DEFAULT_TENANT_ID (supabase_persistence.py:24)

```python
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
```

**Problem**: All data goes to same tenant. Multi-tenancy is fiction. RLS bypassed by using service-role key.

**Fix**: Require tenant_id on all API requests. Remove default. Enforce at API gateway level.

### H4. DCL semantic client silently falls back to local test data (dcl_semantic_client.py:156)

**Problem**: When DCL API is unreachable, system silently loads `data/fact_base.json` and serves it as if it were real. User has no idea they're seeing test data.

**Fix**: Return explicit error or add `data_source: "local_fallback"` flag in all responses so frontend can show warning.

### H5. 139 instances of `return None/[]/{}` as error responses

**Problem**: Functions return empty values on failure, indistinguishable from "no data exists". Callers can't tell if the metric is zero or if the system broke.

**Fix**: Use Result pattern or raise specific exceptions. Never conflate "no data" with "error".

### H6. No input validation on NLQ query text

**Problem**: No length limit, no character restriction. User can send megabytes of text to Claude API (which costs money per token).

**Fix**: Add max length validation (e.g., 1000 chars). Sanitize input.

### H7. Duplicate route registration (main.py:51-60)

```python
app.include_router(router, prefix="/v1")
app.include_router(router, prefix="/api/v1")
```

**Problem**: Every router is registered twice (once at `/v1`, once at `/api/v1`). This doubles the API surface, doubles the OpenAPI spec, and creates ambiguity about which path is canonical.

**Fix**: Pick one prefix. Use Vite proxy to normalize in dev.

### H8. `_force_local_ctx` context variable for test mode (dcl_semantic_client.py:34)

```python
_force_local_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar('_force_local_ctx', default=False)
```

**Problem**: Global mutable state used to switch between test and production data sources. Can leak across async requests. Fragile and hard to reason about.

**Fix**: Pass data source explicitly via dependency injection. Use FastAPI's Depends pattern.

---

## MEDIUM Findings

### M1. Regex pattern sprawl across 3+ files

- `ambiguity.py`: 50+ patterns for ambiguity detection
- `refinement_intent.py`: 30+ patterns for refinement detection
- `visualization_intent.py`: 20+ patterns for viz detection
- Overlapping patterns, no centralized registry

**Fix**: Create a pattern registry module. Deduplicate. Add pattern tests.

### M2. Duplicate response formatting logic

- `query_helpers.py`: `simple_metric_to_nlq_response()`, `simple_metric_to_galaxy_response()`
- `routes.py`: `_format_enriched_text_response()`, `_format_point_query_response()`, etc.
- Multiple code paths produce the same response shape with slight variations

**Fix**: Consolidate into a single response builder.

### M3. Ground truth values hardcoded in 3 places

- `eval_runner.py` (lines ~70-100)
- `ui_eval_runner.py` (lines ~30-58)
- `ui_eval_runner.js` (lines ~13-42)

**Fix**: Single source of truth in `data/ground_truth.json`, loaded by all test runners.

### M4. `personality.py` — 828 lines of hardcoded persona text

**Problem**: Response templates for 5 personas hardcoded as Python string arrays. Adding a persona requires code changes.

**Fix**: Move to JSON/YAML config file. Load at startup.

### M5. No structured logging

**Problem**: `logging.getLogger(__name__)` used everywhere but no configuration for format, level, or output. No request correlation IDs. No structured JSON logging.

**Fix**: Configure logging in `main.py` startup. Add request ID middleware. Use JSON formatter for production.

### M6. `start.sh` has no error handling

```bash
npm run build
exec uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000
```

**Problem**: If `npm run build` fails, server starts anyway with stale/missing frontend.

**Fix**: Add `set -e` and health check.

### M7. Test files import production code but don't mock external services

**Problem**: Tests in `tests/` directory import real Claude client, real Supabase client. No consistent mocking strategy.

**Fix**: Create test fixtures with proper mocks. Use dependency injection.

### M8. `dcl/models.py` at 1,445 lines — too many models in one file

**Fix**: Split into domain-grouped model files.

### M9. `knowledge/schema.py` and `knowledge/synonyms.py` — 1,660 lines of data-as-code

**Problem**: Business metric definitions, synonyms, units are all Python dicts. Changes require code deploys.

**Fix**: Move to config files (JSON/YAML). Validate at startup with Pydantic.

### M10. No API versioning strategy

**Problem**: `/v1/` prefix exists but no mechanism for v2 compatibility. Breaking model changes will break clients.

**Fix**: Document API contract. Add response envelope versioning.

---

## LOW Findings

### L1. Magic numbers scattered throughout
- Session cleanup interval: `300` (routes.py:120)
- Cache TTL: `300` (dcl_semantic_client.py:39)
- Max sessions: `1000` (routes.py:109)
- Similarity thresholds: `0.92, 0.88, 0.75` (query_cache_service.py)
- Max tokens: `500` (llm/client.py:32)

### L2. Inconsistent naming conventions
- Some files use snake_case for classes (`query_helpers`)
- Mix of `Optional[str]` and `str | None`
- Inconsistent use of `async def` vs `def` for route handlers

### L3. `app.py` and `db.py` in root — legacy Streamlit files
- Not used by the FastAPI app
- Could confuse developers

### L4. `XXI5GBfY` file in root with no purpose
- 1,244 bytes, no extension, appears to be test output

### L5. `@app.on_event` deprecated in FastAPI
- Should use `lifespan` context manager instead

---

## Remediation Plan — Prioritized Phases

### Phase 1: Break the Monolith (C1)

**Goal**: Split `routes.py` from 4,377 lines into 6 focused modules without changing behavior.

1. Extract session management → `api/session.py`
2. Extract text query pipeline → `api/query_text.py`
3. Extract galaxy query pipeline → `api/query_galaxy.py`
4. Extract health/schema/pipeline → `api/health.py`
5. Extract eval endpoint → `api/eval.py`
6. Extract formatting utilities → `api/formatters.py`
7. Verify: Run existing test suite, confirm all endpoints return same responses

**Validation**: Before/after comparison of API responses for a fixed set of queries.

### Phase 2: Kill Silent Fallbacks (C2, H4, H5)

**Goal**: Make errors visible. No more returning `None` when the system is broken.

1. Audit all 93 `except Exception` blocks — classify as:
   - **Keep**: Genuine resilience (transient network failure with retry)
   - **Narrow**: Replace `Exception` with specific types (`httpx.ConnectError`, `json.JSONDecodeError`)
   - **Remove**: Cases that hide bugs
2. Add `data_source` field to all responses (shows "dcl_live", "local_fallback", "cache")
3. Replace `return None` patterns with explicit error types in critical paths
4. Add error status to dashboard widgets when data resolution fails

**Validation**: Intentionally break DCL connection and verify errors propagate to UI.

### Phase 3: Harden Configuration & Security (C3, H2, H3, H6)

**Goal**: No hardcoded shortcuts. Proper security boundaries.

1. Move CORS origins to environment variable
2. Add Claude API timeout (30s)
3. Add input validation on query text (max 1000 chars)
4. Move magic numbers to `config.py` Settings class
5. Add rate limiting middleware
6. Remove duplicate route prefixes (pick `/api/v1` as canonical)

**Validation**: Security scan. Verify rate limiting works. Verify timeouts fire.

### Phase 4: Consolidate Duplicate Logic (M1, M2, M3, M4, M9)

**Goal**: Single source of truth for everything.

1. Create centralized pattern registry for regex patterns
2. Consolidate response formatting into response builder
3. Move ground truth to `data/ground_truth.json`
4. Move persona templates to `data/personas.json`
5. Move schema/synonyms to config files

**Validation**: All tests pass. Response format unchanged.

### Phase 5: Improve Observability & Testing (M5, M7, H1)

**Goal**: Debuggable system with proper test coverage.

1. Configure structured JSON logging with request IDs
2. Replace in-memory sessions with Supabase persistence
3. Create proper test fixtures with mocked external services
4. Add integration tests for DCL fallback behavior
5. Add negative tests for error paths

**Validation**: Can trace a query end-to-end through logs. Tests run without external dependencies.

---

## Validation Strategy

For each phase, before merging:

1. **Snapshot current behavior**: Run the eval suite against current code, save responses
2. **Make changes**: Implement the refactor
3. **Compare**: Run same eval suite, diff responses — must be identical (except new error visibility)
4. **Run existing tests**: `pytest tests/` must pass
5. **Manual smoke test**: Submit 5 representative queries through the API

---

## Files Changed Per Phase

| Phase | Files Modified | Files Created | Risk |
|-------|---------------|---------------|------|
| 1 | routes.py (split) | 6 new API modules | Medium - pure refactor |
| 2 | 22 files with bare catches | None | High - behavior changes |
| 3 | main.py, config.py, llm/client.py | None | Low - config changes |
| 4 | 6+ files | 3 config files | Medium - data migration |
| 5 | main.py, tests/ | fixtures, test utilities | Low - additive |
