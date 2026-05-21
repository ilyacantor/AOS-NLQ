"""Demo pipeline monitor — NLQ metrics endpoint.

GET /api/nlq/monitor/metrics — read-only dashboard + query stats for the
AAM-served pipeline monitor page (app/routers/monitor.py in the aam repo).

Additive and read-only: no existing route or service is modified, no DDL is
run, nothing is written. Observes existing state only — the in-memory
dashboard session store and the rag_learning_log table.

CORS: the response carries an explicit Access-Control-Allow-Origin for the
AAM-served origin (MONITOR_ALLOWED_ORIGIN env, default http://localhost:8002).
The app-wide CORSMiddleware is left untouched — this scopes the cross-origin
allowance to this one endpoint without affecting any other route.

tile_errors_1h is reported null (the page renders "n/a"): widget resolution
errors are logged to stderr but never counted or stored. See
nlq_deferred_work.md.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.nlq.api.session import get_dashboard_session_store

router = APIRouter(tags=["Monitor"])

# The AAM-served monitor page's origin. The metrics endpoint echoes this as
# its Access-Control-Allow-Origin so the cross-origin poll succeeds —
# scoped to this endpoint alone, no other route touched.
_ALLOWED_ORIGIN = os.getenv("MONITOR_ALLOWED_ORIGIN", "http://localhost:8002")
_TABLE = "rag_learning_log"

_supabase = None
_supabase_checked = False


def _get_supabase():
    """Read-only Supabase client for the rag_learning_log table. Built once,
    using the same env resolution as RAGLearningLog. Returns None when the
    Supabase env vars are not configured."""
    global _supabase, _supabase_checked
    if _supabase_checked:
        return _supabase
    _supabase_checked = True
    api_url = os.getenv("SUPABASE_API_URL", "").strip()
    fallback = os.getenv("SUPABASE_URL", "").strip()
    url = api_url if api_url.startswith("https://") else (
        fallback if fallback.startswith("https://") else "")
    key = os.getenv("SUPABASE_KEY", "")
    if url and key:
        from supabase import create_client
        _supabase = create_client(url, key)
    return _supabase


def _percentile(values: List[int], pct: float) -> Optional[float]:
    """Nearest-rank percentile, or None when there are no values."""
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


@router.get("/api/nlq/monitor/metrics")
def nlq_monitor_metrics() -> JSONResponse:
    """NLQ panel for the pipeline monitor: active dashboards, queries in the
    last hour, query-latency p95, cache-hit rate. Read-only.

    A failure to read query stats propagates (500) — the monitor page then
    shows NLQ with a gray dot and keeps its last values rather than render a
    half-populated panel (A1)."""
    dashboards_active = get_dashboard_session_store().stats()["total_sessions"]

    client = _get_supabase()
    if client is None:
        raise RuntimeError(
            "NLQ monitor: Supabase is not configured "
            "(SUPABASE_API_URL/SUPABASE_URL + SUPABASE_KEY) — cannot read "
            "rag_learning_log query stats."
        )

    # rag_learning_log.created_at is written as a naive-UTC isoformat string
    # (RAGLearningLog.log_entry); match that form for the window cutoff.
    cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    res = (
        client.table(_TABLE)
        .select("execution_time_ms, source, success", count="exact")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(5000)
        .execute()
    )
    rows = res.data or []
    queries_1h = res.count if getattr(res, "count", None) is not None else len(rows)

    latencies = [r["execution_time_ms"] for r in rows
                 if r.get("execution_time_ms") is not None]
    p95 = _percentile(latencies, 95)

    cache_hit_pct = None
    if rows:
        cache_hits = sum(1 for r in rows
                         if r.get("source") == "cache" and r.get("success"))
        cache_hit_pct = round(cache_hits / len(rows) * 100, 1)

    body = {
        "service": "nlq",
        "dashboards_active": dashboards_active,
        "queries_1h": queries_1h,
        "p95_ms": int(p95) if p95 is not None else None,
        "cache_hit_pct": cache_hit_pct,
        # Widget/tile resolution errors are logged to stderr but never
        # counted or stored — reported n/a. See nlq_deferred_work.md.
        "tile_errors_1h": None,
    }
    return JSONResponse(
        content=body,
        headers={"Access-Control-Allow-Origin": _ALLOWED_ORIGIN, "Vary": "Origin"},
    )
