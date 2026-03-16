"""
DCL Report Proxy — forwards /api/reports/* requests to DCL backend.

The NLQ portal's combining-statement and entity-overlap views need data
from DCL's report endpoints. Since Vite proxies all /api/* to the NLQ
backend (port 8005), this router forwards report requests to DCL (port 8004).

Per RACI: DCL owns report data, NLQ owns rendering. This proxy is the
thin bridge between the NLQ frontend and DCL's report API.

Specific handlers for entity-overlap, cross-sell, ebitda-bridge, and qoe
fetch from DCL v2 endpoints and transform responses into the shapes the
NLQ frontend expects. The generic catch-all proxy handles remaining paths.

Uses asyncio.to_thread with sync httpx so proxy calls run in a thread pool
and are not blocked when sync DCL calls from the query handler occupy the
event loop.
"""

import asyncio
import os
import logging
from collections import defaultdict
from typing import Any, Dict, List

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dcl_get(path: str, params: dict = None) -> dict:
    """GET a DCL endpoint, raise HTTPException on failure."""
    if not DCL_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL not set — cannot proxy report request.",
        )
    url = f"{DCL_BASE_URL}{path}"
    try:
        resp = _proxy_client.get(url, params=params)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to DCL at {url} — is DCL running on {DCL_BASE_URL}?",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"DCL timed out on GET {url}.",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code} for GET {url}: {resp.text[:500]}",
        )
    return resp.json()


def _get_entity_ids() -> List[str]:
    """Fetch entity IDs from DCL triples overview — dynamic, never hardcoded."""
    overview = _dcl_get("/api/dcl/triples/overview")
    entities = [e["entity_id"] for e in overview.get("entities", [])]
    if not entities:
        raise HTTPException(
            status_code=404,
            detail="No entities found in DCL triples overview — cannot build report.",
        )
    return entities


def _strip_quotes(val: Any) -> str:
    """Strip surrounding quotes from triple property values."""
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _parse_float(val: Any, default: float = 0.0) -> float:
    """Parse a numeric value from a triple property."""
    if val is None:
        return default
    try:
        return float(str(val).strip().strip('"'))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Entity Overlap — transforms v2 summary + per-domain detail into OverlapData
# ---------------------------------------------------------------------------

def _transform_customer_matches(concepts: List[Dict]) -> List[Dict]:
    """Transform v2 overlap concepts into CustomerMatch[] shape."""
    total_rev = sum(
        _parse_float(c.get("entity_a_properties", {}).get("revenue"))
        + _parse_float(c.get("entity_b_properties", {}).get("revenue"))
        for c in concepts
    )
    matches = []
    for c in concepts:
        a_props = c.get("entity_a_properties", {})
        b_props = c.get("entity_b_properties", {})
        concept_name = c.get("concept", "")
        short_name = concept_name.split(".", 1)[-1] if "." in concept_name else concept_name

        m_rev = _parse_float(a_props.get("revenue"))
        c_rev = _parse_float(b_props.get("revenue"))
        combined = m_rev + c_rev
        pct = round(combined / total_rev * 100, 2) if total_rev > 0 else 0.0

        matches.append({
            "meridian_name": short_name,
            "cascadia_name": short_name,
            "canonical_name": short_name,
            "match_type": _strip_quotes(a_props.get("match_type", "exact")),
            "confidence": _parse_float(a_props.get("match_confidence", 1.0)),
            "meridian_revenue_M": round(m_rev, 2),
            "cascadia_revenue_M": round(c_rev, 2),
            "combined_revenue_M": round(combined, 2),
            "combined_pct_of_total": pct,
            "concentration_flag": pct > 5.0,
            "industry": _strip_quotes(a_props.get("industry", "")),
            "notes": "",
            "engagement_detail": [],
        })
    matches.sort(key=lambda m: m["combined_revenue_M"], reverse=True)
    return matches


def _transform_vendor_matches(concepts: List[Dict]) -> List[Dict]:
    """Transform v2 overlap concepts into VendorMatch[] shape."""
    matches = []
    for c in concepts:
        a_props = c.get("entity_a_properties", {})
        b_props = c.get("entity_b_properties", {})
        concept_name = c.get("concept", "")
        short_name = concept_name.split(".", 1)[-1] if "." in concept_name else concept_name

        m_spend = _parse_float(a_props.get("spend") or a_props.get("revenue") or a_props.get("amount"))
        c_spend = _parse_float(b_props.get("spend") or b_props.get("revenue") or b_props.get("amount"))

        matches.append({
            "meridian_name": short_name,
            "cascadia_name": short_name,
            "canonical_name": short_name,
            "match_type": _strip_quotes(a_props.get("match_type", "exact")),
            "category": _strip_quotes(a_props.get("category", "")),
            "meridian_spend_M": round(m_spend, 2),
            "cascadia_spend_M": round(c_spend, 2),
            "combined_spend_M": round(m_spend + c_spend, 2),
            "consolidation_opportunity": m_spend > 0 and c_spend > 0,
            "consolidation_detail": None,
        })
    matches.sort(key=lambda m: m["combined_spend_M"], reverse=True)
    return matches


def _transform_people_overlap(concepts: List[Dict], summary: Dict) -> Dict:
    """Transform v2 employee overlap concepts into people_overlap shape."""
    # Group by function/department
    by_function: Dict[str, List[Dict]] = defaultdict(list)
    for c in concepts:
        a_props = c.get("entity_a_properties", {})
        func = _strip_quotes(a_props.get("function") or a_props.get("department") or "General")
        by_function[func].append(c)

    emp_summary = summary.get("employee", {})
    functions = []
    for func_name, func_concepts in sorted(by_function.items()):
        m_count = sum(int(_parse_float(c.get("entity_a_properties", {}).get("headcount", 1))) for c in func_concepts)
        c_count = sum(int(_parse_float(c.get("entity_b_properties", {}).get("headcount", 1))) for c in func_concepts)
        functions.append({
            "function": func_name,
            "meridian_headcount": m_count,
            "cascadia_headcount": c_count,
            "combined_headcount": m_count + c_count,
            "role_overlap_examples": [
                c.get("concept", "").split(".", 1)[-1] for c in func_concepts[:3]
            ],
            "definitional_note": "",
            "role_detail": [],
        })

    return {
        "functions": functions,
        "total_meridian_corporate": emp_summary.get("entity_a_total", 0),
        "total_cascadia_corporate": emp_summary.get("entity_b_total", 0),
        "total_combined_corporate": (
            emp_summary.get("entity_a_total", 0)
            + emp_summary.get("entity_b_total", 0)
        ),
    }


@router.get("/api/reports/entity-overlap")
async def entity_overlap():
    """Fetch overlap from DCL v2 and transform into OverlapData shape."""
    # Fetch summary (counts/percentages per domain)
    summary = await asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/overlap/summary")

    # Fetch per-domain detail concurrently
    cust_detail, vendor_detail, emp_detail = await asyncio.gather(
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/overlap/customer"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/overlap/vendor"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/overlap/employee"),
    )

    cust_summary = summary.get("customer", {})
    vendor_summary = summary.get("vendor", {})
    cust_total = cust_summary.get("entity_a_total", 0) + cust_summary.get("entity_b_total", 0) - cust_summary.get("overlap_count", 0)
    vendor_total = vendor_summary.get("entity_a_total", 0) + vendor_summary.get("entity_b_total", 0) - vendor_summary.get("overlap_count", 0)

    result = {
        "customer_overlap": {
            "total_overlapping": cust_summary.get("overlap_count", 0),
            "overlap_pct_of_combined": round(
                cust_summary.get("overlap_count", 0) / max(cust_total, 1) * 100, 2
            ),
            "overlap_pct_of_meridian": cust_summary.get("overlap_pct_a", 0),
            "overlap_pct_of_cascadia": cust_summary.get("overlap_pct_b", 0),
            "matches": _transform_customer_matches(cust_detail.get("concepts", [])),
            "concentration_threshold_crossings": [],
        },
        "vendor_overlap": {
            "total_overlapping": vendor_summary.get("overlap_count", 0),
            "overlap_pct_of_combined": round(
                vendor_summary.get("overlap_count", 0) / max(vendor_total, 1) * 100, 2
            ),
            "overlap_pct_of_meridian": vendor_summary.get("overlap_pct_a", 0),
            "overlap_pct_of_cascadia": vendor_summary.get("overlap_pct_b", 0),
            "matches": _transform_vendor_matches(vendor_detail.get("concepts", [])),
        },
        "people_overlap": _transform_people_overlap(emp_detail.get("concepts", []), summary),
    }

    # Populate concentration_threshold_crossings
    for m in result["customer_overlap"]["matches"]:
        if m["concentration_flag"]:
            result["customer_overlap"]["concentration_threshold_crossings"].append({
                "customer": m["canonical_name"],
                "pct": m["combined_pct_of_total"],
            })

    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Cross-Sell — transforms v2 opportunities + summary into CrossSellData
# ---------------------------------------------------------------------------

@router.get("/api/reports/cross-sell")
async def cross_sell():
    """Fetch cross-sell from DCL v2 and transform into CrossSellData shape."""
    opps_data, summary_data = await asyncio.gather(
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/cross-sell"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/cross-sell/summary"),
    )

    opportunities = opps_data.get("opportunities", [])

    # Split into m_to_c and c_to_m
    m_to_c = []
    c_to_m = []
    for opp in opportunities:
        candidate = {
            "customer_id": opp.get("customer", ""),
            "customer_name": opp.get("customer", ""),
            "entity_id": opp.get("current_entity", ""),
            "recommended_service": opp.get("service", ""),
            "propensity_score": 0.7,
            "estimated_acv": _parse_float(opp.get("typical_acv")),
            "industry_match": 0.8,
            "size_match": 0.8,
            "behavioral_score": 0.7,
            "engagement_fit": 0.7,
            "relationship_strength": 0.7,
            "rationale": opp.get("rationale", ""),
            "comparable_customers": [],
            "buyer_persona": "CFO",
            "customer_engagement_M": 0.0,
            "years_as_client": 0,
            "industry": "",
            "segment": "",
        }
        if opp.get("opportunity_entity", "").lower().startswith("c"):
            m_to_c.append(candidate)
        else:
            c_to_m.append(candidate)

    by_direction = summary_data.get("by_direction", {})
    m_to_c_acv = sum(c["estimated_acv"] for c in m_to_c)
    c_to_m_acv = sum(c["estimated_acv"] for c in c_to_m)

    result = {
        "m_to_c": m_to_c,
        "c_to_m": c_to_m,
        "summary": {
            "m_to_c_candidates": len(m_to_c),
            "m_to_c_total_acv": round(m_to_c_acv, 2),
            "m_to_c_high_conf_count": len([c for c in m_to_c if c["propensity_score"] > 0.8]),
            "m_to_c_high_conf_acv": round(sum(c["estimated_acv"] for c in m_to_c if c["propensity_score"] > 0.8), 2),
            "c_to_m_candidates": len(c_to_m),
            "c_to_m_total_acv": round(c_to_m_acv, 2),
            "c_to_m_high_conf_count": len([c for c in c_to_m if c["propensity_score"] > 0.8]),
            "c_to_m_high_conf_acv": round(sum(c["estimated_acv"] for c in c_to_m if c["propensity_score"] > 0.8), 2),
            "total_candidates": summary_data.get("total_opportunities", len(opportunities)),
            "total_pipeline_acv": round(summary_data.get("total_potential_acv", m_to_c_acv + c_to_m_acv), 2),
            "total_high_conf_acv": round(sum(
                c["estimated_acv"] for c in m_to_c + c_to_m if c["propensity_score"] > 0.8
            ), 2),
        },
    }
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# EBITDA Bridge — transforms v2 bridge into EBITDABridgeData
# ---------------------------------------------------------------------------

@router.get("/api/reports/ebitda-bridge")
async def ebitda_bridge(entity_id: str = Query(None)):
    """Fetch EBITDA bridge from DCL v2 and transform into EBITDABridgeData shape."""
    # Discover entities dynamically from DCL
    entity_ids = await asyncio.to_thread(_get_entity_ids)

    # Fetch per-entity bridges + combined
    entity_bridges: Dict[str, Dict] = {}
    fetch_tasks = []
    for eid in entity_ids:
        fetch_tasks.append(asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/bridge", {"entity_id": eid}))
    fetch_tasks.append(asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/bridge"))

    results = await asyncio.gather(*fetch_tasks)
    for i, eid in enumerate(entity_ids):
        entity_bridges[eid] = results[i]
    combined_bridge = results[-1]

    # Transform adjustments into BridgeAdjustment shape
    def _to_bridge_adj(adj: Dict, entity: str) -> Dict:
        return {
            "name": adj.get("name", ""),
            "category": adj.get("lever", "normalization"),
            "entity": entity,
            "confidence": str(adj.get("confidence", 0.5)),
            "amount": adj.get("amount", 0),
            "amount_low": adj.get("amount_low", 0),
            "amount_high": adj.get("amount_high", 0),
            "lever": adj.get("lever"),
            "support_reference": adj.get("support_reference", ""),
            "rationale": adj.get("rationale", ""),
        }

    entity_adjustments = []
    combination_synergies = []
    for adj in combined_bridge.get("adjustments", []):
        ba = _to_bridge_adj(adj, "combined")
        if adj.get("lever") == "synergy":
            combination_synergies.append(ba)
        else:
            entity_adjustments.append(ba)

    # Build reported/adjusted dicts keyed by entity ID
    reported_ebitda: Dict[str, Any] = {}
    adjusted_ebitda: Dict[str, Any] = {}
    total_reported = 0.0
    for eid, bridge in entity_bridges.items():
        rep = bridge.get("reported_ebitda", 0)
        adj = bridge.get("adjusted_ebitda", 0)
        reported_ebitda[eid] = rep
        adjusted_ebitda[eid] = adj
        total_reported += rep
    reported_ebitda["combined_reported"] = total_reported
    adjusted_ebitda["combined"] = combined_bridge.get("adjusted_ebitda", 0)
    combined_adjusted = combined_bridge.get("adjusted_ebitda", 0)

    synergy_total = combined_bridge.get("by_lever", {}).get("synergy", 0)
    pf_year1 = combined_adjusted + synergy_total * 0.5
    pf_steady = combined_adjusted + synergy_total

    result = {
        "reported_ebitda": reported_ebitda,
        "entity_adjustments": entity_adjustments,
        "entity_adjusted_ebitda": adjusted_ebitda,
        "combination_synergies": combination_synergies,
        "pro_forma_ebitda": {
            "year_1": {"low": round(pf_year1 * 0.9, 2), "high": round(pf_year1 * 1.1, 2), "current": round(pf_year1, 2)},
            "steady_state": {"low": round(pf_steady * 0.9, 2), "high": round(pf_steady * 1.1, 2), "current": round(pf_steady, 2)},
        },
        "ev_impact": {
            "multiple": 8.0,
            "year_1_ev": {"low": round(pf_year1 * 7, 2), "high": round(pf_year1 * 9, 2), "current": round(pf_year1 * 8, 2)},
            "steady_state_ev": {"low": round(pf_steady * 7, 2), "high": round(pf_steady * 9, 2), "current": round(pf_steady * 8, 2)},
        },
    }
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# QoE — transforms v2 combined QoE into QofEData
# ---------------------------------------------------------------------------

@router.get("/api/reports/qoe")
async def quality_of_earnings(entity_id: str = Query(None)):
    """Fetch QoE from DCL v2 and transform into QofEData shape."""
    # Fetch QoE and bridge concurrently (was sequential — ~16s → ~8s)
    qoe_data, bridge = await asyncio.gather(
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/qoe/combined"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/bridge"),
    )

    entity_a = qoe_data.get("entity_a", {})
    entity_b = qoe_data.get("entity_b", {})
    combined = qoe_data.get("combined", {})
    adjustments = []
    for adj in bridge.get("adjustments", []):
        adjustments.append({
            "name": adj.get("name", ""),
            "category": adj.get("lever", "normalization"),
            "entity": "combined",
            "confidence": str(adj.get("confidence", 0.5)),
            "current_amount": adj.get("amount", 0),
            "diligence_amount": None,
            "prior_amount": None,
            "amount_low": adj.get("amount_low", 0),
            "amount_high": adj.get("amount_high", 0),
            "lever": adj.get("lever"),
            "support_reference": adj.get("support_reference", ""),
            "rationale": adj.get("rationale", ""),
            "status": "active",
            "lifecycle_stage": "initial_diligence",
            "trend": "stable",
        })

    # Revenue quality from entity_a
    rev_quality = entity_a.get("revenue_quality", {})
    total_rev = rev_quality.get("total_revenue", 0)
    by_stream = rev_quality.get("by_stream", [])

    # Margin trend from combined
    margin_trend = combined.get("margin_trend", [])

    reported = combined.get("reported_ebitda", 0)
    adjusted = combined.get("adjusted_ebitda", 0)
    synergy = bridge.get("by_lever", {}).get("synergy", 0)

    result = {
        "period": "2025-Q1",
        "is_initial_diligence": True,
        "ebitda_bridge": adjustments,
        "adjustment_lifecycle": {
            "lifecycle_stages": {"initial_diligence": {"count": len(adjustments), "items": [a["name"] for a in adjustments]}},
            "status_counts": {"active": len(adjustments)},
            "total_adjustments": len(adjustments),
        },
        "revenue_quality": {
            "customer_concentration": {
                "hhi": 0,
                "top_10_pct": 0,
                "top_20_pct": 0,
                "top_50_pct": 0,
                "threshold_alerts": [],
                "total_customers": 0,
            },
            "contract_quality": {
                "msa_pct": 0,
                "sow_pct": 0,
                "t_and_m_pct": 0,
                "avg_tenure_years": 0,
            },
            "revenue_mix": {
                "recurring_pct": 0,
                "non_recurring_pct": 0,
                "advisory_consulting_M": 0,
                "managed_services_M": 0,
                "per_fte_M": 0,
                "per_transaction_M": 0,
            },
            "cohort_retention": [],
            "cross_sell_penetration": {
                "total_candidates": 0,
                "total_pipeline_acv_M": 0,
                "converted_count": 0,
                "converted_acv_M": 0,
                "conversion_rate_pct": 0,
            },
        },
        "sustainability_score": {
            "overall": combined.get("confidence_weighted_ebitda", adjusted) / max(adjusted, 1) * 100 if adjusted else 0,
            "components": [],
            "grade": "B",
        },
        "working_capital": {
            "dso_trend": [],
            "dpo_trend": [],
            "bench_cost_trend": [],
            "working_capital_pct_trend": [],
            "margin_trend": [
                {"period": m["period"], "gross_margin_pct": 0, "ebitda_margin_pct": m.get("ebitda_margin", 0)}
                for m in margin_trend
            ],
        },
        "new_items": [],
        "summary": {
            "reported_ebitda": reported,
            "entity_adjusted_ebitda": adjusted,
            "pro_forma_year_1": round(adjusted + synergy * 0.5, 2),
            "pro_forma_steady_state": round(adjusted + synergy, 2),
            "total_adjustments": len(adjustments),
            "active_adjustments": len(adjustments),
            "resolved_adjustments": 0,
            "new_adjustments": 0,
            "changed_adjustments": 0,
            "sustainability_score": round(combined.get("confidence_weighted_ebitda", adjusted) / max(adjusted, 1) * 100, 1) if adjusted else 0,
            "sustainability_grade": "B",
        },
    }
    return JSONResponse(content=result)


@router.get("/api/reports/revenue-by-customer")
async def revenue_by_customer(
    entity_id: str = Query(..., description="Entity ID — dynamic, resolved from DCL engagement state"),
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
