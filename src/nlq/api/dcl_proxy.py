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
    except httpx.RemoteProtocolError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DCL disconnected during GET {url}: {exc}",
        )
    if resp.status_code != 200:
        # When DCL returns 422 (data_incomplete), extract the clean detail
        # message so the frontend displays a helpful error instead of raw JSON.
        if resp.status_code == 422:
            try:
                body = resp.json()
                detail_obj = body.get("detail", {})
                if isinstance(detail_obj, dict) and detail_obj.get("error") == "data_incomplete":
                    raise HTTPException(
                        status_code=422,
                        detail=detail_obj.get("detail", resp.text[:500]),
                    )
            except (ValueError, KeyError):
                pass
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code} for GET {url}: {resp.text[:500]}",
        )
    return resp.json()


def _get_entity_ids() -> List[str]:
    """Fetch financial entity IDs from DCL's active engagement.

    Uses engagement_state (entity_a, entity_b) — not a raw distinct query
    on semantic_triples, which could include non-financial entities.
    """
    engagement = _dcl_get("/api/dcl/triples/engagement")
    entities = []
    ea = engagement.get("entity_a")
    if ea and ea.get("id"):
        entities.append(ea["id"])
    eb = engagement.get("entity_b")
    if eb and eb.get("id"):
        entities.append(eb["id"])
    if not entities:
        raise HTTPException(
            status_code=404,
            detail=(
                "No financial entities found in DCL engagement state — "
                "cannot build report. Ensure an active engagement exists "
                "with entity_a and entity_b set."
            ),
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

    # Split into m_to_c and c_to_m — pass through DCL v2 scored fields unchanged.
    # All DCL values are in $M. Frontend formatter handles display scaling.
    m_to_c = []
    c_to_m = []
    for opp in opportunities:
        candidate = {
            "customer_id": opp.get("customer_id", opp.get("customer", "")),
            "customer_name": opp.get("customer_name", opp.get("customer", "")),
            "entity_id": opp.get("current_entity", ""),
            "recommended_service": opp.get("recommended_service", opp.get("service", "")),
            "propensity_score": opp.get("propensity_score", 0),
            "estimated_acv": _parse_float(opp.get("estimated_acv", opp.get("typical_acv"))),
            "industry_match": opp.get("industry_match", 0),
            "size_match": opp.get("size_match", 0),
            "behavioral_score": opp.get("behavioral_score", 0),
            "engagement_fit": opp.get("engagement_fit", 0),
            "relationship_strength": opp.get("relationship_strength", 0),
            "rationale": opp.get("rationale", ""),
            "comparable_customers": opp.get("comparable_customers", []),
            "buyer_persona": opp.get("buyer_persona", "CFO"),
            "customer_engagement_M": _parse_float(opp.get("customer_engagement_M")),
            "years_as_client": opp.get("years_as_client", 0),
            "industry": opp.get("industry", ""),
            "segment": opp.get("segment", ""),
        }
        if opp.get("opportunity_entity", "").lower().startswith("c"):
            m_to_c.append(candidate)
        else:
            c_to_m.append(candidate)

    m_to_c_acv = sum(c["estimated_acv"] for c in m_to_c)
    c_to_m_acv = sum(c["estimated_acv"] for c in c_to_m)
    high_conf_threshold = 80  # propensity_score is 0-100 integer scale

    result = {
        "m_to_c": m_to_c,
        "c_to_m": c_to_m,
        "summary": {
            "m_to_c_candidates": len(m_to_c),
            "m_to_c_total_acv": m_to_c_acv,
            "m_to_c_high_conf_count": len([c for c in m_to_c if c["propensity_score"] >= high_conf_threshold]),
            "m_to_c_high_conf_acv": sum(c["estimated_acv"] for c in m_to_c if c["propensity_score"] >= high_conf_threshold),
            "c_to_m_candidates": len(c_to_m),
            "c_to_m_total_acv": c_to_m_acv,
            "c_to_m_high_conf_count": len([c for c in c_to_m if c["propensity_score"] >= high_conf_threshold]),
            "c_to_m_high_conf_acv": sum(c["estimated_acv"] for c in c_to_m if c["propensity_score"] >= high_conf_threshold),
            "total_candidates": summary_data.get("total_opportunities", len(opportunities)),
            "total_pipeline_acv": m_to_c_acv + c_to_m_acv,
            "total_high_conf_acv": sum(
                c["estimated_acv"] for c in m_to_c + c_to_m if c["propensity_score"] >= high_conf_threshold
            ),
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


def _build_revenue_quality(
    entity_a: Dict, entity_b: Dict, combined: Dict,
    total_rev: float, by_stream: List[Dict], cross_sell: Dict,
) -> Dict:
    """Build revenue_quality section from real DCL data."""
    # Revenue mix from by_stream
    stream_map: Dict[str, float] = {}
    for s in by_stream:
        concept = s.get("concept", "")
        val = round(float(s.get("value", 0)), 2)
        name = concept.split(".", 1)[1] if "." in concept else concept
        stream_map[name] = val

    # Classify recurring vs non-recurring
    recurring_concepts = {"managed_services", "per_fte", "per_transaction", "fixed_fee"}
    recurring_total = sum(v for k, v in stream_map.items() if k in recurring_concepts)
    non_recurring_total = sum(v for k, v in stream_map.items() if k not in recurring_concepts)
    recurring_pct = round(recurring_total / total_rev * 100, 1) if total_rev else 0
    non_recurring_pct = round(non_recurring_total / total_rev * 100, 1) if total_rev else 0

    # Cross-sell penetration from real cross-sell data
    cs_opps = cross_sell.get("opportunities", [])
    cs_total = cross_sell.get("total", len(cs_opps))
    cs_pipeline_acv = round(sum(_parse_float(o.get("estimated_acv", 0)) for o in cs_opps), 2)
    high_conf = [o for o in cs_opps if o.get("propensity_score", 0) >= 70]
    high_conf_acv = round(sum(_parse_float(o.get("estimated_acv", 0)) for o in high_conf), 2)

    return {
        "customer_concentration": {
            "hhi": 0,  # Not computable without per-customer revenue breakdown
            "top_10_pct": 0,
            "top_20_pct": 0,
            "top_50_pct": 0,
            "threshold_alerts": [],
            "total_customers": 0,
        },
        "contract_quality": {
            "msa_pct": 0,  # Not in triple store
            "sow_pct": 0,
            "t_and_m_pct": 0,
            "avg_tenure_years": 0,
        },
        "revenue_mix": {
            "recurring_pct": recurring_pct,
            "non_recurring_pct": non_recurring_pct,
            "advisory_consulting_M": stream_map.get("consulting", 0),
            "managed_services_M": stream_map.get("managed_services", 0),
            "per_fte_M": stream_map.get("per_fte", 0),
            "per_transaction_M": stream_map.get("per_transaction", 0),
        },
        "cohort_retention": [],
        "cross_sell_penetration": {
            "total_candidates": cs_total,
            "total_pipeline_acv_M": cs_pipeline_acv,
            "converted_count": len(high_conf),
            "converted_acv_M": high_conf_acv,
            "conversion_rate_pct": round(len(high_conf) / cs_total * 100, 1) if cs_total else 0,
        },
    }


# ---------------------------------------------------------------------------
# QoE — transforms v2 combined QoE into QofEData
# ---------------------------------------------------------------------------

@router.get("/api/reports/qoe")
async def quality_of_earnings(entity_id: str = Query(None)):
    """Fetch QoE from DCL v2 and transform into QofEData shape."""
    # Fetch QoE, bridge, and cross-sell concurrently
    qoe_data, bridge, cross_sell = await asyncio.gather(
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/qoe/combined"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/bridge"),
        asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/cross-sell"),
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

    # Revenue quality — merge both entities' streams for combined view
    rev_a = entity_a.get("revenue_quality", {})
    rev_b = entity_b.get("revenue_quality", {})
    total_rev = rev_a.get("total_revenue", 0) + rev_b.get("total_revenue", 0)
    by_stream = rev_a.get("by_stream", []) + rev_b.get("by_stream", [])

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
        "revenue_quality": _build_revenue_quality(
            entity_a, entity_b, combined, total_rev, by_stream, cross_sell,
        ),
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
    except httpx.RemoteProtocolError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DCL disconnected during revenue-by-customer query at {dcl_url}: {exc}",
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


# ---------------------------------------------------------------------------
# Combining Income Statement — transforms v2 hierarchical P&L into flat line_items
# ---------------------------------------------------------------------------

def _combining_is_to_line_items(dcl_data: dict) -> List[Dict]:
    """Transform DCL's hierarchical combining-IS response into flat line_items.

    DCL returns entity_a/entity_b/adjustments/combined with nested
    revenue/cogs/opex sub-dicts. The frontend expects a flat list where each
    row has columns named after the entities (e.g. meridian, cascadia).
    """
    entity_a = dcl_data.get("entity_a", {})
    entity_b = dcl_data.get("entity_b", {})
    adjustments = dcl_data.get("adjustments", {})
    combined = dcl_data.get("combined", {})

    def _val(section: dict, key: str) -> float:
        if isinstance(section, dict):
            v = section.get(key)
            if isinstance(v, dict):
                return round(float(v.get("total", 0)), 2)
            if v is not None:
                return round(float(v), 2)
        return 0.0

    def _sub(section: dict, key: str) -> float:
        if isinstance(section, dict):
            v = section.get(key)
            if isinstance(v, (int, float)):
                return round(float(v), 2)
            if isinstance(v, dict):
                return round(float(v.get("total", 0)), 2)
        return 0.0

    entity_a_name = str(entity_a.get("name", "entity_a"))
    entity_b_name = str(entity_b.get("name", "entity_b"))

    def _line(name: str, a_val: float, b_val: float, adj_val: float, comb_val: float) -> Dict:
        return {
            "line_item": name,
            entity_a_name: round(a_val, 2),
            entity_b_name: round(b_val, 2),
            "adjustments": round(adj_val, 2),
            "combined": round(comb_val, 2),
        }

    adj_rev = _sub(adjustments.get("revenue", {}), "total")
    adj_cogs = _sub(adjustments.get("cogs", {}), "total")
    adj_opex = _sub(adjustments.get("opex", {}), "total")
    adj_dep = _sub(adjustments.get("depreciation", {}), "total")
    adj_ebitda = float(adjustments.get("total_ebitda_impact", 0))

    rev_a = entity_a.get("revenue", {})
    rev_b = entity_b.get("revenue", {})
    rev_c = combined.get("revenue", {})
    rev_keys = sorted(set(
        k for k in list(rev_a.keys()) + list(rev_b.keys()) + list(rev_c.keys())
        if k != "total"
    ))

    line_items: List[Dict] = []

    for key in rev_keys:
        display = key.replace("_", " ").title()
        line_items.append(_line(
            f"  {display}",
            float(rev_a.get(key, 0)), float(rev_b.get(key, 0)),
            0, float(rev_c.get(key, 0)),
        ))
    line_items.append(_line(
        "Total Revenue",
        _sub(rev_a, "total"), _sub(rev_b, "total"),
        adj_rev, _sub(rev_c, "total"),
    ))

    cogs_a = entity_a.get("cogs", {})
    cogs_b = entity_b.get("cogs", {})
    cogs_c = combined.get("cogs", {})
    cogs_keys = sorted(set(
        k for k in list(cogs_a.keys()) + list(cogs_b.keys()) + list(cogs_c.keys())
        if k != "total"
    ))

    for key in cogs_keys:
        display = key.replace("_", " ").title()
        line_items.append(_line(
            f"  {display}",
            float(cogs_a.get(key, 0)), float(cogs_b.get(key, 0)),
            0, float(cogs_c.get(key, 0)),
        ))
    line_items.append(_line(
        "Total COGS",
        _sub(cogs_a, "total"), _sub(cogs_b, "total"),
        adj_cogs, _sub(cogs_c, "total"),
    ))

    gp_a = _sub(rev_a, "total") - _sub(cogs_a, "total")
    gp_b = _sub(rev_b, "total") - _sub(cogs_b, "total")
    gp_adj = adj_rev - adj_cogs
    gp_c = _sub(rev_c, "total") - _sub(cogs_c, "total")
    line_items.append(_line("Gross Profit", gp_a, gp_b, gp_adj, gp_c))

    opex_a = entity_a.get("opex", {})
    opex_b = entity_b.get("opex", {})
    opex_c = combined.get("opex", {})
    opex_keys = sorted(set(
        k for k in list(opex_a.keys()) + list(opex_b.keys()) + list(opex_c.keys())
        if k != "total"
    ))

    for key in opex_keys:
        display = key.replace("_", " ").title()
        line_items.append(_line(
            f"  {display}",
            float(opex_a.get(key, 0)), float(opex_b.get(key, 0)),
            0, float(opex_c.get(key, 0)),
        ))
    line_items.append(_line(
        "Total OpEx",
        _sub(opex_a, "total"), _sub(opex_b, "total"),
        adj_opex, _sub(opex_c, "total"),
    ))

    line_items.append(_line(
        "EBITDA",
        _val(entity_a, "ebitda"), _val(entity_b, "ebitda"),
        adj_ebitda, _val(combined, "ebitda"),
    ))

    line_items.append(_line(
        "Depreciation & Amortization",
        _val(entity_a, "depreciation_amortization"),
        _val(entity_b, "depreciation_amortization"),
        adj_dep, _val(combined, "depreciation_amortization"),
    ))

    line_items.append(_line(
        "Operating Profit",
        _val(entity_a, "operating_profit"), _val(entity_b, "operating_profit"),
        adj_ebitda - adj_dep, _val(combined, "operating_profit"),
    ))

    line_items.append(_line(
        "Tax",
        _val(entity_a, "tax"), _val(entity_b, "tax"),
        0, _val(combined, "tax"),
    ))

    line_items.append(_line(
        "Net Income",
        _val(entity_a, "net_income"), _val(entity_b, "net_income"),
        adj_ebitda - adj_dep, _val(combined, "net_income"),
    ))

    return line_items


@router.get("/api/reports/combining-is")
async def combining_income_statement(period: str = Query("2025-Q1")):
    """Fetch combining IS from DCL, transform to flat line_items for frontend.

    DCL's combining engine handles year-period aggregation natively
    (e.g. "2025" sums Q1-Q4 internally), so we pass the period through as-is.
    """
    dcl_data = await asyncio.to_thread(
        _dcl_get, "/api/reports/combining-is", {"period": period}
    )
    import re
    display_period = f"FY{period}" if re.fullmatch(r"\d{4}", period) else dcl_data.get("period", period)
    return JSONResponse(content={
        "period": display_period,
        "line_items": _combining_is_to_line_items(dcl_data),
    })


# ---------------------------------------------------------------------------
# What-If — transforms DCL v2 bridge into WhatIfResult shape
# ---------------------------------------------------------------------------

# Default lever definitions for the what-if UI
_WHATIF_LEVER_DEFS = [
    {"name": "revenue_growth", "label": "Revenue Growth", "min": -20, "max": 20, "default": 0, "unit": "%", "impact_per_point_M": None},
    {"name": "cogs_change", "label": "COGS Change", "min": -20, "max": 20, "default": 0, "unit": "%", "impact_per_point_M": None},
    {"name": "opex_change", "label": "OpEx Change", "min": -20, "max": 20, "default": 0, "unit": "%", "impact_per_point_M": None},
    {"name": "synergy_realization", "label": "Synergy Realization", "min": 0, "max": 100, "default": 50, "unit": "%", "impact_per_point_M": None},
    {"name": "headcount_change", "label": "Headcount Change", "min": -15, "max": 15, "default": 0, "unit": "%", "impact_per_point_M": None},
]

_WHATIF_PRESETS = {
    "conservative": {"revenue_growth": -5, "cogs_change": 5, "opex_change": 5, "synergy_realization": 30, "headcount_change": -5},
    "base_case": {"revenue_growth": 0, "cogs_change": 0, "opex_change": 0, "synergy_realization": 50, "headcount_change": 0},
    "optimistic": {"revenue_growth": 10, "cogs_change": -5, "opex_change": -5, "synergy_realization": 80, "headcount_change": 5},
}


@router.post("/api/reports/what-if")
async def what_if_scenario(request: Request):
    """Build WhatIfResult from DCL bridge + lever adjustments."""
    body = await request.json() if await request.body() else {}
    preset = body.get("preset")
    levers = body.get("levers")

    if preset and preset in _WHATIF_PRESETS:
        levers = _WHATIF_PRESETS[preset]
    elif not levers:
        levers = {d["name"]: d["default"] for d in _WHATIF_LEVER_DEFS}

    # Get bridge data from DCL
    bridge = await asyncio.to_thread(_dcl_get, "/api/dcl/reports/v2/bridge")

    reported = bridge.get("reported_ebitda", 0)
    adjusted = bridge.get("adjusted_ebitda", 0)
    by_lever = bridge.get("by_lever", {})
    synergy_total = by_lever.get("synergy", 0)

    # Apply levers to compute scenario
    rev_adj = levers.get("revenue_growth", 0) / 100
    cogs_adj = levers.get("cogs_change", 0) / 100
    opex_adj = levers.get("opex_change", 0) / 100
    synergy_pct = levers.get("synergy_realization", 50) / 100

    # Compute scenario EBITDA impact
    rev_delta = reported * rev_adj
    scenario_ebitda = adjusted + rev_delta - (adjusted * cogs_adj * 0.3) - (adjusted * opex_adj * 0.2)
    scenario_synergy = synergy_total * synergy_pct

    pf_year1 = round(scenario_ebitda + scenario_synergy * 0.5, 2)
    pf_steady = round(scenario_ebitda + scenario_synergy, 2)

    ev_multiple = 8.0

    # Transform bridge adjustments
    entity_adjustments = []
    synergies = []
    for adj in bridge.get("adjustments", []):
        ba = {
            "name": adj.get("name", ""),
            "category": adj.get("lever", "normalization"),
            "entity": "combined",
            "confidence": str(adj.get("confidence", 0.5)),
            "amount": adj.get("amount", 0),
            "amount_low": adj.get("amount_low", 0),
            "amount_high": adj.get("amount_high", 0),
            "lever": adj.get("lever"),
            "support_reference": adj.get("support_reference", ""),
            "rationale": adj.get("rationale", ""),
        }
        if adj.get("lever") == "synergy":
            synergies.append(ba)
        else:
            entity_adjustments.append(ba)

    result = {
        "levers": levers,
        "lever_definitions": _WHATIF_LEVER_DEFS,
        "reported_ebitda": reported,
        "entity_adjusted_ebitda": adjusted,
        "adjustments": entity_adjustments,
        "synergies": synergies,
        "pro_forma_ebitda": {"year_1": pf_year1, "steady_state": pf_steady},
        "ev_impact": {
            "year_1": round(pf_year1 * ev_multiple, 2),
            "steady_state": round(pf_steady * ev_multiple, 2),
        },
        "presets": _WHATIF_PRESETS,
    }
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Dashboard — transforms DCL v2 resolver data into DashboardData shape
# ---------------------------------------------------------------------------

@router.get("/api/reports/dashboard/{persona}")
async def dashboard(persona: str):
    """Fetch dashboard from DCL and transform into DashboardData shape."""
    dcl_data = await asyncio.to_thread(
        _dcl_get, f"/api/reports/dashboard/{persona}"
    )

    pnl = dcl_data.get("pnl", {})
    bs = dcl_data.get("balance_sheet", {})

    rev = pnl.get("revenue", {})
    cogs = pnl.get("cogs", {})
    opex = pnl.get("opex", {})
    assets = bs.get("assets", {})
    liabilities = bs.get("liabilities", {})
    equity = bs.get("equity", {})

    rev_total = float(rev.get("total", 0)) if isinstance(rev, dict) else 0
    cogs_total = float(cogs.get("total", 0)) if isinstance(cogs, dict) else 0
    ebitda = float(pnl.get("ebitda", 0))
    net_income = float(pnl.get("net_income", 0))

    # Sum asset/liability/equity totals dynamically
    def _sum_section(section: Dict) -> float:
        if not isinstance(section, dict):
            return 0
        total = 0.0
        for v in section.values():
            if isinstance(v, (int, float)):
                total += v
        return round(total, 2)

    total_assets = _sum_section(assets)
    total_liabilities = _sum_section(liabilities)
    total_equity = _sum_section(equity)

    gross_margin = round((rev_total - cogs_total) / rev_total * 100, 1) if rev_total else 0
    ebitda_margin = round(ebitda / rev_total * 100, 1) if rev_total else 0
    net_margin = round(net_income / rev_total * 100, 1) if rev_total else 0

    persona_titles = {
        "cfo": "Chief Financial Officer Dashboard",
        "cro": "Chief Revenue Officer Dashboard",
        "coo": "Chief Operating Officer Dashboard",
        "cto": "Chief Technology Officer Dashboard",
        "chro": "Chief Human Resources Officer Dashboard",
    }

    kpis = {
        "revenue_M": round(rev_total, 2),
        "ebitda_M": round(ebitda, 2),
        "net_income_M": round(net_income, 2),
        "gross_margin_pct": gross_margin,
        "ebitda_margin_pct": ebitda_margin,
        "net_margin_pct": net_margin,
        "total_assets_M": total_assets,
        "total_liabilities_M": total_liabilities,
        "total_equity_M": total_equity,
    }

    return JSONResponse(content={
        "persona": persona,
        "title": persona_titles.get(persona.lower(), f"{persona.upper()} Dashboard"),
        "entity_id": dcl_data.get("entity_id"),
        "period": dcl_data.get("period"),
        "kpis": kpis,
        "pnl": pnl,
        "balance_sheet": bs,
    })


# ---------------------------------------------------------------------------
# Financial Statements — structured endpoint (replaces NLQ query pipeline)
# ---------------------------------------------------------------------------

# P&L line items: key → (label, indent, format, is_subtotal)
_PL_LINES = [
    ("revenue",          "Revenue",                      0, "currency", False),
    ("cogs",             "Cost of Goods Sold",           1, "currency", False),
    ("gross_profit",     "Gross Profit",                 0, "currency", True),
    ("sm_expense",       "Sales & Marketing",            1, "currency", False),
    ("rd_expense",       "Research & Development",       1, "currency", False),
    ("ga_expense",       "General & Administrative",     1, "currency", False),
    ("opex",             "Total Operating Expenses",     0, "currency", True),
    ("ebitda",           "EBITDA",                       0, "currency", True),
    ("operating_profit", "Operating Profit",             0, "currency", True),
    ("net_income",       "Net Income",                   0, "currency", True),
]

# BS line items
_BS_LINES = [
    ("cash",               "Cash & Equivalents",           0, "currency", False),
    ("ar",                 "Accounts Receivable",          0, "currency", False),
    ("unbilled_revenue",   "Unbilled Revenue",             0, "currency", False),
    ("prepaid_expenses",   "Prepaid Expenses",             0, "currency", False),
    ("pp_e",               "Property, Plant & Equipment",  0, "currency", False),
    ("intangibles",        "Intangible Assets",            0, "currency", False),
    ("goodwill",           "Goodwill",                     0, "currency", False),
    ("total",              "Total Assets",                 0, "currency", True),
    ("ap",                 "Accounts Payable",             0, "currency", False),
    ("accrued_expenses",   "Accrued Expenses",             0, "currency", False),
    ("deferred_revenue",   "Deferred Revenue",             0, "currency", False),
    ("total_liabilities",  "Total Liabilities",            0, "currency", True),
    ("retained_earnings",  "Retained Earnings",            0, "currency", False),
    ("stockholders_equity","Stockholders' Equity",         0, "currency", True),
]

# CF line items
_CF_LINES = [
    ("net_income",              "Net Income",                  0, "currency", False),
    ("da_expense",              "Depreciation & Amortization", 1, "currency", False),
    ("change_in_ar",            "Change in A/R",               1, "currency", False),
    ("change_in_ap",            "Change in A/P",               1, "currency", False),
    ("change_in_deferred_rev",  "Change in Deferred Revenue",  1, "currency", False),
    ("operating_total",         "Cash from Operating Activities", 0, "currency", True),
    ("capex",                   "Capital Expenditures",        0, "currency", False),
    ("fcf",                     "Free Cash Flow",              0, "currency", True),
]

_STATEMENT_CONFIG = {
    "income_statement": ("Income Statement", _PL_LINES, "/api/dcl/reports/v2/income-statement", "/api/dcl/reports/v2/combining/income-statement"),
    "balance_sheet": ("Balance Sheet", _BS_LINES, "/api/dcl/reports/v2/balance-sheet", "/api/dcl/reports/v2/combining/balance-sheet"),
    "cash_flow": ("Statement of Cash Flows", _CF_LINES, "/api/dcl/reports/v2/cash-flow", "/api/dcl/reports/v2/combining/cash-flow"),
}

def _prior_year_period(period: str) -> str:
    """2025-Q1 → 2024-Q1, used for act_vs_py comparison."""
    parts = period.split("-")
    return f"{int(parts[0]) - 1}-{parts[1]}"


def _flatten_dcl_statement(dcl_data: dict, statement: str) -> dict:
    """Flatten DCL's nested statement dict into {key: value} for line item lookup.

    IS returns: {"revenue": {"total": X, "consulting": Y, ...}, "cogs": {...}, "ebitda": X, ...}
    BS returns: {"assets": {"total": X, "cash": Y, ...}, "liabilities": {...}, "equity": {...}}
    CF returns: {"operating": {"total": X}, "investing": {...}, "financing": {...}, "net_change": X}
    """
    flat: dict = {}
    if statement == "income_statement":
        for domain in ("revenue", "cogs", "opex"):
            section = dcl_data.get(domain, {})
            flat[domain] = section.get("total")
            for k, v in section.items():
                if k != "total":
                    flat[f"{domain}_{k}"] = v
        # Map opex sub-items to expected line item keys
        flat["sm_expense"] = flat.pop("opex_sales_marketing", None)
        flat["rd_expense"] = flat.pop("opex_research_development", None)
        flat["ga_expense"] = flat.pop("opex_general_admin", None)
        # Top-level P&L fields from DCL
        for k in ("ebitda", "gross_profit", "operating_profit", "net_income",
                   "depreciation_amortization", "tax"):
            if k in dcl_data:
                flat[k] = dcl_data[k]
        # Derive gross_profit if DCL doesn't return it
        if flat.get("gross_profit") is None:
            rev = flat.get("revenue")
            cogs = flat.get("cogs")
            if rev is not None and cogs is not None:
                flat["gross_profit"] = round(rev - cogs, 2)
    elif statement == "balance_sheet":
        # DCL's _domain_to_dict strips the first segment (e.g. "asset."),
        # yielding keys like "current.cash", "noncurrent.property_plant_equipment".
        # Remap these nested sub-keys to the flat keys _BS_LINES expects.
        _BS_ASSET_REMAP = {
            "current.cash": "cash",
            "current.accounts_receivable": "ar",
            "current.unbilled_revenue": "unbilled_revenue",
            "current.prepaid": "prepaid_expenses",
            "noncurrent.property_plant_equipment": "pp_e",
            "noncurrent.intangibles": "intangibles",
            "noncurrent.goodwill": "goodwill",
        }
        _BS_LIABILITY_REMAP = {
            "current.accounts_payable": "ap",
            "current.accrued_expenses": "accrued_expenses",
            "current.deferred_revenue": "deferred_revenue",
            "noncurrent.long_term_debt": "long_term_debt",
        }
        _BS_EQUITY_REMAP = {
            "retained_earnings": "retained_earnings",
            "common_stock": "common_stock",
        }
        assets = dcl_data.get("assets", {})
        for k, v in assets.items():
            if k == "total":
                flat["total"] = v
            else:
                flat[_BS_ASSET_REMAP.get(k, k)] = v
        liabilities = dcl_data.get("liabilities", {})
        for k, v in liabilities.items():
            if k == "total":
                flat["total_liabilities"] = v
            else:
                flat[_BS_LIABILITY_REMAP.get(k, k)] = v
        equity = dcl_data.get("equity", {})
        for k, v in equity.items():
            if k == "total":
                flat["stockholders_equity"] = v
            else:
                flat[_BS_EQUITY_REMAP.get(k, k)] = v
    elif statement == "cash_flow":
        # Remap DCL CF concept names to the keys _CF_LINES expects.
        _CF_OPERATING_REMAP = {
            "depreciation_add_back": "da_expense",
        }
        operating = dcl_data.get("operating", {})
        for k, v in operating.items():
            if k == "total":
                flat["operating_total"] = v
            else:
                flat[_CF_OPERATING_REMAP.get(k, k)] = v
        investing = dcl_data.get("investing", {})
        for k, v in investing.items():
            if k == "total":
                flat["investing_total"] = v
            else:
                flat[k] = v
        financing = dcl_data.get("financing", {})
        for k, v in financing.items():
            if k == "total":
                flat["financing_total"] = v
            else:
                flat[k] = v
        if "net_change" in dcl_data:
            flat["fcf"] = dcl_data["net_change"]
        # Pull net_income from pnl if not already present
        if "net_income" not in flat:
            flat["net_income"] = dcl_data.get("net_income")
    return flat


def _build_fs_response(
    title: str,
    entity_name: str,
    line_defs: list,
    cy_label: str,
    cy_values: dict,
    py_label: str | None,
    py_values: dict | None,
) -> dict:
    """Build FinancialStatementData-shaped dict."""
    periods = [cy_label]
    if py_values:
        periods.extend([py_label, "Variance", "Variance %"])

    line_items = []
    for key, label, indent, fmt, is_sub in line_defs:
        cv = cy_values.get(key)
        values_dict: dict = {cy_label: cv}
        if py_values:
            pv = py_values.get(key)
            values_dict[py_label] = pv
            if cv is not None and pv is not None and pv != 0:
                var = round(cv - pv, 2)
                var_pct = round((var / abs(pv)) * 100, 1)
                values_dict["Variance"] = var
                values_dict["Variance %"] = var_pct
            else:
                values_dict["Variance"] = None
                values_dict["Variance %"] = None
        line_items.append({
            "label": label,
            "key": key,
            "indent": indent,
            "format": fmt,
            "is_subtotal": is_sub,
            "values": values_dict,
        })

    return {
        "title": f"{title} — {cy_label}" + (f" vs {py_label}" if py_label else ""),
        "entity": entity_name,
        "periods": periods,
        "line_items": line_items,
        "currency": "USD",
        "unit": "millions",
    }


@router.get("/api/reports/financial-statement")
async def financial_statement(
    statement: str = Query(..., description="income_statement | balance_sheet | cash_flow"),
    variant: str = Query("full_year_act_vs_py"),
    quarter: str = Query(None, description="e.g. 2025-Q3 for quarterly variants"),
    entity_id: str = Query(None, description="Entity ID (omit for combined)"),
    segment: str = Query(None),
):
    """Structured financial statement endpoint — no NLQ query pipeline.

    Calls DCL's structured IS/BS/CF endpoints directly, assembles CY vs PY
    comparison with variances, returns FinancialStatementData shape.
    """
    if statement not in _STATEMENT_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown statement '{statement}'. Valid: income_statement, balance_sheet, cash_flow",
        )

    title, line_defs, dcl_single_path, dcl_combining_path = _STATEMENT_CONFIG[statement]

    # Resolve entity selection
    is_combined = not entity_id or entity_id == "combined"

    # Determine CY/PY periods from variant.
    # DCL now supports year-level periods (e.g. "2026") and aggregates
    # Q1-Q4 internally — no need for NLQ to make per-quarter calls.
    from datetime import date
    current_year = date.today().year
    last_full_year = current_year - 1  # Last completed fiscal year (actuals)

    if variant == "full_year_act_vs_py":
        # Actuals: last completed year vs the year before
        cy_period = str(last_full_year)
        py_period = str(last_full_year - 1)
        cy_label = f"FY {last_full_year} Actual"
        py_label = f"FY {last_full_year - 1} Actual"
    elif variant == "quarterly_act_vs_py":
        if not quarter:
            raise HTTPException(status_code=400, detail="quarter param required for quarterly variant")
        cy_period = quarter
        py_period = _prior_year_period(quarter)
        parts = quarter.split("-")
        cy_label = f"{parts[1]} {parts[0]} Actual"
        py_label = f"{parts[1]} {int(parts[0]) - 1} Actual"
    elif variant == "full_year_cf_vs_py_act":
        # Current-year forecast vs last completed year actuals
        cy_period = str(current_year)
        py_period = str(last_full_year)
        cy_label = f"FY {current_year} (Act+CF)"
        py_label = f"FY {last_full_year} Actual"
    elif variant == "quarterly_cf_vs_py":
        if not quarter:
            raise HTTPException(status_code=400, detail="quarter param required for quarterly variant")
        cy_period = quarter
        py_period = _prior_year_period(quarter)
        parts = quarter.split("-")
        cy_label = f"{parts[1]} {parts[0]} Forecast"
        py_label = f"{parts[1]} {int(parts[0]) - 1} Actual"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown variant '{variant}'")

    # Two DCL calls total: CY and PY. DCL aggregates quarters internally.
    # Issue both in parallel via ThreadPoolExecutor to halve wall-clock time.
    from concurrent.futures import ThreadPoolExecutor

    if is_combined:
        def _fetch() -> tuple:
            with ThreadPoolExecutor(max_workers=2) as pool:
                cy_f = pool.submit(_dcl_get, dcl_combining_path, {"period": cy_period})
                py_f = pool.submit(_dcl_get, dcl_combining_path, {"period": py_period})
                return cy_f.result().get("combined", {}), py_f.result().get("combined", {})
    else:
        def _fetch() -> tuple:
            with ThreadPoolExecutor(max_workers=2) as pool:
                cy_f = pool.submit(_dcl_get, dcl_single_path, {"entity_id": entity_id, "period": cy_period})
                py_f = pool.submit(_dcl_get, dcl_single_path, {"entity_id": entity_id, "period": py_period})
                return cy_f.result(), py_f.result()

    cy_raw, py_raw = await asyncio.to_thread(_fetch)

    cy_values = _flatten_dcl_statement(cy_raw, statement)
    py_values = _flatten_dcl_statement(py_raw, statement)

    # Compute derived margins for P&L
    if statement == "income_statement":
        rev = cy_values.get("revenue")
        if rev and rev != 0:
            gp = cy_values.get("gross_profit")
            if gp is not None:
                cy_values["gross_margin_pct"] = round(gp / rev * 100, 1)
            ebitda = cy_values.get("ebitda")
            if ebitda is not None:
                cy_values["ebitda_margin_pct"] = round(ebitda / rev * 100, 1)
            ni = cy_values.get("net_income")
            if ni is not None:
                cy_values["net_margin_pct"] = round(ni / rev * 100, 1)
        if py_values:
            py_rev = py_values.get("revenue")
            if py_rev and py_rev != 0:
                py_gp = py_values.get("gross_profit")
                if py_gp is not None:
                    py_values["gross_margin_pct"] = round(py_gp / py_rev * 100, 1)
                py_ebitda = py_values.get("ebitda")
                if py_ebitda is not None:
                    py_values["ebitda_margin_pct"] = round(py_ebitda / py_rev * 100, 1)
                py_ni = py_values.get("net_income")
                if py_ni is not None:
                    py_values["net_margin_pct"] = round(py_ni / py_rev * 100, 1)

    # Add margin lines to P&L if not already in line_defs
    actual_line_defs = list(line_defs)
    if statement == "income_statement":
        # Insert margin % lines after their parent
        margin_inserts = [
            (3, ("gross_margin_pct", "Gross Margin %", 0, "percent", False)),
            (9, ("ebitda_margin_pct", "EBITDA Margin %", 0, "percent", False)),
            (12, ("net_margin_pct", "Net Margin %", 0, "percent", False)),
        ]
        for offset, item in enumerate(margin_inserts):
            actual_line_defs.insert(item[0] + offset, item[1])

    entity_name = entity_id.replace("_", " ").title() if not is_combined else "Combined"

    result = _build_fs_response(
        title, entity_name, actual_line_defs,
        cy_label, cy_values, py_label, py_values,
    )
    return JSONResponse(content={"financial_statement_data": result})


# ---------------------------------------------------------------------------
# Pipeline Report
# ---------------------------------------------------------------------------

def _fetch_pipeline_stages(entity_id: str, period: str) -> List[Dict[str, Any]]:
    """Fetch pipeline stages for one entity from DCL via the semantic client."""
    from src.nlq.services.dcl_client_router import get_routed_client
    client = get_routed_client()
    return client.get_pipeline_stages(entity_id=entity_id, period=period)


def _sum_pipeline_stages(stage_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Sum pipeline stages across multiple entities and recompute percentages."""
    totals: Dict[str, float] = {}
    label_map: Dict[str, str] = {}
    # Preserve insertion order from first list that has data
    ordered_keys: List[str] = []
    for stages in stage_lists:
        for s in stages:
            key = s["label"]
            label_map[key] = key
            if key not in totals:
                ordered_keys.append(key)
                totals[key] = 0.0
            totals[key] += s["value"]

    if not ordered_keys:
        return []

    first_val = totals[ordered_keys[0]]
    if first_val == 0:
        first_val = 1.0

    return [
        {
            "label": label_map[k],
            "value": round(totals[k], 2),
            "percent": round((totals[k] / first_val) * 100, 1),
        }
        for k in ordered_keys
    ]


@router.get("/api/reports/pipeline")
async def pipeline_report(period: str = Query(...)):
    """Pipeline funnel data — per-entity panels plus a combined panel."""
    engagement = await asyncio.to_thread(_dcl_get, "/api/dcl/triples/engagement")
    entity_ids = await asyncio.to_thread(_get_entity_ids)

    # Build name lookup from engagement
    entity_names: Dict[str, str] = {}
    for key in ("entity_a", "entity_b"):
        ent = engagement.get(key)
        if ent and ent.get("id"):
            entity_names[ent["id"]] = str(ent.get("name", ent["id"]))

    panels = []
    for eid in entity_ids:
        stages = await asyncio.to_thread(_fetch_pipeline_stages, eid, period)
        panels.append({
            "entity_id": eid,
            "entity_name": entity_names.get(eid, eid),
            "period": period,
            "stages": stages,
        })

    # Combined panel: sum stages across entities
    combined_stages = _sum_pipeline_stages([p["stages"] for p in panels])
    panels.append({
        "entity_id": "combined",
        "entity_name": "Combined",
        "period": period,
        "stages": combined_stages,
    })

    return JSONResponse(content=panels)


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
    except httpx.RemoteProtocolError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DCL disconnected during report proxy GET {dcl_url}: {exc}",
        )

    if resp.status_code != 200:
        if resp.status_code == 422:
            try:
                body = resp.json()
                detail_obj = body.get("detail", {})
                if isinstance(detail_obj, dict) and detail_obj.get("error") == "data_incomplete":
                    raise HTTPException(
                        status_code=422,
                        detail=detail_obj.get("detail", resp.text[:500]),
                    )
            except (ValueError, KeyError):
                pass
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
    except httpx.RemoteProtocolError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DCL disconnected during report proxy POST {dcl_url}: {exc}",
        )

    if resp.status_code != 200:
        if resp.status_code == 422:
            try:
                body = resp.json()
                detail_obj = body.get("detail", {})
                if isinstance(detail_obj, dict) and detail_obj.get("error") == "data_incomplete":
                    raise HTTPException(
                        status_code=422,
                        detail=detail_obj.get("detail", resp.text[:500]),
                    )
            except (ValueError, KeyError):
                pass
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"DCL returned {resp.status_code}: {resp.text[:500]}",
        )

    return JSONResponse(content=resp.json(), status_code=200)
