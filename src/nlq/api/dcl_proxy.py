"""
DCL Report Proxy — forwards /api/reports/* requests to DCL backend.

The NLQ portal's combining-statement and entity-overlap views need data
from DCL's report endpoints. Since Vite proxies all /api/* to the NLQ
backend (port 8005), this router forwards report requests to DCL (port 8004).

Per RACI: DCL owns report data, NLQ owns rendering. This proxy is the
thin bridge between the NLQ frontend and DCL's report API.

Uses asyncio.to_thread with sync httpx so proxy calls run in a thread pool
and are not blocked when sync DCL calls from the query handler occupy the
event loop.
"""

import asyncio
import os
import logging
from collections import defaultdict

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["DCL Proxy"])

DCL_BASE_URL = os.environ.get("DCL_API_URL", "").rstrip("/")
if not DCL_BASE_URL:
    logger.error(
        "DCL_API_URL environment variable is not set. "
        "DCL report proxy will fail on all requests. "
        "Set DCL_API_URL to the DCL service URL (e.g. https://aos-dclv2.onrender.com)."
    )

# Shared sync HTTP client — connection pool reused across proxy calls.
_proxy_client = httpx.Client(timeout=30.0, follow_redirects=True)


@router.get("/api/reports/revenue-by-customer")
async def revenue_by_customer(
    entity_id: str = Query(..., description="Entity ID (meridian or cascadia)"),
):
    """
    Revenue by customer pivoted into a quarterly table.

    Queries DCL for revenue with dimensions=["customer"] across all available
    quarters, then pivots into {customers: [{name, Q1, Q2, ..., total}], quarters, total_revenue, provenance}.
    """
    if not DCL_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL not set — cannot query revenue by customer.",
        )

    dcl_url = f"{DCL_BASE_URL}/api/dcl/query"
    payload = {
        "metric": "revenue",
        "dimensions": ["customer"],
        "entity_id": entity_id,
        "time_range": {"start": "2024-Q1", "end": "2026-Q4"},
    }

    try:
        resp = await asyncio.to_thread(
            _proxy_client.post, dcl_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to DCL at {dcl_url} for revenue-by-customer query.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"DCL timed out on revenue-by-customer query at {dcl_url}.",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code}: {resp.text[:500]}",
        )

    dcl_body = resp.json()
    data = dcl_body.get("data", [])
    metadata = dcl_body.get("metadata", {})

    # Pivot: {customer -> {quarter -> value}}
    pivot: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    quarters_set: set[str] = set()
    for row in data:
        dims = row.get("dimensions", {})
        customer = dims.get("customer") if isinstance(dims, dict) else row.get("customer")
        period = row.get("period")
        value = row.get("value", 0)
        if customer and period and isinstance(value, (int, float)):
            pivot[customer][period] += value
            quarters_set.add(period)

    quarters = sorted(quarters_set)

    # Build customer rows sorted by total descending
    customers = []
    for name, qvals in pivot.items():
        total = sum(qvals.values())
        row = {"name": name, "total": round(total, 2)}
        for q in quarters:
            row[q] = round(qvals.get(q, 0), 2)
        customers.append(row)
    customers.sort(key=lambda c: c["total"], reverse=True)

    total_revenue = sum(c["total"] for c in customers)

    # Build provenance from DCL metadata
    provenance = {
        "run_id": metadata.get("run_id"),
        "mode": metadata.get("mode"),
        "source": metadata.get("source"),
        "run_timestamp": metadata.get("run_timestamp"),
        "entity_id": metadata.get("entity_id"),
    }

    return JSONResponse(content={
        "entity_id": entity_id,
        "quarters": quarters,
        "customers": customers,
        "total_revenue": round(total_revenue, 2),
        "customer_count": len(customers),
        "provenance": provenance,
    })


@router.get("/api/reports/{path:path}")
async def proxy_dcl_report_get(path: str, request: Request):
    """Forward GET /api/reports/* to DCL backend."""
    # Maestra is now native to NLQ — do not proxy to DCL
    if path.startswith("maestra"):
        raise HTTPException(status_code=404, detail="Maestra routes have moved to /maestra/*")
    if not DCL_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL environment variable is not set. "
                   "Cannot proxy report requests to DCL.",
        )
    dcl_url = f"{DCL_BASE_URL}/api/reports/{path}"
    if request.query_params:
        dcl_url += f"?{request.query_params}"

    try:
        resp = await asyncio.to_thread(_proxy_client.get, dcl_url)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=(
                f"DCL report proxy failed: could not connect to DCL at {dcl_url}. "
                f"Ensure DCL backend is running on {DCL_BASE_URL}."
            ),
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"DCL report proxy timed out waiting for {dcl_url}.",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code}: {resp.text[:500]}",
        )

    return JSONResponse(content=resp.json(), status_code=200)


@router.post("/api/reports/{path:path}")
async def proxy_dcl_report_post(path: str, request: Request):
    """Forward POST /api/reports/* to DCL backend."""
    # Maestra is now native to NLQ — do not proxy to DCL
    if path.startswith("maestra"):
        raise HTTPException(status_code=404, detail="Maestra routes have moved to /maestra/*")
    if not DCL_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL environment variable is not set. "
                   "Cannot proxy report requests to DCL.",
        )
    dcl_url = f"{DCL_BASE_URL}/api/reports/{path}"

    body = await request.body()

    try:
        resp = await asyncio.to_thread(
            _proxy_client.post, dcl_url,
            content=body,
            headers={"Content-Type": "application/json"},
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=(
                f"DCL report proxy failed: could not connect to DCL at {dcl_url}. "
                f"Ensure DCL backend is running on {DCL_BASE_URL}."
            ),
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"DCL report proxy timed out waiting for {dcl_url}.",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code}: {resp.text[:500]}",
        )

    return JSONResponse(content=resp.json(), status_code=200)
