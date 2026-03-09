"""
DCL Report Proxy — forwards /api/reports/* requests to DCL backend.

The NLQ portal's combining-statement and entity-overlap views need data
from DCL's report endpoints. Since Vite proxies all /api/* to the NLQ
backend (port 8005), this router forwards report requests to DCL (port 8004).

Per RACI: DCL owns report data, NLQ owns rendering. This proxy is the
thin bridge between the NLQ frontend and DCL's report API.
"""

import os
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["DCL Proxy"])

DCL_BASE_URL = (
    os.environ.get("DCL_API_URL", "").rstrip("/")
    or "http://localhost:8004"
)


@router.get("/api/reports/{path:path}")
async def proxy_dcl_report_get(path: str, request: Request):
    """Forward GET /api/reports/* to DCL backend."""
    dcl_url = f"{DCL_BASE_URL}/api/reports/{path}"
    if request.query_params:
        dcl_url += f"?{request.query_params}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(dcl_url)
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
    """Forward POST /api/reports/* to DCL backend (what-if, maestra)."""
    dcl_url = f"{DCL_BASE_URL}/api/reports/{path}"

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                dcl_url,
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
