# NLQ Live Mode - Fail Loudly Fix

## Problem Statement
NLQ in live mode was silently falling back to `fact_base.json` (demo data) instead of failing with clear error messages when:
- DCL was unreachable
- DCL returned errors
- Metrics had no ingested data

This made debugging impossible and violated the "fail loudly" principle.

## Root Cause
1. DCL **IS working correctly** - has 229KB+ of ingested data from multiple source systems
2. When `data_mode=live` is passed to DCL, it correctly serves from ingest buffer
3. **NLQ was catching all exceptions** and silently returning demo data or empty results

## Changes Made

### 1. `dcl_semantic_client.py` - Prevent Silent Fallbacks

**Lines 1057-1073**: Added guards to prevent local fallback in live mode
```python
# LIVE MODE: Prevent fallback to local fact_base - fail loudly instead
if data_mode == "live" and (force_local or ctx_force):
    raise RuntimeError(
        "LIVE MODE FAILURE: force_local=True but data_mode='live'. "
        "Cannot serve demo data in live mode. Check request configuration."
    )

if data_mode == "live" and not self.dcl_url:
    raise RuntimeError(
        "LIVE MODE FAILURE: DCL_API_URL not configured. "
        "Live mode requires DCL endpoint. Set DCL_API_URL environment variable or switch to Demo mode."
    )
```

**Lines 1116-1135**: Fail loudly on DCL errors in live mode
```python
if response.status_code == 404:
    if data_mode == "live":
        raise RuntimeError(f"LIVE MODE FAILURE: Metric not found in DCL catalog...")

elif response.status_code == 400:
    if data_mode == "live":
        raise RuntimeError(f"LIVE MODE FAILURE: Invalid query - {error_msg}...")
```

**Lines 1144-1159**: Fail loudly on network errors in live mode
```python
except httpx.HTTPStatusError as e:
    if data_mode == "live":
        raise RuntimeError(f"LIVE MODE FAILURE: DCL query failed with status {e.response.status_code}...")

except (httpx.RequestError, json.JSONDecodeError) as e:
    if data_mode == "live":
        raise RuntimeError(f"LIVE MODE FAILURE: Cannot reach DCL endpoint...")
```

### 2. `dashboard_data_resolver.py` - Detect Demo Data in Live Mode

**Lines 120-133**: Check if DCL returned demo data when live was requested
```python
# LIVE MODE: Fail loudly if we got demo data when live was requested
current_mode = get_data_mode()
if current_mode == "live":
    data_source = result.get("data_source", "")
    if data_source == "demo":
        reason = result.get("data_source_reason", "DCL returned demo data instead of live data")
        raise RuntimeError(
            f"LIVE MODE FAILURE: {reason}. "
            f"Metric '{metric}' not available in live ingested data. "
            f"Check DCL ingest buffer or switch to Demo mode."
        )
```

### 3. `dashboard_routes.py` - Surface Clear Errors to UI

**Lines 175-189**: Provide helpful suggestions for live mode failures
```python
error_str = str(e)

# Provide clear error messages for live mode failures
suggestions = []
if "LIVE MODE FAILURE" in error_str:
    suggestions = [
        "Switch to Demo mode to use local test data",
        "Check DCL service status",
        "Verify this metric has ingested data in DCL"
    ]
```

## Behavior Now

### Live Mode with Working Metric
```bash
curl -X POST /api/v1/query/dashboard \
  -d '{"question":"Show me revenue","data_mode":"live"}'

✓ Returns dashboard with live ingested data
✓ metadata.mode: "Ingest"
✓ metadata.source: "ingest"
✓ No silent fallback
```

### Live Mode with Missing Metric
```bash
curl -X POST /api/v1/query/dashboard \
  -d '{"question":"Show me attrition rate","data_mode":"live"}'

✗ Returns clear error:
{
  "success": false,
  "error": "LIVE MODE FAILURE: Metric 'attrition_rate' not available in live ingested data. Check DCL ingest buffer or switch to Demo mode.",
  "suggestions": [
    "Switch to Demo mode to use local test data",
    "Check DCL service status",
    "Verify this metric has ingested data in DCL"
  ]
}
```

### Live Mode with DCL Down
```bash
# If DCL is unreachable:
✗ Returns clear error:
"LIVE MODE FAILURE: Cannot reach DCL endpoint at https://aos-dclv2.onrender.com. Check network connectivity or switch to Demo mode."
```

### Demo Mode (Unchanged)
```bash
curl -X POST /api/v1/query/dashboard \
  -d '{"question":"Show me revenue","data_mode":"demo"}'

✓ Uses fact_base.json as expected
✓ No DCL calls made
✓ Works offline
```

## Testing Done

1. ✅ Live mode with valid metric (revenue) - returns live data
2. ✅ Live mode with invalid grain - fails with clear error
3. ✅ Live mode with missing metric - fails with clear error
4. ✅ Demo mode - continues to work normally
5. ✅ Error messages include actionable suggestions

## DCL Status Confirmed

```bash
$ curl https://aos-dclv2.onrender.com/api/dcl/ingest/runs | jq '.runs | length'
156

$ curl https://aos-dclv2.onrender.com/api/dcl/semantic-export | jq '.mode'
{
  "data_mode": "Demo",
  "run_mode": "Dev",
  "last_updated": "2026-02-23T16:40:49.490999Z"
}
```

DCL has 156 ingested runs from source systems:
- intuit, nextio inc, notion, onepad inc, opensuite inc, pagerduty, pipedrive, etc.

## Next Steps (Recommended)

1. **Update DCL's data_mode** - DCL's semantic export shows `"data_mode": "Demo"` but it HAS ingested data. This is cosmetic but confusing.

2. **Monitor live mode usage** - Track which metrics users request in live mode vs demo mode to prioritize ingest coverage.

3. **Add /health endpoint to DCL** - Currently returns 404. Would help monitoring.

## Files Modified
- `src/nlq/services/dcl_semantic_client.py`
- `src/nlq/core/dashboard_data_resolver.py`
- `src/nlq/api/dashboard_routes.py`

## Backward Compatibility
✅ Demo mode behavior unchanged
✅ API contracts unchanged
✅ Only affects error handling in live mode
