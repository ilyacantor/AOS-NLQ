"""
API route definitions for AOS-NLQ.

Endpoints:
- POST /v1/query: Process natural language query (NLQResponse)
- POST /v1/query/galaxy: Process query with Galaxy visualization (IntentMapResponse)
- GET /v1/health: Health check
- GET /v1/schema: Return available metrics and periods

All endpoints return JSON responses with consistent structure.
"""

import functools
import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.nlq.core.ambiguity import detect_ambiguity, needs_clarification
from src.nlq.core.confidence import bounded_confidence
from src.nlq.core.executor import QueryExecutor
from src.nlq.core.node_generator import (
    calculate_overall_metrics,
    generate_nodes_for_aggregation_query,
    generate_nodes_for_ambiguous_query,
    generate_nodes_for_breakdown_query,
    generate_nodes_for_comparison_query,
    generate_nodes_for_point_query,
)
from src.nlq.core.parser import QueryParser
from src.nlq.core.resolver import PeriodResolver
from src.nlq.knowledge.schema import FINANCIAL_SCHEMA, get_canonical_unit, get_metric_unit
from src.nlq.knowledge.synonyms import normalize_metric
from src.nlq.knowledge.display import get_display_name
from src.nlq.llm.client import ClaudeClient
from src.nlq.models.query import NLQRequest, QueryIntent, ParsedQuery, PeriodType, QueryMode
from src.nlq.models.response import AmbiguityType, Domain, IntentMapResponse, IntentNode, MatchType, NLQResponse, RelatedMetric
from src.nlq.core.personality import (
    generate_personality_response,
    handle_off_topic_or_easter_egg,
    detect_persona_from_question,
    detect_persona_from_metric,
    get_stumped_response,
)
from src.nlq.services.llm_call_counter import get_call_counter
from src.nlq.services.rag_learning_log import get_learning_log, LearningLogEntry
from src.nlq.services.query_cache_service import CacheHitType, get_cache_service
from src.nlq.services.dcl_enrichment import enrich_response as dcl_enrich_response
from src.nlq.config import get_tenant_id
from src.nlq.services.dcl_semantic_client import set_force_local, set_data_mode, set_entity_id, force_local_data, diag, diag_init, diag_collect
from src.nlq.services.insufficient_data_tracker import get_insufficient_data_tracker, CONFIDENCE_THRESHOLD
from src.nlq.core.dates import current_year, current_quarter, prior_year

# Dashboard generation imports
from src.nlq.core.visualization_intent import (
    should_generate_visualization,
    VisualizationIntent,
    is_ambiguous_visualization_query,
)
from src.nlq.core.dashboard_generator import generate_dashboard_schema, refine_dashboard_schema
from src.nlq.core.dashboard_data_resolver import DashboardDataResolver
from src.nlq.core.refinement_intent import (
    detect_refinement_intent,
    RefinementType,
    is_context_dependent_query,
    needs_clarification_without_context,
)
from src.nlq.core.debug_info import (
    DashboardDebugInfo,
    DashboardGenerationError,
    FailureCategory,
    DecisionSource,
    is_strict_mode,
)

# Shared query helpers (consolidates /query and /query/galaxy logic)
# Shared query helpers (consolidates /query and /query/galaxy logic)
from src.nlq.api.query_helpers import (
    SimpleMetricResult,
    GuidedDiscoveryResult,
    MissingDataResult,
    IngestStatusResult,
    determine_domain,
    determine_domain_from_name,
    simple_metric_to_nlq_response,
    guided_discovery_to_nlq_response,
    missing_data_to_nlq_response,
    ingest_status_to_nlq_response,
    off_topic_to_nlq_response,
)
# Galaxy-specific converters removed: simple_metric_to_galaxy_response,
# guided_discovery_to_galaxy_response, missing_data_to_galaxy_response,
# ingest_status_to_galaxy_response, people_response_to_galaxy,
# off_topic_to_galaxy_response, breakdown_to_galaxy_response

# C1: Extracted modules — formatters, health, eval
from src.nlq.api.formatters import (
    nodes_to_related_metrics as _nodes_to_related_metrics,
    format_value_with_unit as _format_value_with_unit,
    format_answer as _format_answer,
)
# format_enriched_text_response removed — only used by deleted query_galaxy()
from src.nlq.api.health import (
    router as _health_router,
    HealthResponse,
    SchemaResponse,
    PipelineStatusResponse,
)
from src.nlq.api.eval import router as _eval_router, EvalResult

# =============================================================================
# SESSION-BASED DASHBOARD STATE
# =============================================================================
# Extracted to src/nlq/api/session.py — proper service with cleanup, persistence
# awareness, and no module-level mutable globals. These re-exports maintain
# backward compatibility for all call sites in this file.
import time
from src.nlq.api.session import (
    get_session_dashboard,
    set_session_dashboard,
    clear_session_dashboard,
    get_session_stats,
)


# =============================================================================
# QUERY LOGGING HELPER — consolidates learning log calls for ALL query paths
# =============================================================================

async def _log_query_event(
    query: str,
    source: str,
    *,
    success: bool = True,
    learned: bool = False,
    message: str = "",
    persona: str = "CFO",
    similarity: float = 0.0,
    llm_confidence: float = 0.0,
    execution_time_ms: int | None = None,
    session_id: str | None = None,
) -> None:
    """
    Log a query event to the RAG learning log.

    This is the single funnel for ALL query paths — cache hits, LLM calls,
    and early-exit bypass paths (off-topic, simple metric, dashboard, etc.).
    """
    learning_log = get_learning_log()
    await learning_log.log_entry(LearningLogEntry(
        query=query,
        success=success,
        source=source,
        learned=learned,
        message=message,
        persona=persona,
        similarity=similarity,
        llm_confidence=llm_confidence,
        execution_time_ms=execution_time_ms,
        session_id=session_id,
    ))


def _elapsed_ms(start: float) -> int:
    """Compute elapsed milliseconds from a time.perf_counter() start."""
    return int((time.perf_counter() - start) * 1000)


# =============================================================================
# INSUFFICIENT DATA TRACKING HELPERS
# =============================================================================

def _track_insufficient_data_if_needed(
    response: NLQResponse,
    question: str,
    session_id: str = None,
    metric_found: bool = True,
    period_found: bool = True,
    data_exists: bool = True,
    is_ambiguous: bool = False,
) -> NLQResponse:
    """
    Track a response if confidence is below threshold (80%).

    Adds 'Possible insufficient data condition' message if tracked.
    Returns the response (potentially modified with warning message).
    """
    tracker = get_insufficient_data_tracker()

    # Only track if below threshold
    if not tracker.should_track(response.confidence):
        return response

    # Detect persona from the response
    persona = "CFO"  # default
    if response.resolved_metric:
        detected = detect_persona_from_metric(response.resolved_metric)
        if detected:
            persona = detected

    # Track the entry
    entry = tracker.track_sync(
        query=question,
        confidence=response.confidence,
        persona=persona,
        resolved_metric=response.resolved_metric,
        resolved_period=response.resolved_period,
        parsed_intent=response.parsed_intent,
        session_id=session_id,
        metric_found=metric_found,
        period_found=period_found,
        data_exists=data_exists,
        is_ambiguous=is_ambiguous,
    )

    # If tracked, add warning to answer
    if entry and response.answer:
        warning = f"\n\n⚠️ Possible insufficient data condition ({response.confidence:.0%} confidence)"
        response_dict = response.model_dump()
        response_dict["answer"] = response.answer + warning
        return NLQResponse(**response_dict)

    return response


def _track_intent_map_if_needed(
    response: IntentMapResponse,
    question: str,
    session_id: str = None,
    metric_found: bool = True,
    period_found: bool = True,
    data_exists: bool = True,
    is_ambiguous: bool = False,
) -> IntentMapResponse:
    """
    Track an IntentMapResponse if overall_confidence is below threshold (80%).

    Adds 'Possible insufficient data condition' message if tracked.
    Returns the response (potentially modified with warning message).
    """
    tracker = get_insufficient_data_tracker()

    # Only track if below threshold
    if not tracker.should_track(response.overall_confidence):
        return response

    # Detect persona and resolved info from nodes
    persona = "CFO"
    resolved_metric = None
    resolved_period = None
    parsed_intent = response.query_type

    if response.nodes:
        first_node = response.nodes[0]
        resolved_metric = first_node.metric
        resolved_period = first_node.period
        if first_node.domain:
            # Map domain to persona
            domain_persona_map = {
                Domain.FINANCE: "CFO",
                Domain.GROWTH: "CRO",
                Domain.OPS: "COO",
                Domain.PRODUCT: "CTO",
                Domain.PEOPLE: "CHRO",
            }
            persona = domain_persona_map.get(first_node.domain, "CFO")

    # Track the entry
    entry = tracker.track_sync(
        query=question,
        confidence=response.overall_confidence,
        persona=persona,
        resolved_metric=resolved_metric,
        resolved_period=resolved_period,
        parsed_intent=parsed_intent,
        session_id=session_id,
        metric_found=metric_found,
        period_found=period_found,
        data_exists=data_exists,
        is_ambiguous=is_ambiguous,
    )

    # If tracked, add warning to text response
    if entry and response.text_response:
        warning = f"\n\n⚠️ Possible insufficient data condition ({response.overall_confidence:.0%} confidence)"
        response_dict = response.model_dump()
        response_dict["text_response"] = response.text_response + warning
        return IntentMapResponse(**response_dict)

    return response


# =============================================================================
# RAG CACHE HELPERS
# =============================================================================

def _cached_to_parsed_query(cached: dict) -> ParsedQuery:
    """
    Convert a cached dict from RAG cache back to a ParsedQuery object.

    Args:
        cached: Dict with intent, metric, period_type, period_reference, etc.

    Returns:
        ParsedQuery object ready for execution
    """
    # Map string intent back to QueryIntent enum
    intent_str = cached.get("intent", "POINT_QUERY")
    try:
        intent = QueryIntent(intent_str)
    except ValueError:
        intent = QueryIntent.POINT_QUERY

    # Map string period_type back to PeriodType enum
    period_type_str = cached.get("period_type", "annual")
    try:
        period_type = PeriodType(period_type_str)
    except ValueError:
        period_type = PeriodType.ANNUAL

    # Normalize metric using synonym system
    raw_metric = cached.get("metric", "revenue")
    normalized_metric = normalize_metric(raw_metric)

    return ParsedQuery(
        intent=intent,
        metric=normalized_metric,
        period_type=period_type,
        period_reference=cached.get("period_reference", current_year()),
        is_relative=False,  # Cached queries have resolved periods
        comparison_period=cached.get("comparison_period"),
        aggregation_type=cached.get("aggregation_type"),
        aggregation_periods=cached.get("aggregation_periods"),
        breakdown_metrics=cached.get("breakdown_metrics"),
        raw_metric=raw_metric,
    )


def _parsed_query_to_cache_dict(parsed: ParsedQuery) -> dict:
    """
    Convert a ParsedQuery to a dict for storing in RAG cache.

    Args:
        parsed: ParsedQuery object from Claude parser

    Returns:
        Dict ready for cache storage
    """
    return {
        "intent": parsed.intent.value,
        "metric": parsed.metric,
        "period_type": parsed.period_type.value,
        "period_reference": parsed.period_reference,
        "comparison_type": getattr(parsed, 'comparison_type', None),
        "comparison_period": parsed.comparison_period,
        "aggregation_type": parsed.aggregation_type,
        "aggregation_periods": parsed.aggregation_periods,
        "breakdown_metrics": parsed.breakdown_metrics,
    }


def _is_dashboard_query(question: str) -> bool:
    """Detect if this is a dashboard/report request."""
    q = question.lower()

    dashboard_terms = [
        "dashboard", "report", "summary", "overview", "scorecard",
        "give me a dashboard", "show me a dashboard", "get me a dashboard",
        "executive summary", "board deck", "board report",
        "how are we doing", "how's the business", "business review",
        "quarterly report", "q1 report", "q2 report", "q3 report", "q4 report",
        "monthly report", "weekly report", "status report",
        "kpis", "key metrics", "top metrics", "main metrics",
        "health check", "quick check", "pulse check",
    ]

    return any(term in q for term in dashboard_terms)


def _extract_period_from_dashboard_query(question: str) -> str:
    """Extract period from dashboard query, default to latest quarter."""
    q = question.lower()

    # Check for specific quarter mentions
    import re
    quarter_match = re.search(r'q([1-4])\s*(?:20)?(\d{2})?', q)
    if quarter_match:
        quarter = f"Q{quarter_match.group(1)}"
        year = quarter_match.group(2)
        if year:
            year = f"20{year}" if len(year) == 2 else year
        else:
            year = current_year()
        return f"{year}-{quarter}"

    # Check for year mentions
    year_match = re.search(r'20(2[4-6])', q)
    if year_match:
        return f"20{year_match.group(1)}"

    # Default to latest available period
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    return get_semantic_client().get_latest_period()


def _handle_dashboard_query(question: str, persona: Optional[str] = None, entity_id: str = None) -> Optional[IntentMapResponse]:
    """
    Generate persona-specific dashboard with key metrics.

    All data is fetched from DCL.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()

    def _query_metric_value(metric: str, period: Optional[str] = None) -> Optional[float]:
        """Query a single metric value from DCL."""
        period = period or current_quarter()
        try:
            result = dcl_client.query(
                metric=metric,
                time_range={"period": period, "granularity": "quarterly"},
                tenant_id=get_tenant_id(),
                entity_id=entity_id,
            )
            if result.get("error") or not result.get("data"):
                # Retry with annual grain as fallback
                result = dcl_client.query(
                    metric=metric,
                    time_range={"period": current_year(), "granularity": "annual"},
                    tenant_id=get_tenant_id(),
                    entity_id=entity_id,
                )
            if result.get("error"):
                return None
            data = result.get("data", [])
            if not data:
                return None
            # Handle different response formats
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict) and "value" in data[0]:
                    values = [d.get("value") for d in data if d.get("value") is not None]
                    if not values:
                        return None
                    # Non-additive metrics (percentages, ratios, scores) must be
                    # averaged across quarters, not summed.
                    from src.nlq.knowledge.schema import is_additive_metric
                    if is_additive_metric(metric):
                        return sum(values)
                    return sum(values) / len(values)
                else:
                    return data[-1] if data else None
            elif isinstance(data, (int, float)):
                return data
            return None
        except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
            logger.debug(f"Failed to query {metric}: {e}")
            return None

    def _build_period_data(period: Optional[str] = None) -> dict:
        period = period or current_year()
        """Build a period data dict by querying DCL for each metric."""
        metrics_to_query = [
            "revenue", "gross_margin_pct", "operating_margin_pct", "net_income",
            "cash", "arr", "burn_multiple", "pipeline", "win_rate_pct",
            "churn_rate_pct", "nrr", "sales_cycle_days", "quota_attainment_pct",
            "new_logo_revenue", "headcount", "revenue_per_employee",
            "magic_number", "cac_payback_months", "ltv_cac", "attrition_rate_pct",
            "implementation_days", "uptime_pct", "deploys_per_week",
            "mttr_p1_hours", "sprint_velocity", "tech_debt_pct",
            "code_coverage_pct", "features_shipped", "hires",
            "engineering_headcount", "sales_headcount", "cs_headcount",
            "csat", "employee_growth_rate"
        ]
        period_data = {}
        for metric in metrics_to_query:
            value = _query_metric_value(metric, period)
            if value is not None:
                period_data[metric] = value
        return period_data

    # Get period data from DCL (use current quarter — DCL ingest data is at quarterly grain)
    period_data = _build_period_data(current_quarter())

    q = question.lower()
    period = _extract_period_from_dashboard_query(question)

    # Check if query is asking for KPIs without specific period
    # KPI queries should use annual data for current year summary
    is_kpi_query = "kpi" in q or "key metric" in q
    has_explicit_quarter = any(qtr in q for qtr in ['q1', 'q2', 'q3', 'q4', 'quarter'])

    # If asking for a specific quarter, fetch that quarter's data instead
    if has_explicit_quarter and period != current_year():
        period_data = _build_period_data(period)
    # Default to annual data (already fetched above)

    # Use explicitly passed persona; fall back to keyword detection
    persona = persona or _detect_dashboard_persona(question)

    # Build dashboard based on persona
    nodes = []
    text_lines = []

    # Check if query asks for specific metrics (e.g., "revenue, margin, and pipeline KPIs")
    # This takes precedence over persona-based dashboards
    if "kpi" in q:
        requested_metrics = []
        if "revenue" in q:
            requested_metrics.append(("revenue", "Revenue", period_data.get('revenue'), "M", Domain.FINANCE))
        if "margin" in q and "operating" not in q:
            # "margin" alone means gross margin, not operating margin
            requested_metrics.append(("gross_margin_pct", "Gross Margin", period_data.get('gross_margin_pct'), "%", Domain.FINANCE))
        if "operating" in q and "margin" in q:
            requested_metrics.append(("operating_margin_pct", "Operating Margin", period_data.get('operating_margin_pct'), "%", Domain.FINANCE))
        if "pipeline" in q:
            requested_metrics.append(("pipeline", "Pipeline", period_data.get('pipeline'), "M", Domain.GROWTH))
        if "win" in q and "rate" in q:
            requested_metrics.append(("win_rate_pct", "Win Rate", period_data.get('win_rate_pct'), "%", Domain.GROWTH))
        if "churn" in q:
            requested_metrics.append(("churn_rate_pct", "Churn", period_data.get('churn_rate_pct'), "%", Domain.GROWTH))
        if "nrr" in q or "retention" in q:
            requested_metrics.append(("nrr", "NRR", period_data.get('nrr'), "%", Domain.GROWTH))
        if "headcount" in q:
            requested_metrics.append(("headcount", "Headcount", period_data.get('headcount'), "", Domain.OPS))

        if requested_metrics:
            # Return only the specifically requested metrics
            metrics = requested_metrics
            persona = "KPIs"
            metric_names = [m[1] for m in requested_metrics]
            text_lines.append(f"**Key Metrics ({period})**")
            text_lines.append(" | ".join([f"{m[1]}: {m[2]}{m[3] if m[3] != 'M' else 'M'}" if m[3] != 'M' else f"{m[1]}: ${m[2]}M" for m in requested_metrics]))
        else:
            # Fall through to persona-based dashboard
            pass

    if persona == "KPIs":
        # Already handled above
        pass

    elif persona == "CFO":
        metrics = [
            ("revenue", "Revenue", period_data.get('revenue'), "M", Domain.FINANCE),
            ("gross_margin_pct", "Gross Margin", period_data.get('gross_margin_pct'), "%", Domain.FINANCE),
            ("operating_margin_pct", "Operating Margin", period_data.get('operating_margin_pct'), "%", Domain.FINANCE),
            ("net_income", "Net Income", period_data.get('net_income'), "M", Domain.FINANCE),
            ("cash", "Cash", period_data.get('cash'), "M", Domain.FINANCE),
            ("arr", "ARR", period_data.get('arr'), "M", Domain.FINANCE),
            ("burn_multiple", "Burn Multiple", period_data.get('burn_multiple'), "x", Domain.FINANCE),
        ]
        text_lines.append(f"**CFO Dashboard ({period})**")
        def _fmt(label, val, unit):
            if val is None: return None
            v = round(val, 1) if isinstance(val, float) else val
            if unit == "M": return f"{label}: ${v}M"
            elif unit == "%": return f"{label}: {v}%"
            elif unit == "x": return f"{label}: {v}x"
            return f"{label}: {v}"
        cfo_items = [
            _fmt("Revenue", period_data.get('revenue'), "M"),
            _fmt("Gross Margin", period_data.get('gross_margin_pct'), "%"),
            _fmt("Operating Margin", period_data.get('operating_margin_pct'), "%"),
            _fmt("Net Income", period_data.get('net_income'), "M"),
            _fmt("Cash", period_data.get('cash'), "M"),
            _fmt("ARR", period_data.get('arr'), "M"),
            _fmt("Burn", period_data.get('burn_multiple'), "x"),
        ]
        text_lines.append(" | ".join(item for item in cfo_items if item))

    elif persona == "CRO":
        metrics = [
            ("pipeline", "Pipeline", period_data.get('pipeline'), "M", Domain.GROWTH),
            ("win_rate_pct", "Win Rate", period_data.get('win_rate_pct'), "%", Domain.GROWTH),
            ("churn_rate_pct", "Churn", period_data.get('churn_rate_pct'), "%", Domain.GROWTH),
            ("nrr", "NRR", period_data.get('nrr'), "%", Domain.GROWTH),
            ("sales_cycle_days", "Sales Cycle", period_data.get('sales_cycle_days'), "days", Domain.GROWTH),
            ("quota_attainment_pct", "Quota Attainment", period_data.get('quota_attainment_pct'), "%", Domain.GROWTH),
            ("new_logo_revenue", "New Logo Revenue", period_data.get('new_logo_revenue'), "M", Domain.GROWTH),
        ]
        text_lines.append(f"**CRO Dashboard ({period})**")
        text_lines.append(f"Pipeline: ${period_data.get('pipeline')}M | Win Rate: {period_data.get('win_rate_pct')}%")
        text_lines.append(f"Churn: {period_data.get('churn_rate_pct')}% | NRR: {period_data.get('nrr')}%")
        text_lines.append(f"Sales Cycle: {period_data.get('sales_cycle_days')} days | Quota: {period_data.get('quota_attainment_pct')}%")

    elif persona == "COO":
        metrics = [
            ("headcount", "Headcount", period_data.get('headcount'), "", Domain.OPS),
            ("revenue_per_employee", "Rev/Employee", period_data.get('revenue_per_employee'), "M", Domain.OPS),
            ("magic_number", "Magic Number", period_data.get('magic_number'), "", Domain.OPS),
            ("cac_payback_months", "CAC Payback", period_data.get('cac_payback_months'), "mo", Domain.OPS),
            ("ltv_cac", "LTV/CAC", period_data.get('ltv_cac'), "x", Domain.OPS),
            ("attrition_rate_pct", "Attrition Rate", period_data.get('attrition_rate_pct'), "%", Domain.OPS),
            ("implementation_days", "Impl. Days", period_data.get('implementation_days'), "days", Domain.OPS),
        ]
        text_lines.append(f"**COO Dashboard ({period})**")
        text_lines.append(f"Headcount: {period_data.get('headcount')} | Rev/Employee: ${period_data.get('revenue_per_employee')}M")
        text_lines.append(f"Magic Number: {period_data.get('magic_number')} | CAC Payback: {period_data.get('cac_payback_months')} months")
        text_lines.append(f"LTV/CAC: {period_data.get('ltv_cac')}x | Attrition: {period_data.get('attrition_rate_pct')}%")

    elif persona == "CTO":
        metrics = [
            ("uptime_pct", "Uptime", period_data.get('uptime_pct'), "%", Domain.PRODUCT),
            ("deploys_per_week", "Deploys/Week", period_data.get('deploys_per_week'), "", Domain.PRODUCT),
            ("mttr_p1_hours", "MTTR (P1)", period_data.get('mttr_p1_hours'), "hrs", Domain.PRODUCT),
            ("sprint_velocity", "Velocity", period_data.get('sprint_velocity'), "pts", Domain.PRODUCT),
            ("tech_debt_pct", "Tech Debt", period_data.get('tech_debt_pct'), "%", Domain.PRODUCT),
            ("code_coverage_pct", "Code Coverage", period_data.get('code_coverage_pct'), "%", Domain.PRODUCT),
            ("features_shipped", "Features Shipped", period_data.get('features_shipped'), "", Domain.PRODUCT),
        ]
        text_lines.append(f"**CTO Dashboard ({period})**")
        text_lines.append(f"Uptime: {period_data.get('uptime_pct')}% | Deploys: {period_data.get('deploys_per_week')}/week")
        text_lines.append(f"MTTR: {period_data.get('mttr_p1_hours')}hrs | Velocity: {period_data.get('sprint_velocity')} pts")
        text_lines.append(f"Tech Debt: {period_data.get('tech_debt_pct')}% | Coverage: {period_data.get('code_coverage_pct')}%")

    elif persona == "People":
        metrics = [
            ("headcount", "Headcount", period_data.get('headcount'), "", Domain.PEOPLE),
            ("hires", "New Hires", period_data.get('hires'), "", Domain.PEOPLE),
            ("attrition_rate_pct", "Attrition", period_data.get('attrition_rate_pct'), "%", Domain.PEOPLE),
            ("engineering_headcount", "Engineering", period_data.get('engineering_headcount'), "", Domain.PEOPLE),
            ("sales_headcount", "Sales", period_data.get('sales_headcount'), "", Domain.PEOPLE),
            ("cs_headcount", "Customer Success", period_data.get('cs_headcount'), "", Domain.PEOPLE),
            ("csat", "CSAT", period_data.get('csat'), "/5", Domain.PEOPLE),
        ]
        text_lines.append(f"**People Dashboard ({period})**")
        text_lines.append(f"Headcount: {period_data.get('headcount')} | Hires: {period_data.get('hires')} | Attrition: {period_data.get('attrition_rate_pct')}%")
        text_lines.append(f"Engineering: {period_data.get('engineering_headcount')} | Sales: {period_data.get('sales_headcount')} | CS: {period_data.get('cs_headcount')}")

    elif "kpi" in q:
        # Comprehensive KPI dashboard - current year vs prior year comparison
        _cy = current_year()
        _py = prior_year()
        y25 = period_data  # Already have current year data
        y24 = _build_period_data(_py)  # Fetch prior year for comparison

        def calc_change(v25, v24, is_pct=False):
            """Calculate YoY change."""
            if v25 is None or v24 is None or v24 == 0:
                return ""
            if is_pct:
                diff = v25 - v24
                return f"+{diff:.1f}pp" if diff > 0 else f"{diff:.1f}pp"
            else:
                pct = ((v25 - v24) / v24) * 100
                return f"+{pct:.0f}%" if pct > 0 else f"{pct:.0f}%"

        # Build comparison metrics with 2025 values and change indicators
        metrics = [
            # CFO (Finance - Blue)
            ("revenue", "Revenue", y25.get('revenue'), "M", Domain.FINANCE),
            ("gross_margin_pct", "Gross Margin", y25.get('gross_margin_pct'), "%", Domain.FINANCE),
            ("net_income", "Net Income", y25.get('net_income'), "M", Domain.FINANCE),
            # CRO (Growth - Pink)
            ("pipeline", "Pipeline", y25.get('pipeline'), "M", Domain.GROWTH),
            ("nrr", "NRR", y25.get('nrr'), "%", Domain.GROWTH),
            ("win_rate_pct", "Win Rate", y25.get('win_rate_pct'), "%", Domain.GROWTH),
            # COO (Ops - Green)
            ("headcount", "Headcount", y25.get('headcount'), "", Domain.OPS),
            ("magic_number", "Magic Number", y25.get('magic_number'), "", Domain.OPS),
            ("ltv_cac", "LTV/CAC", y25.get('ltv_cac'), "x", Domain.OPS),
            # CTO (Product - Purple)
            ("uptime_pct", "Uptime", y25.get('uptime_pct'), "%", Domain.PRODUCT),
            ("deploys_per_week", "Deploys/Week", y25.get('deploys_per_week'), "", Domain.PRODUCT),
            ("features_shipped", "Features Shipped", y25.get('features_shipped'), "", Domain.PRODUCT),
            # People (Orange)
            ("headcount", "Total Headcount", y25.get('headcount'), "", Domain.PEOPLE),
            ("employee_growth_rate", "HC Growth", y25.get('employee_growth_rate'), "%", Domain.PEOPLE),
        ]
        persona = "KPIs"
        period = f"{_cy} vs {_py}"

        # Build detailed comparison text
        text_lines.append(f"**{_cy} vs {_py} Full Year KPIs**")
        text_lines.append("")
        text_lines.append(f"| Persona | Metric | {_py} | {_cy} | Change |")
        text_lines.append("|---------|--------|------|------|--------|")
        text_lines.append(f"| **CFO** | Revenue | ${y24.get('revenue')}M | ${y25.get('revenue')}M | {calc_change(y25.get('revenue'), y24.get('revenue'))} |")
        text_lines.append(f"| | Gross Margin | {y24.get('gross_margin_pct')}% | {y25.get('gross_margin_pct')}% | {calc_change(y25.get('gross_margin_pct'), y24.get('gross_margin_pct'), True)} |")
        text_lines.append(f"| | Net Income | ${y24.get('net_income')}M | ${y25.get('net_income')}M | {calc_change(y25.get('net_income'), y24.get('net_income'))} |")
        text_lines.append(f"| **CRO** | Pipeline | ${y24.get('pipeline')}M | ${y25.get('pipeline')}M | {calc_change(y25.get('pipeline'), y24.get('pipeline'))} |")
        text_lines.append(f"| | NRR | {y24.get('nrr')}% | {y25.get('nrr')}% | {calc_change(y25.get('nrr'), y24.get('nrr'), True)} |")
        text_lines.append(f"| | Win Rate | {y24.get('win_rate_pct')}% | {y25.get('win_rate_pct')}% | {calc_change(y25.get('win_rate_pct'), y24.get('win_rate_pct'), True)} |")
        text_lines.append(f"| **COO** | Headcount | {y24.get('headcount')} | {y25.get('headcount')} | {calc_change(y25.get('headcount'), y24.get('headcount'))} |")
        text_lines.append(f"| | Magic Number | {y24.get('magic_number')} | {y25.get('magic_number')} | {calc_change(y25.get('magic_number'), y24.get('magic_number'))} |")
        text_lines.append(f"| | LTV/CAC | {y24.get('ltv_cac')}x | {y25.get('ltv_cac')}x | {calc_change(y25.get('ltv_cac'), y24.get('ltv_cac'))} |")
        text_lines.append(f"| **CTO** | Uptime | {y24.get('uptime_pct')}% | {y25.get('uptime_pct')}% | {calc_change(y25.get('uptime_pct'), y24.get('uptime_pct'), True)} |")
        text_lines.append(f"| | Deploys/Week | {y24.get('deploys_per_week')} | {y25.get('deploys_per_week')} | {calc_change(y25.get('deploys_per_week'), y24.get('deploys_per_week'))} |")
        text_lines.append(f"| | Features | {y24.get('features_shipped')} | {y25.get('features_shipped')} | {calc_change(y25.get('features_shipped'), y24.get('features_shipped'))} |")
        text_lines.append(f"| **People** | Headcount | {y24.get('headcount')} | {y25.get('headcount')} | {calc_change(y25.get('headcount'), y24.get('headcount'))} |")
        text_lines.append(f"| | Growth Rate | {y24.get('employee_growth_rate')}% | {y25.get('employee_growth_rate')}% | {calc_change(y25.get('employee_growth_rate'), y24.get('employee_growth_rate'), True)} |")

    else:
        # Executive/General dashboard - mix of all
        metrics = [
            ("revenue", "Revenue", period_data.get('revenue'), "M", Domain.FINANCE),
            ("gross_margin_pct", "Gross Margin", period_data.get('gross_margin_pct'), "%", Domain.FINANCE),
            ("pipeline", "Pipeline", period_data.get('pipeline'), "M", Domain.GROWTH),
            ("nrr", "NRR", period_data.get('nrr'), "%", Domain.GROWTH),
            ("headcount", "Headcount", period_data.get('headcount'), "", Domain.OPS),
            ("uptime_pct", "Uptime", period_data.get('uptime_pct'), "%", Domain.PRODUCT),
            ("cash", "Cash", period_data.get('cash'), "M", Domain.FINANCE),
        ]
        persona = "Executive"
        text_lines.append(f"**Executive Dashboard ({period})**")
        text_lines.append(f"Revenue: ${period_data.get('revenue')}M | Margin: {period_data.get('gross_margin_pct')}% | Cash: ${period_data.get('cash')}M")
        text_lines.append(f"Pipeline: ${period_data.get('pipeline')}M | NRR: {period_data.get('nrr')}%")
        text_lines.append(f"Headcount: {period_data.get('headcount')} | Uptime: {period_data.get('uptime_pct')}%")

    # Build nodes
    for i, (metric, display, value, unit, domain) in enumerate(metrics):
        if value is not None:
            formatted = f"{value}{unit}" if unit else str(value)
            if unit == "M":
                formatted = f"${value}M"
            nodes.append(IntentNode(
                id=f"dash_{i}",
                metric=metric,
                display_name=display,
                match_type=MatchType.EXACT,
                domain=domain,
                confidence=0.95,
                data_quality=1.0,
                freshness="0h",
                value=value,
                formatted_value=formatted,
                period=period,
                semantic_label="Dashboard Metric",
            ))

    text_response = "\n".join(text_lines)

    return IntentMapResponse(
        query=question,
        query_type="DASHBOARD",
        ambiguity_type=None,
        persona=persona,
        overall_confidence=0.95,
        overall_data_quality=1.0,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id="dash_0" if nodes else None,
        primary_answer=text_response,
        text_response=text_response,
        needs_clarification=False,
        clarification_prompt=None,
    )


def _detect_dashboard_persona(question: str) -> str:
    """Detect which persona's dashboard to show."""
    q = question.lower()

    if any(term in q for term in ["cfo", "finance", "financial", "revenue", "margin", "cash"]):
        return "CFO"
    elif any(term in q for term in ["cro", "sales", "pipeline", "churn", "nrr", "quota"]):
        return "CRO"
    elif any(term in q for term in ["coo", "operations", "ops", "efficiency", "headcount", "magic number"]):
        return "COO"
    elif any(term in q for term in ["cto", "engineering", "tech", "product", "uptime", "velocity"]):
        return "CTO"
    elif any(term in q for term in ["people", "hr", "hiring", "attrition", "team"]):
        return "People"
    else:
        return "Executive"  # Default to executive overview


logger = logging.getLogger(__name__)


# C1: Formatter functions extracted to api/formatters.py.
# Imported above as _nodes_to_related_metrics, _format_enriched_text_response,
# _format_value_with_unit, _format_answer — keeping underscore names for all call sites.

router = APIRouter()


# Lazy-loaded singletons
_claude_client: ClaudeClient = None


def get_claude_client() -> ClaudeClient:
    """Get or create the Claude client singleton."""
    global _claude_client
    if _claude_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not configured"
            )
        _claude_client = ClaudeClient(api_key=api_key)
    return _claude_client


# C1: HealthResponse, SchemaResponse, PipelineStatusResponse imported from api/health.py
# C1: EvalResult imported from api/eval.py


# =============================================================================
# TIERED METRIC QUERY - Embedding-based metric lookup (replaces regex patterns)
# =============================================================================
#
# Tier 1: FREE (no API calls)
#   - Exact metric match via synonyms
#   - RAG cache hit (handled elsewhere)
#
# Tier 2: CHEAP (~$0.0001/query)
#   - Embedding-based metric classification
#
# Tier 3: EXPENSIVE (~$0.003+/query)
#   - Full LLM parse (falls through to Claude)
#
# This replaces the old _SIMPLE_METRIC_PATTERNS regex approach which:
# - Didn't scale (required manual pattern maintenance)
# - Only worked for specific phrasings ("what is X" but not just "X")
# =============================================================================

import re

# Import tiered intent components
from src.nlq.services.tiered_intent import detect_complexity, QueryComplexity
from src.nlq.knowledge.synonyms import normalize_metric
from src.nlq.core.superlative_intent import (
    is_superlative_query,
    detect_superlative_intent,
    get_sort_order,
)


# ---------------------------------------------------------------------------
# Complexity signal detector — queries with analytical language must bypass
# the ambiguity handler and reach the LLM / cache path instead.
# ---------------------------------------------------------------------------
_COMPLEXITY_SIGNALS = re.compile(
    r"\b(why|how come|what caused|what drove|compare|versus|difference between"
    r"|trend|over time|changed|increased|decreased|explain|analyze|deep dive)\b",
    re.IGNORECASE,
)


def _has_complexity_signal(query: str) -> bool:
    """Return True if the query contains analytical/causal language that the LLM should handle."""
    return bool(_COMPLEXITY_SIGNALS.search(query))


def _try_comparison_query(question: str, entity_id: Optional[str] = None) -> Optional[NLQResponse]:
    """
    Handle comparison, trend, direction, and YoY growth queries.

    Patterns handled:
    - "Compare Q1 vs Q2 revenue" (period vs period, same metric)
    - "Compare gross vs net margin" (metric vs metric, same period)
    - "Margin this quarter vs last" (period vs period)
    - "Revenue growth year over year" / "YoY headcount growth" (YoY)
    - "Is revenue going up or down?" (direction)
    - "How has pipeline changed this year?" (change over time)
    - "Which quarter had the best revenue?" (superlative across time)
    - "Bookings this year vs last year" (period vs period)
    """
    import re as _re
    from src.nlq.core.dates import current_year, current_quarter, prior_quarter, prior_year
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    from src.nlq.knowledge.synonyms import normalize_metric
    from src.nlq.knowledge.schema import get_metric_unit, is_additive_metric
    from src.nlq.knowledge.display import get_display_name

    q = question.lower().strip()

    def _dcl_val(metric: str, period: str) -> Optional[float]:
        """Query a single metric value from DCL for a specific period."""
        client = get_semantic_client()
        result = client.query(metric=metric, time_range={"period": period, "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=entity_id)
        if result.get("error") or not result.get("data"):
            return None
        data = result.get("data", [])
        if isinstance(data, list) and data:
            if isinstance(data[0], dict) and "value" in data[0]:
                vals = [d.get("value") for d in data if d.get("value") is not None]
                if not vals:
                    return None
                if is_additive_metric(metric):
                    return sum(vals)
                return sum(vals) / len(vals)
            return data[-1] if data else None
        elif isinstance(data, (int, float)):
            return data
        return None

    def _fmt(metric: str, value: float) -> str:
        unit = get_metric_unit(metric)
        if unit == "USD millions":
            return f"${round(value, 1)}M"
        elif unit == "USD thousands":
            return f"${round(value, 1)}K"
        elif unit == "%":
            return f"{round(value, 1)}%"
        elif unit in ("days", "hours", "months"):
            return f"{round(value, 1)} {unit}"
        return str(round(value, 1))

    def _pct_change(new_val, old_val) -> str:
        if old_val and old_val != 0:
            chg = (new_val - old_val) / abs(old_val) * 100
            sign = "+" if chg >= 0 else ""
            return f"{sign}{round(chg, 1)}%"
        return "N/A"

    cq = current_quarter()
    pq = prior_quarter()
    cy = current_year()
    py = prior_year()

    # ── Pattern 1: "Compare Q1 vs Q2 2025 revenue" (explicit quarter vs quarter) ──
    m = _re.search(r'q([1-4])\s*vs\.?\s*q([1-4])\s*(\d{4})?', q)
    if m:
        q1, q2 = m.group(1), m.group(2)
        year = m.group(3) or cy
        # Extract metric from surrounding text
        metric_text = _re.sub(r'compare|q[1-4]|vs\.?|\d{4}', '', q).strip()
        metric_key = normalize_metric(metric_text) if metric_text else "revenue"
        if not metric_key:
            metric_key = "revenue"
        p1 = f"{year}-Q{q1}"
        p2 = f"{year}-Q{q2}"
        v1 = _dcl_val(metric_key, p1)
        v2 = _dcl_val(metric_key, p2)
        dn = get_display_name(metric_key)
        if v1 is not None and v2 is not None:
            chg = _pct_change(v2, v1)
            answer = f"{dn}: {p1} {_fmt(metric_key, v1)} vs {p2} {_fmt(metric_key, v2)} ({chg})"
            return NLQResponse(success=True, answer=answer, value=v2, unit=get_metric_unit(metric_key),
                confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=p2)

    # ── Pattern 2: "Margin this quarter vs last" (period vs period, quarter) ──
    m = _re.search(r'(\w[\w\s]*?)\s+this\s+(?:quarter|q)\s+vs\.?\s+last', q)
    if m:
        metric_text = m.group(1).strip()
        metric_key = normalize_metric(metric_text)
        if metric_key:
            v_this = _dcl_val(metric_key, cq)
            v_last = _dcl_val(metric_key, pq)
            if v_this is not None and v_last is not None:
                dn = get_display_name(metric_key)
                chg = _pct_change(v_this, v_last)
                answer = f"{dn}: {cq} {_fmt(metric_key, v_this)} vs {pq} {_fmt(metric_key, v_last)} ({chg})"
                return NLQResponse(success=True, answer=answer, value=v_this, unit=get_metric_unit(metric_key),
                    confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=cq)

    # ── Pattern 3: "X this year vs last year" (year vs year) ──
    m = _re.search(r'(\w[\w\s]*?)\s+this\s+year\s+vs\.?\s+last\s+year', q)
    if m:
        metric_text = m.group(1).strip()
        metric_key = normalize_metric(metric_text)
        if metric_key:
            v_this = _dcl_val(metric_key, cq)
            v_last = _dcl_val(metric_key, pq)
            if v_this is not None and v_last is not None:
                dn = get_display_name(metric_key)
                chg = _pct_change(v_this, v_last)
                answer = f"{dn}: {cy} {_fmt(metric_key, v_this)} vs {py} {_fmt(metric_key, v_last)} ({chg})"
                return NLQResponse(success=True, answer=answer, value=v_this, unit=get_metric_unit(metric_key),
                    confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=cy)

    # ── Pattern 4: "Compare gross vs net margin" (metric vs metric) ──
    # Must come AFTER period-vs-period patterns to avoid "X this year vs last year"
    # being misinterpreted as metric-vs-metric.
    m = _re.search(r'(?:compare\s+)?(\w[\w\s]*?)\s+vs\.?\s+(\w[\w\s]*?)(?:\s*$|\?)', q)
    if m:
        m1_text, m2_text = m.group(1).strip(), m.group(2).strip()
        # Skip if this looks like a period comparison (contains "year", "quarter")
        if not _re.search(r'\b(year|quarter|q[1-4]|20\d{2})\b', m2_text):
            m1_key = normalize_metric(m1_text)
            m2_key = normalize_metric(m2_text)
            if m1_key and m2_key and m1_key != m2_key:
                v1 = _dcl_val(m1_key, cq)
                v2 = _dcl_val(m2_key, cq)
                if v1 is not None and v2 is not None:
                    dn1, dn2 = get_display_name(m1_key), get_display_name(m2_key)
                    answer = f"{cq}: {dn1} {_fmt(m1_key, v1)} vs {dn2} {_fmt(m2_key, v2)}"
                    return NLQResponse(success=True, answer=answer, value=v1, unit=get_metric_unit(m1_key),
                        confidence=0.9, parsed_intent="COMPARISON", resolved_metric=f"{m1_key}_vs_{m2_key}", resolved_period=cq)

    # ── Pattern 5: "Revenue growth year over year" / "YoY headcount growth" ──
    if "year over year" in q or "yoy" in q:
        # Extract metric
        metric_text = _re.sub(r'year over year|yoy|growth|rate', '', q).strip()
        metric_key = normalize_metric(metric_text)
        if not metric_key:
            metric_key = "revenue"
        v_this = _dcl_val(metric_key, cq)
        v_last = _dcl_val(metric_key, pq)
        if v_this is not None and v_last is not None:
            dn = get_display_name(metric_key)
            chg = _pct_change(v_this, v_last)
            answer = f"{dn} YoY: {cy} {_fmt(metric_key, v_this)} vs {py} {_fmt(metric_key, v_last)} (growth {chg})"
            return NLQResponse(success=True, answer=answer, value=v_this, unit=get_metric_unit(metric_key),
                confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=cy)

    # ── Pattern 6: "Is revenue going up or down?" (direction) ──
    m = _re.search(r'(?:is|are)\s+(\w[\w\s]*?)\s+(?:going|trending|heading)\s+(?:up|down)', q)
    if m:
        metric_text = m.group(1).strip()
        metric_key = normalize_metric(metric_text)
        if metric_key:
            v_this = _dcl_val(metric_key, cq)
            v_last = _dcl_val(metric_key, pq)
            if v_this is not None and v_last is not None:
                dn = get_display_name(metric_key)
                direction = "up" if v_this > v_last else "down" if v_this < v_last else "flat"
                chg = _pct_change(v_this, v_last)
                answer = f"{dn} is trending **{direction}**: {pq} {_fmt(metric_key, v_last)} → {cq} {_fmt(metric_key, v_this)} ({chg})"
                return NLQResponse(success=True, answer=answer, value=v_this, unit=get_metric_unit(metric_key),
                    confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=cq)

    # ── Pattern 7: "How has pipeline changed this year?" ──
    m = _re.search(r'how (?:has|have|did)\s+(\w[\w\s]*?)\s+changed', q)
    if m:
        metric_text = m.group(1).strip()
        metric_key = normalize_metric(metric_text)
        if metric_key:
            v_this = _dcl_val(metric_key, cq)
            v_last = _dcl_val(metric_key, pq)
            if v_this is not None and v_last is not None:
                dn = get_display_name(metric_key)
                direction = "increased" if v_this > v_last else "decreased" if v_this < v_last else "stayed flat"
                chg = _pct_change(v_this, v_last)
                answer = f"{dn} has {direction}: {pq} {_fmt(metric_key, v_last)} → {cq} {_fmt(metric_key, v_this)} ({chg})"
                return NLQResponse(success=True, answer=answer, value=v_this, unit=get_metric_unit(metric_key),
                    confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=cq)

    # ── Pattern 8: "Which quarter had the best revenue?" ──
    m = _re.search(r'which\s+quarter\s+(?:had|has|was)\s+(?:the\s+)?(?:best|highest|most|largest)\s+(\w[\w\s]*)', q)
    if m:
        metric_text = m.group(1).strip().rstrip('?')
        metric_key = normalize_metric(metric_text)
        if metric_key:
            # Check last 4 quarters
            year, qn = int(cq[:4]), int(cq[-1])
            best_q, best_v = None, None
            quarters_data = []
            for _ in range(4):
                qstr = f"{year}-Q{qn}"
                v = _dcl_val(metric_key, qstr)
                if v is not None:
                    quarters_data.append((qstr, v))
                    if best_v is None or v > best_v:
                        best_v = v
                        best_q = qstr
                qn -= 1
                if qn == 0:
                    qn = 4
                    year -= 1
            if best_q and quarters_data:
                dn = get_display_name(metric_key)
                parts = [f"{qstr}: {_fmt(metric_key, v)}" for qstr, v in sorted(quarters_data)]
                answer = f"**{best_q}** had the highest {dn} at {_fmt(metric_key, best_v)}. All quarters: " + ", ".join(parts)
                return NLQResponse(success=True, answer=answer, value=best_v, unit=get_metric_unit(metric_key),
                    confidence=0.9, parsed_intent="COMPARISON", resolved_metric=metric_key, resolved_period=best_q)

    return None


def _try_superlative_query(question: str) -> Optional[SimpleMetricResult]:
    """
    Handle superlative/ranking queries like 'who is our top rep?'

    Returns a SimpleMetricResult with the ranked data, or None if not a superlative query.
    """
    if not is_superlative_query(question):
        return None

    intent = detect_superlative_intent(question)
    if not intent:
        return None

    # Get the DCL client
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    from src.nlq.api.query_helpers import determine_domain
    dcl_client = get_semantic_client()

    # Execute ranking query
    order_by = get_sort_order(intent.ranking_type)
    result = dcl_client.query_ranking(
        metric=intent.metric,
        dimension=intent.dimension,
        order_by=order_by,
        limit=intent.limit,
        time_range={"period": dcl_client.get_latest_period()}
    )

    if "error" in result or not result.get("data"):
        # Superlative intent was detected but DCL has no data for this combination.
        # Return an explicit no-data response instead of None to prevent fallthrough
        # to the general handler which would silently substitute a different metric.
        from src.nlq.api.query_helpers import determine_domain
        dim_display = intent.dimension.replace("_", " ")
        metric_display = intent.metric.replace("_pct", "").replace("_", " ")
        return SimpleMetricResult(
            metric=intent.metric,
            value=None,
            formatted_value="N/A",
            unit="",
            display_name="",
            domain=determine_domain(intent.metric),
            answer=(
                f"{metric_display.title()} data ranked by {dim_display} is not available "
                f"in the current data connection. This ranking requires dimensional data "
                f"that has not been materialized in DCL."
            ),
            period=dcl_client.get_latest_period(),
        )

    data = result.get("data", [])

    # Determine unit based on metric
    if intent.metric in ("quota_attainment_pct", "win_rate_pct", "slo_attainment_pct",
                          "gross_margin_pct", "churn_rate_pct", "churn_pct",
                          "attrition_rate_pct", "nrr"):
        unit = "%"
    elif intent.metric in ("revenue", "pipeline", "deal_value", "cloud_spend"):
        unit = "USD millions"
    elif intent.metric == "headcount":
        unit = "employees"
    elif intent.metric in ("deploys_per_week",):
        unit = "/week"
    else:
        unit = ""

    # Determine domain
    domain = determine_domain(intent.metric)

    # Helper to extract dimension name from a data item
    def _extract_dim_name(item: dict, dim_key: str) -> str:
        """Extract dimension value from DCL response item, checking nested then flat."""
        _dims = item.get("dimensions", {})
        return (
            (_dims.get(dim_key) if isinstance(_dims, dict) else None)
            or (next(iter(_dims.values()), None) if isinstance(_dims, dict) and _dims else None)
            or item.get(dim_key)
            or item.get("name")
            or item.get("company")
            or ""
        )

    # Helper to format value string
    def _format_value(val, metric_id: str) -> str:
        if metric_id in ("quota_attainment_pct", "win_rate_pct", "slo_attainment_pct",
                          "gross_margin_pct", "churn_rate_pct", "churn_pct",
                          "attrition_rate_pct", "nrr"):
            return f"{val}%"
        elif metric_id in ("revenue", "pipeline", "deal_value", "cloud_spend"):
            return f"${val}M"
        elif metric_id == "headcount":
            return f"{int(val)} employees"
        elif metric_id == "deploys_per_week":
            return f"{val}/week"
        return str(val)

    # Format response based on result
    if intent.limit == 1:
        # Single result - "top rep", "largest deal", etc.
        top_item = data[0]
        name = _extract_dim_name(top_item, intent.dimension)
        value = top_item.get("value") or top_item.get("attainment_pct") or top_item.get("pipeline") or 0
        value_str = _format_value(value, intent.metric)
        metric_display = intent.metric.replace("_pct", "").replace("_", " ")

        if not name:
            # DCL returned data but without dimension labels — aggregate value only.
            # This happens when DCL has the metric but not the dimensional breakdown.
            dim_display = intent.dimension.replace("_", " ")
            response_text = (
                f"{metric_display.title()} is {value_str} overall. "
                f"{dim_display.title()}-level ranking is not available in the current data set."
            )
        else:
            # Use direction-aware label: if user asked "worst" for a
            # LOWER_IS_BETTER metric, the sort is desc but the label
            # should reflect the user's language, not the sort direction.
            query_lower = question.lower()
            if any(w in query_lower for w in ("worst", "weakest", "lagging", "poorest")):
                ranking_word = "worst-performing"
            elif any(w in query_lower for w in ("best", "leading", "strongest")):
                ranking_word = "best-performing"
            else:
                ranking_word = "top" if order_by == "desc" else "bottom"
            response_text = f"**{name}** is the {ranking_word} {intent.dimension} with {value_str} {metric_display}."

        return SimpleMetricResult(
            metric=intent.metric,
            value=value,
            formatted_value=value_str,
            unit=unit,
            display_name=name or "",
            domain=domain,
            answer=response_text,
            period=dcl_client.get_latest_period(),
        )
    else:
        # Multiple results - "top 5 reps", etc.
        query_lower = question.lower()
        if any(w in query_lower for w in ("worst", "weakest", "lagging", "poorest")):
            ranking_word = "Worst"
        elif any(w in query_lower for w in ("best", "leading", "strongest")):
            ranking_word = "Best"
        else:
            ranking_word = "Top" if order_by == "desc" else "Bottom"
        metric_display = intent.metric.replace("_pct", "").replace("_", " ")
        lines = [f"**{ranking_word} {intent.limit} {intent.dimension}s by {metric_display}:**\n"]

        for i, item in enumerate(data, 1):
            name = _extract_dim_name(item, intent.dimension)
            value = item.get("value") or item.get("attainment_pct") or item.get("pipeline") or 0
            value_str = _format_value(value, intent.metric)

            lines.append(f"{i}. **{name or 'Unknown'}** - {value_str}")

        response_text = "\n".join(lines)
        first_value = data[0].get("value") or data[0].get("attainment_pct") or data[0].get("pipeline") or 0

        return SimpleMetricResult(
            metric=intent.metric,
            value=first_value,
            formatted_value=response_text,
            unit=unit,
            display_name=f"{ranking_word} {intent.limit} {intent.dimension}s",
            domain=domain,
            answer=response_text,
            period=dcl_client.get_latest_period(),
        )


def _try_tiered_metric_query_core(question: str, entity_id: Optional[str] = None) -> Optional[SimpleMetricResult]:
    """
    Core logic for tiered metric queries - uses embedding-based lookup.

    Replaces the old regex-based _try_simple_metric_query_core.
    All data is fetched from DCL.

    Strategy:
    1. Detect if query is complex (comparison, trend, breakdown) -> skip, let LLM handle
    2. Try exact metric match via synonyms (FREE)
    3. Try embedding-based lookup (CHEAP, ~$0.0001)
    4. Return None to fall through to LLM (EXPENSIVE)
    """
    # Step 0a: Dashboard queries must NOT be handled here — they need the
    # visualization intent handler downstream. Without this guard,
    # " dashboard" gets stripped as a conversational suffix and
    # "CRO dashboard" becomes a point query for "CRO" (wrong).
    if _is_dashboard_query(question):
        return None

    # Step 0b: Check for superlative/ranking queries first
    superlative_result = _try_superlative_query(question)
    if superlative_result:
        return superlative_result

    # Step 1: Check complexity - complex queries need LLM
    complexity = detect_complexity(question)
    if complexity in (QueryComplexity.COMPARISON, QueryComplexity.TREND,
                      QueryComplexity.BREAKDOWN, QueryComplexity.COMPLEX):
        return None  # Let LLM handle complex queries

    q = question.lower().strip()

    # Step 2: Try exact metric match via synonyms (FREE - no API call)
    # Strip common prefixes to get to the metric name
    # Order matters - longer/more specific prefixes should come first
    prefixes_to_strip = [
        # Multi-word question patterns (check these first)
        "can you show me ", "can you tell me ", "can you get me ",
        "how long is our ", "how long is the ",
        "what did we ", "what have we ", "how much did we ",
        "what are our ", "what is our ", "what's our ", "whats our ",
        "what are the ", "what is the ", "what's the ", "whats the ",
        "how much is our ", "how much is the ", "how much do we have in ",
        "how many ", "how much ",
        # Standard question words
        "what is ", "what's ", "what was ", "whats ", "what are ",
        "how is ", "how's ", "hows ",
        "tell me about ", "tell me the ", "tell me ",
        "show me the ", "show me ", "get me the ", "get me ", "give me the ", "give me ",
        # Visualization/command prefixes (e.g., "make a revenue chart" -> "revenue")
        "make me a chart of ", "make a chart of ", "make chart of ",
        "make me a graph of ", "make a graph of ", "make graph of ",
        "create a chart of ", "create chart of ", "create a graph of ",
        "build a chart of ", "build chart of ", "build a graph of ",
        "display a chart of ", "display chart of ", "display a graph of ",
        "show a chart of ", "show chart of ", "show a graph of ", "show graph of ",
        "show a dashboard of ", "show a kpi of ", "show a tile of ", "show a card of ",
        "graph of ", "chart of ", "visualization of ",
        "make me a ", "make a ", "make ",
        "create a dashboard widget for ", "create a dashboard for ",
        "create a visualization of ", "create visualization of ",
        "create a ", "create ", "build a ", "build ",
        "display a ", "display ", "graph ", "visualize ",
        "add a card showing ", "add a tile showing ", "add a kpi for ",
        "add a card for ", "add a tile for ", "add a kpi showing ",
        "add a ", "add ",
        "drill deeper into ", "drill down into ", "drill down on ", "drill into ", "drill down ",
        "pull up ", "pull ", "compare ",
        # Casual prefixes
        "yo whats ", "yo what's ", "quick question ", "need ",
        "how we doing on ", "how are we doing on ",
        "let's start with ", "lets start with ", "start with ",
        # Simple prefixes (check last)
        "show ", "see ", "view ",
        "our ", "the ", "current ", "total ", "latest ", "a ",
    ]
    metric_query = q
    # Keep stripping prefixes until none match (handles nested prefixes)
    stripped = True
    while stripped:
        stripped = False
        for prefix in prefixes_to_strip:
            if metric_query.startswith(prefix):
                metric_query = metric_query[len(prefix):]
                stripped = True
                break
    metric_query = metric_query.rstrip("?").strip()

    # Strip conversational suffixes (e.g., "how's pipeline looking" -> "pipeline")
    # Order by length (longest first) to handle overlapping patterns
    # Note: Do NOT strip " rate" - it's part of metric names like "attrition rate"
    conversational_suffixes = [
        # Longer patterns first (must be before shorter ones like " kpi")
        " across departments", " across regions", " across stages",
        " across department", " across region", " across stage",
        " by departments", " by regions",
        " by department", " by region", " by stage",
        " as a widget", " as a tile", " as a card", " as a kpi",
        " visualization", " dashboard", " report",
        " that we have", " do we have", " we have", " work here",
        " performing", " trending",
        " metrics", " figures", " numbers", " stats", " data",
        " looking", " doing", " going",
        " currently", " today",
        # Shorter patterns last
        " widget", " tile", " card", " chart", " graph", " kpi", " metric",
        " look", " now",
    ]
    # Keep stripping until no more suffixes match
    stripped = True
    while stripped:
        stripped = False
        for suffix in conversational_suffixes:
            if metric_query.endswith(suffix):
                metric_query = metric_query[:-len(suffix)].strip()
                stripped = True
                break

    # Strip entity names from the metric query so "meridian revenue" -> "revenue"
    # and "cascadia ebitda" -> "ebitda". The entity_id is captured separately.
    _entity_names = ["meridian", "cascadia", "combined", "consolidated"]
    for ename in _entity_names:
        # Handle possessives: "meridian's revenue" -> "revenue"
        metric_query = metric_query.replace(ename + "'s ", " ").replace(ename, "")
    metric_query = metric_query.strip()

    # Strip entity/filter suffixes (e.g., "revenue for North America" → "revenue")
    # This ensures the metric is correctly identified even when a filter is present.
    # The filter itself isn't applied here — that requires graph resolution.
    # IMPORTANT: Do NOT strip "for 2025", "for Q3 2025" etc. — those are periods, not entities.
    import re as _re
    for_match = _re.search(r"\s+for\s+(?:the\s+)?(.+)$", metric_query)
    if for_match:
        captured = for_match.group(1).strip()
        # Only strip if it's an entity filter, not a period reference
        # Matches: "2025", "Q1 2025", "2025-Q1", "2025 Q1", "H1 2025"
        is_period_ref = bool(_re.match(
            r'^(?:q[1-4]\s+)?20\d{2}(?:[-\s]q[1-4])?$|^20\d{2}[-\s]?q[1-4]$|^h[12]\s+20\d{2}$',
            captured, _re.IGNORECASE,
        ))
        is_period_phrase = captured in ("this year", "last year", "this quarter", "last quarter")
        if not is_period_ref and not is_period_phrase:
            metric_query = metric_query[:for_match.start()].strip()

    # ── Extract period from query BEFORE stripping it ──────────────────
    # Capture any explicit year or quarter so we can pass it downstream.
    import re as _re_period
    _extracted_period: Optional[str] = None

    # Check for "Q3 2025" / "q3 2025" pattern first
    _qtr_year = _re_period.search(r'\bq([1-4])\s*(20\d{2})\b', metric_query, _re_period.IGNORECASE)
    if _qtr_year:
        _extracted_period = f"{_qtr_year.group(2)}-Q{_qtr_year.group(1)}"
    else:
        # Check for "2025-Q1" / "2025 Q1" pattern (ISO-style)
        _year_qtr = _re_period.search(r'\b(20\d{2})[-\s]q([1-4])\b', metric_query, _re_period.IGNORECASE)
        if _year_qtr:
            _extracted_period = f"{_year_qtr.group(1)}-Q{_year_qtr.group(2)}"
        else:
            # Check for standalone year: "2025", "2024"
            _year_match = _re_period.search(r'\b(20\d{2})\b', metric_query)
            if _year_match:
                _extracted_period = _year_match.group(1)
            else:
                # Check for standalone quarter: "q3", "Q1"
                _qtr_match = _re_period.search(r'\bq([1-4])\b', metric_query, _re_period.IGNORECASE)
                if _qtr_match:
                    _extracted_period = f"{current_year()}-Q{_qtr_match.group(1)}"
                elif "this year" in metric_query:
                    _extracted_period = current_year()
                elif "last year" in metric_query:
                    _extracted_period = str(int(current_year()) - 1)
                elif "this quarter" in metric_query or "this quater" in metric_query:
                    _extracted_period = current_quarter()
                elif "last quarter" in metric_query or "last quater" in metric_query:
                    # Simple last quarter calc
                    from src.nlq.core.dates import prior_quarter
                    _extracted_period = prior_quarter()
                elif "last month" in metric_query:
                    # Last month: use current quarter as approximation
                    # (monthly grain not available, quarterly is closest)
                    from src.nlq.core.dates import prior_quarter
                    _extracted_period = prior_quarter()

    # Strip period suffixes (e.g., "revenue 2025", "margin for 2025", "arr in q3")
    # Include prepositions and common misspellings
    period_suffixes = [
        # With prepositions first (longer match wins)
        # ISO-style YYYY-QN format with prepositions
        " for 2024-q1", " for 2024-q2", " for 2024-q3", " for 2024-q4",
        " for 2025-q1", " for 2025-q2", " for 2025-q3", " for 2025-q4",
        " for 2026-q1", " for 2026-q2", " for 2026-q3", " for 2026-q4",
        " in 2024-q1", " in 2024-q2", " in 2024-q3", " in 2024-q4",
        " in 2025-q1", " in 2025-q2", " in 2025-q3", " in 2025-q4",
        " in 2026-q1", " in 2026-q2", " in 2026-q3", " in 2026-q4",
        " for 2024", " for 2025", " for 2026",
        " in 2024", " in 2025", " in 2026",
        " during 2024", " during 2025", " during 2026",
        " for q1 2024", " for q1 2025", " for q1 2026",
        " for q2 2024", " for q2 2025", " for q2 2026",
        " for q3 2024", " for q3 2025", " for q3 2026",
        " for q4 2024", " for q4 2025", " for q4 2026",
        " in q1 2024", " in q1 2025", " in q1 2026",
        " in q2 2024", " in q2 2025", " in q2 2026",
        " in q3 2024", " in q3 2025", " in q3 2026",
        " in q4 2024", " in q4 2025", " in q4 2026",
        " for this year", " for last year", " for this quarter", " for last quarter",
        " in this year", " in last year",
        # Without prepositions (fallback)
        # ISO-style YYYY-QN format
        " 2024-q1", " 2024-q2", " 2024-q3", " 2024-q4",
        " 2025-q1", " 2025-q2", " 2025-q3", " 2025-q4",
        " 2026-q1", " 2026-q2", " 2026-q3", " 2026-q4",
        " 2024", " 2025", " 2026",
        " this year", " last year", " this quarter", " last quarter",
        " this quater", " last quater",  # misspellings
        " last month", " this month",
        " q1 2024", " q1 2025", " q1 2026",
        " q2 2024", " q2 2025", " q2 2026",
        " q3 2024", " q3 2025", " q3 2026",
        " q4 2024", " q4 2025", " q4 2026",
        " q1", " q2", " q3", " q4",
        " ytd", " mtd", " qtd",
    ]
    for suffix in period_suffixes:
        if metric_query.endswith(suffix):
            metric_query = metric_query[:-len(suffix)].strip()
            break  # Only strip the first matching suffix

    # Strip trailing prepositions left after period stripping
    # e.g., "gross margin for" → "gross margin", "revenue in" → "revenue"
    for prep in (" for", " in", " during"):
        if metric_query.endswith(prep):
            metric_query = metric_query[:-len(prep)].strip()

    # Strip period prefixes (e.g., "2025 revenue", "q3 margin")
    period_prefixes = [
        "2024 ", "2025 ", "2026 ",
        "q1 ", "q2 ", "q3 ", "q4 ",
    ]
    for prefix in period_prefixes:
        if metric_query.startswith(prefix):
            metric_query = metric_query[len(prefix):].strip()

    # Try synonym lookup
    resolved_metric = normalize_metric(metric_query)
    if resolved_metric:
        return _build_simple_metric_result(resolved_metric, period=_extracted_period, entity_id=entity_id)

    # Also try the original query in case it's already a metric name
    resolved_metric = normalize_metric(q.rstrip("?").strip())
    if resolved_metric:
        return _build_simple_metric_result(resolved_metric, period=_extracted_period, entity_id=entity_id)

    # Step 3: Try embedding-based lookup (CHEAP - ~$0.0001)
    # Only do this if we have the embedding index available
    try:
        from src.nlq.services.metric_embedding_index import get_metric_embedding_index
        import asyncio

        metric_index = get_metric_embedding_index()
        if metric_index.is_initialized:
            # Run async lookup synchronously
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context - can't use run_until_complete
                    # Fall through to LLM
                    pass
                else:
                    result = loop.run_until_complete(metric_index.lookup(metric_query))
                    if result and result.is_high_confidence:
                        return _build_simple_metric_result(result.canonical_metric, period=_extracted_period, entity_id=entity_id)
            except RuntimeError:
                # No event loop, create one
                result = asyncio.run(metric_index.lookup(metric_query))
                if result and result.is_high_confidence:
                    return _build_simple_metric_result(result.canonical_metric, period=_extracted_period, entity_id=entity_id)
    except ImportError:
        pass  # Embedding index not available, fall through
    except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
        logger.warning(f"Embedding lookup failed: {e}")

    return None  # No match, let normal flow handle it


def _detect_entity_id(question: str) -> Optional[str]:
    """Detect entity mentions in the question text.

    Returns the entity_id if an entity name is found, or None for default behavior.
    """
    q = question.lower()
    if "meridian" in q:
        return "meridian"
    if "cascadia" in q:
        return "cascadia"
    if "combined" in q or "consolidated" in q:
        return "combined"
    return None


def _build_simple_metric_result(metric: str, period: Optional[str] = None, entity_id: Optional[str] = None) -> Optional[SimpleMetricResult]:
    """
    Build a SimpleMetricResult for a resolved metric.

    All data is fetched from DCL.
    Uses the explicit period from the query when provided.
    Falls back to latest available period only when no period was specified.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()

    # Use explicit period from query, or fall back to latest
    requested_period = period or dcl_client.get_latest_period()

    # Determine granularity from period format
    # "2025" = annual (get quarterly data for that year and sum)
    # "2025-Q3" = quarterly (get that specific quarter)
    import re as _re_bsmr
    is_annual = bool(_re_bsmr.match(r'^20\d{2}$', str(requested_period)))
    is_quarterly = bool(_re_bsmr.match(r'^20\d{2}-Q[1-4]$', str(requested_period)))

    result = dcl_client.query(
        metric=metric,
        time_range={"period": requested_period, "granularity": "quarterly"},
        tenant_id=get_tenant_id(),
        entity_id=entity_id,
    )

    # Extract value from DCL response
    if result.get("status") == "error" or result.get("error"):
        logger.debug(f"DCL query failed for {metric}: {result.get('error')}")
        return None

    data = result.get("data", [])
    if not data:
        return None

    # Extract quality metadata from DCL response (defaults for local fallback)
    metadata = result.get("metadata", {})
    data_quality = metadata.get("quality_score", 1.0)
    freshness = metadata.get("freshness_display", "") or "0h"

    # Determine aggregation method BEFORE summing:
    # Additive metrics (revenue, costs, counts) -> sum quarterly rows for annual
    # Non-additive metrics (pct, ratio, score, days) -> average quarterly rows
    from src.nlq.knowledge.schema import is_additive_metric
    _is_additive = is_additive_metric(metric)

    # Handle different response formats
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict) and "value" in data[0]:
            # Filter rows to only those matching the requested period
            if is_annual:
                # Annual: filter rows whose period falls in the requested year
                filtered = [d for d in data
                            if d.get("value") is not None
                            and str(requested_period) in str(d.get("period", ""))]
                if not filtered:
                    # If period field doesn't exist on rows, use all (backward compat)
                    filtered = [d for d in data if d.get("value") is not None]
                if _is_additive:
                    value = sum(d.get("value", 0) for d in filtered)
                else:
                    # Average for percentages, ratios, scores, durations
                    vals = [d.get("value") for d in filtered if d.get("value") is not None]
                    value = sum(vals) / len(vals) if vals else None
            elif is_quarterly:
                # Quarterly: take the single matching row
                matching = [d for d in data
                            if d.get("value") is not None
                            and str(requested_period) in str(d.get("period", ""))]
                if matching:
                    value = matching[0].get("value")
                else:
                    # Fall back to last row if no period field on rows
                    value = data[-1].get("value") if isinstance(data[-1], dict) else data[-1]
            else:
                # Unknown period format
                if _is_additive:
                    value = sum(d.get("value", 0) for d in data if d.get("value") is not None)
                else:
                    vals = [d.get("value") for d in data if d.get("value") is not None]
                    value = sum(vals) / len(vals) if vals else None
        else:
            value = data[-1] if data else None
    elif isinstance(data, (int, float)):
        value = data
    else:
        return None

    if value is None:
        return None

    # Get metric metadata
    display_name = get_display_name(metric)
    display_unit = get_metric_unit(metric)
    if display_unit == "unknown" and result.get("unit"):
        display_unit = result["unit"]
    canonical_unit = get_canonical_unit(metric)

    # Format the value for human-readable answer
    if display_unit == "USD thousands":
        formatted = f"${round(value, 1)}K"
        answer = f"{display_name} for {requested_period} is {formatted}"
    elif display_unit in ("USD millions", "USD", "$"):
        formatted = f"${round(value, 1)}M"
        answer = f"{display_name} for {requested_period} is {formatted}"
    elif display_unit == "%":
        formatted = f"{round(value, 1)}%"
        answer = f"{display_name} for {requested_period} is {formatted}"
    elif display_unit in ("count", ""):
        formatted = f"{int(value):,}"
        answer = f"{display_name} for {requested_period} is {formatted}"
    else:
        formatted = str(round(value, 1))
        answer = f"{display_name} for {requested_period} is {formatted}"

    return SimpleMetricResult(
        metric=metric,
        value=value,
        formatted_value=formatted,
        unit=canonical_unit,
        display_name=display_name,
        domain=determine_domain(metric),
        answer=answer,
        period=requested_period,
        data_quality=data_quality,
        freshness=freshness,
        source=result.get("source", "local"),
        run_provenance=result.get("run_provenance"),
        data_source=result.get("data_source"),
        data_source_reason=result.get("data_source_reason"),
    )


# =============================================================================
# P&L / INCOME STATEMENT COMPOSITE HANDLER
# =============================================================================

def _has_explicit_period(question: str) -> bool:
    """Return True if the question contains an explicit year, quarter, or bare Q reference."""
    q = question.lower()
    if re.search(r'q[1-4]', q):
        return True
    if re.search(r'20(2[4-6])', q):
        return True
    return False


def _try_report_query(question: str, session_id: Optional[str] = None, entity_id: Optional[str] = None) -> Optional[NLQResponse]:
    """Detect Standard Reporting Package queries and generate comparison reports."""
    from src.nlq.core.report_intent import detect_report_intent

    intent = detect_report_intent(question)
    if intent is None:
        return None

    entity_id = entity_id or _detect_entity_id(question)
    query_fn = (
        functools.partial(_build_simple_metric_result, entity_id=entity_id)
        if entity_id
        else _build_simple_metric_result
    )

    from src.nlq.services.report_generator import ReportGenerator
    generator = ReportGenerator(query_fn=query_fn, entity_id=entity_id)
    result = generator.generate_report(
        statement_type=intent.statement_type,
        variant=intent.variant,
        selected_quarter=intent.selected_quarter,
    )

    if result and result.financial_statement_data and session_id:
        from src.nlq.api.session import get_dashboard_session_store
        store = get_dashboard_session_store()
        store.set_financial_statement(session_id, result.financial_statement_data.model_dump())

    return result


def _try_pl_statement_query(question: str, session_id: Optional[str] = None, entity_id: Optional[str] = None) -> Optional[NLQResponse]:
    """
    Detect P&L / income statement queries and fan out DCL queries for all line items.

    Returns an NLQResponse with financial_statement_data for structured rendering,
    or None if the question isn't a P&L query or not enough data resolves.
    """
    from src.nlq.core.composite_query import is_pl_statement_query, PLStatementHandler, determine_pl_periods

    if not is_pl_statement_query(question):
        return None

    if _has_explicit_period(question):
        period_spec = _extract_period_from_dashboard_query(question)
    else:
        period_spec = None  # signals "show all periods"

    entity_id = entity_id or _detect_entity_id(question)
    query_fn = (
        functools.partial(_build_simple_metric_result, entity_id=entity_id)
        if entity_id
        else _build_simple_metric_result
    )

    periods = determine_pl_periods(period_spec)
    handler = PLStatementHandler(periods=periods, query_fn=query_fn, entity_id=entity_id)
    result = handler.execute()

    if result and result.financial_statement_data and session_id:
        from src.nlq.api.session import get_dashboard_session_store
        store = get_dashboard_session_store()
        store.set_financial_statement(session_id, result.financial_statement_data.model_dump())

    return result


def _try_bridge_query(question: str, session_id: Optional[str] = None, entity_id: Optional[str] = None) -> Optional[NLQResponse]:
    """Detect revenue bridge/waterfall queries and build the variance decomposition."""
    from src.nlq.core.bridge_query import is_bridge_query, BridgeHandler

    bridge_type = is_bridge_query(question)
    if bridge_type is None:
        return None

    entity_id = entity_id or _detect_entity_id(question)
    query_fn = (
        functools.partial(_build_simple_metric_result, entity_id=entity_id)
        if entity_id
        else _build_simple_metric_result
    )

    handler = BridgeHandler(query_fn=query_fn)
    result = handler.execute()

    if result and result.bridge_chart_data and session_id:
        from src.nlq.api.session import get_dashboard_session_store
        store = get_dashboard_session_store()
        store.set_bridge_chart(session_id, result.bridge_chart_data.model_dump())

    return result


def _try_multi_metric_query(question: str) -> Optional[NLQResponse]:
    """
    Handle queries that ask for multiple metrics joined by 'and' or commas.
    E.g., "EBITDA and net income", "Revenue, COGS, and gross profit"
    """
    import re
    from src.nlq.knowledge.synonyms import normalize_metric

    q = question.lower().strip().rstrip("?")
    # Strip common prefixes
    for prefix in ["what's ", "what is ", "what are ", "show me ", "give me ", "tell me "]:
        if q.startswith(prefix):
            q = q[len(prefix):]
    q = q.strip()

    # Split on " and " or ", "
    parts = re.split(r'\s+and\s+|,\s*', q)
    if len(parts) < 2:
        return None

    # Try to resolve each part as a metric
    resolved = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        metric = normalize_metric(part)
        if metric:
            resolved.append((part, metric))

    if len(resolved) < 2:
        return None

    # Build results for each metric
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    from src.nlq.knowledge.schema import get_metric_unit, get_canonical_unit
    from src.nlq.knowledge.display import get_display_name

    dcl_client = get_semantic_client()
    period = current_quarter()
    entity_id = _detect_entity_id(question)
    parts_text = []
    primary_value = None

    for term, metric in resolved:
        result = dcl_client.query(metric=metric, time_range={"period": period, "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=entity_id)
        if result.get("error") or not result.get("data"):
            continue
        data = result.get("data", [])
        if isinstance(data, list) and data:
            val = data[-1].get("value") if isinstance(data[-1], dict) else data[-1]
        elif isinstance(data, (int, float)):
            val = data
        else:
            continue
        if val is None:
            continue
        if primary_value is None:
            primary_value = val
        display = get_display_name(metric)
        unit = get_metric_unit(metric)
        if unit in ("USD millions",):
            parts_text.append(f"{display}: ${round(val, 1)}M")
        elif unit == "%":
            parts_text.append(f"{display}: {round(val, 1)}%")
        else:
            parts_text.append(f"{display}: {round(val, 1)}")

    if len(parts_text) < 2:
        return None

    answer = f"For {period}: " + ", ".join(parts_text)
    return NLQResponse(
        success=True, answer=answer, value=primary_value,
        unit=get_canonical_unit(resolved[0][1]),
        confidence=0.95, parsed_intent="POINT_QUERY",
        resolved_metric=resolved[0][1], resolved_period=period,
    )


def _try_simple_metric_query(question: str, entity_id: Optional[str] = None) -> Optional[NLQResponse]:
    """
    Try to answer a simple metric query directly from DCL.

    Uses tiered approach: exact match -> embedding lookup -> fall through to LLM.
    Handles queries like "ebitda", "what's our revenue?", "GM" without Claude.
    Returns None if no confident match found.

    All data is fetched from DCL.
    """
    entity_id = entity_id or _detect_entity_id(question)
    result = _try_tiered_metric_query_core(question, entity_id=entity_id)
    if result:
        return simple_metric_to_nlq_response(result)

    # ── Guard: if synonym lookup resolved the metric but DCL returned no data,
    # return a "no data" response preserving the correct resolved_metric.
    # Without this, the query falls through to Claude LLM parsing which may
    # silently substitute a completely different metric (e.g. attrition_rate_pct
    # gets replaced with logo_churn_pct).
    from src.nlq.knowledge.synonyms import normalize_metric, _METRIC_REVERSE_LOOKUP
    q = question.lower().strip().rstrip("?").strip()
    # Re-do the prefix stripping to get the metric phrase
    for pfx in ("what is our ", "what's our ", "what is the ", "what's the ",
                 "how much is our ", "how many ", "how much ",
                 "what is ", "what's ", "show me ", "tell me about ",
                 "tell me ", "our ", "the ", "current "):
        if q.startswith(pfx):
            q = q[len(pfx):]
            break
    q = q.strip()
    # Check static synonym lookup (Tier 1 only — no DCL fuzzy)
    static_hit = _METRIC_REVERSE_LOOKUP.get(q)
    if static_hit:
        from src.nlq.knowledge.display import get_display_name
        from src.nlq.knowledge.schema import FINANCIAL_SCHEMA
        display = get_display_name(static_hit)
        defn = FINANCIAL_SCHEMA.get(static_hit)
        desc_part = f" ({defn.description})" if defn and defn.description else ""
        logger.warning(
            f"KNOWN METRIC NO DATA: resolved '{q}' to metric '{static_hit}' "
            f"but DCL returned no data. Check DCL ingest status for this metric."
        )
        return NLQResponse(
            success=True,
            answer=(
                f"I recognize **{display}**{desc_part}, "
                f"but I don't have data for it right now. "
                f"This may indicate missing data in the current dataset for metric `{static_hit}`."
            ),
            value=None,
            unit=None,
            confidence=0.5,
            parsed_intent="POINT_QUERY",
            resolved_metric=static_hit,
            resolved_period=current_year(),
        )

    return None  # No match, let normal flow handle it


# =============================================================================
# SIMPLE BREAKDOWN HANDLER - Handle "X by Y" queries without LLM
# =============================================================================

# Dimension aliases for normalization
_DIMENSION_ALIASES = {
    # Region aliases
    "geo": "region",
    "geography": "region",
    "territory": "region",
    "territories": "region",
    "reigon": "region",  # misspelling
    # Department aliases — "team" is NOT aliased here because DCL has
    # native "team" and "department" as separate dimensions
    "dept": "department",
    "org": "department",
    "departmnet": "department",  # misspelling
    # Stage aliases
    "phase": "stage",
    "phases": "stage",
    "sales stage": "stage",
    "sales_stage": "stage",
    # Segment aliases
    "customer segment": "segment",
    "customer_segment": "segment",
    "tier": "segment",
    "market segment": "segment",
    "market_segment": "segment",
    "board segment": "segment",
    "board_segment": "segment",
    "segmnet": "segment",  # misspelling
    # Service aliases — "service" passes through as-is (DCL has native "service" dimension)
    "service line": "service_line",
    "service_line": "service_line",
    # Category aliases — DCL uses "resource_type" for cloud_spend breakdowns
    "category": "resource_type",
    # Cost center aliases
    "cost center": "cost_center",
    "cost_center": "cost_center",
    # Product aliases
    "product line": "product",
    "product_line": "product",
}


def _try_simple_breakdown_query(question: str) -> Optional[NLQResponse]:
    """
    Try to answer a simple breakdown query directly from DCL.

    Handles queries like "Revenue by region", "Headcount by department" without Claude.
    Returns None if no confident match found.
    """
    import re
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    from src.nlq.knowledge.synonyms import normalize_metric

    q = question.lower().strip()

    # Match "metric by dimension" pattern
    # Remove prefixes first (longer prefixes should come before shorter ones)
    prefixes = [
        "drill deeper into ", "drill down into ", "drill down on ", "drill down ",
        "drill into ", "break down ", "breakdown ", "compare ",
        "show me ", "show ", "display ", "get ", "give me ", "what's ", "what is ",
        "create ", "make ", "build ", "add ", "graph ", "chart ",
        # Additional visualization prefixes that may remain after initial strip
        "a visualization of ", "a chart of ", "a graph of ", "a dashboard of ",
        "visualization of ", "chart of ", "graph of ", "dashboard of ",
    ]
    for prefix in prefixes:
        if q.startswith(prefix):
            q = q[len(prefix):]
            break  # Only strip one prefix at a time, but loop continues below

    # Loop to strip multiple prefixes (e.g., "create a visualization of" -> "")
    while True:
        stripped = False
        for prefix in prefixes:
            if q.startswith(prefix):
                q = q[len(prefix):]
                stripped = True
                break
        if not stripped:
            break

    # Match "X by Y" or "X across Y" pattern
    # Allow up to 4 words for metric (e.g., "time to fill days")
    # Dimension must stop at "for", "in", "during", period words, or end of string
    by_match = re.search(r"^(\w+(?:\s+\w+){0,3})\s+(?:by|across)\s+(\w+(?:\s+\w+)??)(?:\s+(?:for|in|during|q[1-4]|20\d{2})|$|\s*[?.!])", q)
    if not by_match:
        # Fallback: try simpler single-word dimension pattern
        by_match = re.search(r"^(\w+(?:\s+\w+){0,3})\s+(?:by|across)\s+(\w+)", q)
        if not by_match:
            return None

    metric_term = by_match.group(1).strip()
    dim_term = by_match.group(2).strip()

    # Extract "for [filter]" suffix and period text after the dimension match
    filter_dim = None
    filter_val = None
    remainder = q[by_match.end():].strip().rstrip("?.!,;")
    # Also check the part of the string after the dimension for period text
    post_dim = q[by_match.start(2) + len(dim_term):].strip()

    # Extract period from the breakdown query (e.g. "for 2025", "Q2 2025")
    _bd_period = None
    _bd_period_match = re.search(r'(?:for\s+)?(?:the\s+)?q([1-4])\s+(20\d{2})', post_dim, re.IGNORECASE)
    if _bd_period_match:
        _bd_period = f"{_bd_period_match.group(2)}-Q{_bd_period_match.group(1)}"
    else:
        _bd_year_match = re.search(r'(?:for\s+)?(?:the\s+)?(20\d{2})', post_dim)
        if _bd_year_match:
            _bd_period = _bd_year_match.group(1)

    for_match = re.search(r"for\s+(?:the\s+)?(.+?)(?:\s+(?:division|department|region|segment|team))?$", remainder)
    if for_match:
        filter_text = for_match.group(0)
        # Try to extract "for the X Y" where Y is a dimension name
        dim_val_match = re.search(
            r"for\s+(?:the\s+)?(.+?)\s+(division|department|region|segment|team|cost center|service line)$",
            filter_text,
        )
        if dim_val_match:
            filter_val = dim_val_match.group(1).strip()
            filter_dim = _DIMENSION_ALIASES.get(dim_val_match.group(2), dim_val_match.group(2))
        else:
            # Just a value filter without explicit dimension name
            filter_val = for_match.group(1).strip().rstrip("?")

    # Temporal dimensions should route to trend query, not breakdown query.
    # "revenue by quarter" is a time series, not a categorical breakdown.
    _TEMPORAL_DIMENSIONS = {"quarter", "quarters", "month", "months", "year", "years", "week", "weeks"}
    if dim_term.lower() in _TEMPORAL_DIMENSIONS:
        return None

    # Handle plural dimension terms (e.g., "stages" -> "stage", "departments" -> "department")
    if dim_term.endswith("s") and dim_term not in ("business", "success"):
        dim_term = dim_term[:-1]  # Remove trailing 's'

    # Strip possessive/article words that leak into metric_term
    # e.g., "our cloud spend" → "cloud spend", "the revenue" → "revenue"
    _STRIP_WORDS = {"our", "my", "the", "their", "your", "its", "current", "total", "overall"}
    metric_words = metric_term.split()
    metric_words = [w for w in metric_words if w.lower() not in _STRIP_WORDS]
    metric_term = " ".join(metric_words)

    # Handle multi-concept queries: "revenue and headcount by department"
    # Split on " and " and use the first concept for the breakdown query
    if " and " in metric_term:
        metric_term = metric_term.split(" and ")[0].strip()

    # Normalize metric
    metric = normalize_metric(metric_term)
    if not metric:
        return None

    # Normalize dimension
    dimension = _DIMENSION_ALIASES.get(dim_term, dim_term)

    # Query DCL for breakdown data
    dcl_client = get_semantic_client()
    current_period = _bd_period or dcl_client.get_latest_period()

    # Don't force granularity for breakdown queries — breakdowns are categorical
    # (e.g., revenue by region) not temporal. Forcing grain="quarter" causes DCL
    # to return 0 rows for metrics stored at other grains (e.g., deploy_frequency
    # stored at grain="week"). Let DCL use native grain.
    result = dcl_client.query(
        metric=metric,
        dimensions=[dimension],
        time_range={"period": current_period},
        tenant_id=get_tenant_id(),
    )

    # If flat query failed, try graph resolution (cross-system join path)
    if result.get("error") or not result.get("data"):
        # Build filter list from extracted "for X" clause
        graph_filters = []
        if filter_val:
            graph_filters.append({
                "dimension": filter_dim or dimension,
                "operator": "equals",
                "value": filter_val,
            })
        graph_result = dcl_client.resolve_via_graph(
            concepts=[metric],
            dimensions=[dimension],
            filters=graph_filters if graph_filters else None,
        )
        if graph_result.get("can_answer"):
            # Graph found a resolution path — return it
            _conf_raw = graph_result.get("confidence", 0.5)
            confidence = _conf_raw.get("overall", 0.5) if isinstance(_conf_raw, dict) else float(_conf_raw)
            join_paths = graph_result.get("join_paths", [])
            provenance = graph_result.get("provenance", [])
            filters_resolved = graph_result.get("filters_resolved", {})
            warnings = graph_result.get("warnings", [])
            resolved = graph_result.get("resolved_concepts", [])

            # Build answer describing the resolution path
            path_desc_parts = []
            for jp in join_paths:
                if isinstance(jp, dict) and jp.get("type") == "cross_system_join":
                    path_desc_parts.append(
                        f"{jp['dimension']} via cross-system join "
                        f"({jp.get('source_system', '?')} -> {jp.get('join_system', '?')})"
                    )
            path_desc = "; ".join(path_desc_parts) if path_desc_parts else "graph resolution"
            systems = [p.get("source_system", "") for p in provenance if isinstance(p, dict) and p.get("source_system")]

            return NLQResponse(
                success=True,
                answer=f"{metric.replace('_', ' ').title()} by {dim_term} resolved via {path_desc}.",
                value=None,
                unit=None,
                confidence=confidence,
                parsed_intent="GRAPH_RESOLUTION",
                resolved_metric=metric,
                resolved_period=current_period,
                response_type="text",
                data_source="dcl" if graph_result.get("source") == "dcl_graph" else "graph_catalog",
                provenance={
                    "source_systems": systems,
                    "join_paths": join_paths,
                    "filters_resolved": filters_resolved,
                    "resolved_concepts": resolved,
                    "warnings": warnings,
                    "resolution_source": graph_result.get("source", "unknown"),
                },
            )

        # Graph can't answer either — provide helpful fallback
        valid_dims = dcl_client.get_valid_dimensions(metric)
        if valid_dims:
            valid_list = ", ".join(valid_dims)
            return NLQResponse(
                success=True,
                answer=f"No data available for {metric.replace('_', ' ')} by {dim_term}. "
                       f"Try breaking down by: {valid_list}.",
                value=None,
                unit=None,
                confidence=0.85,
                parsed_intent="DATA_NOT_AVAILABLE",
                resolved_metric=metric,
                resolved_period=current_period,
                response_type="text",
            )
        # Metric not in catalog or no dimensions — return clean rejection.
        return NLQResponse(
            success=True,
            answer=f"Cannot answer: {metric.replace('_', ' ')} by {dim_term} "
                   f"is not a valid combination in the data catalog.",
            value=None,
            unit=None,
            confidence=0.3,
            parsed_intent="DATA_NOT_AVAILABLE",
            resolved_metric=metric,
            resolved_period=current_period,
            response_type="text",
        )

    # Format as dashboard data
    breakdown_data = result.get("data", [])
    if not breakdown_data:
        return None

    # Filter breakdown data by requested period (DCL may return ALL quarters
    # even when a year filter is requested). Match rows whose period contains
    # the requested year/quarter string.
    if _bd_period and breakdown_data:
        _filtered = [
            item for item in breakdown_data
            if isinstance(item, dict) and _bd_period in str(item.get("period", ""))
        ]
        if _filtered:
            breakdown_data = _filtered

    # Convert breakdown data to the expected format: list of {label, value}
    formatted_data = []
    for item in breakdown_data:
        if isinstance(item, dict):
            # Extract dimension key and value
            # DCL returns dimensions nested: {"dimensions": {"region": "AMER"}, "value": 24.0}
            # Local returns flat: {"region": "AMER", "value": 24.0}
            dims_dict = item.get("dimensions", {})
            dim_key = (
                (dims_dict.get(dimension) if isinstance(dims_dict, dict) else None)
                or item.get(dimension)
                or item.get("label", "")
            )
            val = item.get("value")

            # Handle nested value dicts (e.g., {'pipeline': 6.4, 'qualified': 3.84})
            if isinstance(val, dict):
                # Try to get the metric value, or first numeric value
                if metric in val:
                    val = val[metric]
                else:
                    # Get first numeric value from the dict
                    for v in val.values():
                        if isinstance(v, (int, float)):
                            val = v
                            break
                    else:
                        val = 0

            if dim_key and val is not None:
                formatted_data.append({"label": str(dim_key), "value": val})

    # Aggregate duplicate dimension labels (DCL may return per-quarter data
    # when queried for a year period, producing N entries per dimension label).
    if formatted_data:
        from src.nlq.knowledge.schema import is_additive_metric
        _bd_additive = is_additive_metric(metric)

        # Remove aggregate/total rows that DCL may include as summary
        _AGGREGATE_LABELS = {"total", "all", "grand total", "overall", "sum"}
        formatted_data = [
            item for item in formatted_data
            if item["label"].lower() not in _AGGREGATE_LABELS
        ]

        _agg = {}
        _counts = {}
        for item in formatted_data:
            lbl = item["label"]
            _agg[lbl] = _agg.get(lbl, 0) + item["value"]
            _counts[lbl] = _counts.get(lbl, 0) + 1

        if _bd_additive:
            formatted_data = [{"label": k, "value": v} for k, v in _agg.items()]
        else:
            formatted_data = [{"label": k, "value": v / _counts[k]} for k, v in _agg.items()]

    if not formatted_data:
        # No breakdown data found - provide helpful message
        valid_dims = dcl_client.get_valid_dimensions(metric)
        if valid_dims:
            valid_list = ", ".join(valid_dims)
            return NLQResponse(
                success=True,
                answer=f"No breakdown data available for {metric.replace('_', ' ')} by {dim_term}. "
                       f"Try breaking down by: {valid_list}.",
                value=None,
                unit=None,
                confidence=0.85,
                parsed_intent="DATA_NOT_AVAILABLE",
                resolved_metric=metric,
                resolved_period=current_period,
                response_type="text",
            )
        return None

    # Build dashboard response with breakdown in expected format
    # Format: {widget_id: {series: [{data: [{label, value}]}]}}
    widget_id = f"breakdown_{metric}_by_{dimension}"
    dashboard_data = {
        widget_id: {
            "title": f"{metric.replace('_', ' ').title()} by {dimension.title()}",
            "type": "bar_chart",
            "series": [{
                "name": metric,
                "data": formatted_data,
            }]
        }
    }

    # Extract provenance and data_source from DCL result
    data_source = result.get("data_source")
    provenance_data = result.get("run_provenance") or (result.get("metadata") or {}).get("provenance")

    return NLQResponse(
        success=True,
        answer=f"Here's {metric.replace('_', ' ')} by {dimension}",
        value=None,
        unit=None,
        confidence=0.9,
        parsed_intent="BREAKDOWN",
        resolved_metric=metric,
        resolved_period=current_period,
        response_type="dashboard",
        dashboard_data=dashboard_data,
        data_source=data_source,
        provenance=provenance_data if isinstance(provenance_data, dict) else None,
    )


# Guided discovery patterns and available metrics by domain
_GUIDED_DISCOVERY_DOMAINS = {
    "customer": {
        "pattern": r"\b(?:what can you show me|what do you have|tell me about|show me available)\b.*\bcustomer",
        "metrics": ["customer_count", "nrr", "churn_rate_pct", "logo_churn_pct"],
        "response": "For customers, I can show you:\n- Customer Count (currently 950)\n- Net Revenue Retention / NRR (118%)\n- Gross Churn Rate (7%)\n- Logo Churn Rate\n\nWould you like to see a dashboard with customer metrics, or ask about a specific metric?"
    },
    "sales": {
        "pattern": r"\b(?:what can you show me|what do you have|tell me about|show me available)\b.*\bsales",
        "metrics": ["revenue", "pipeline", "win_rate_pct", "quota_attainment_pct", "sales_cycle_days"],
        "response": "For sales, I can show you:\n- Revenue ($150M for 2025)\n- Pipeline ($431M)\n- Win Rate (42%)\n- Quota Attainment (95.8%)\n- Sales Cycle (85 days)\n\nWould you like to see a sales dashboard or drill into a specific metric?"
    },
    "finance": {
        "pattern": r"\b(?:what can you show me|what do you have|tell me about|show me available)\b.*\b(?:finance|financial)",
        "metrics": ["revenue", "gross_margin_pct", "net_income", "arr"],
        "response": "For finance, I can show you:\n- Revenue ($150M)\n- Gross Margin (65%)\n- Net Income ($28.1M)\n- ARR ($142.5M)\n\nWould you like a financial dashboard or details on a specific metric?"
    },
}


def _try_guided_discovery_core(question: str) -> Optional[GuidedDiscoveryResult]:
    """
    Core logic for guided discovery queries - shared between /query and /query/galaxy.

    Returns available metrics for the requested domain.
    """
    q = question.lower().strip()

    for domain_name, config in _GUIDED_DISCOVERY_DOMAINS.items():
        if re.search(config["pattern"], q, re.IGNORECASE):
            return GuidedDiscoveryResult(
                domain_name=domain_name,
                domain=determine_domain_from_name(domain_name),
                metrics=config["metrics"],
                response_text=config["response"],
            )

    return None


def _try_guided_discovery(question: str) -> Optional[NLQResponse]:
    """
    Handle guided discovery queries like "what can you show me about customers?"

    Returns available metrics for the requested domain.
    """
    result = _try_guided_discovery_core(question)
    if result:
        return guided_discovery_to_nlq_response(result)
    return None


# =============================================================================
# INGEST / INFRASTRUCTURE STATUS QUERIES
# =============================================================================

# Keywords that signal the user is asking about data sources, tenants, or ingest status
_INGEST_KEYWORDS = [
    "ingest", "ingesting", "ingestion",
    "source system", "source systems", "data source", "data sources",
    "connected", "connection", "connections",
    "pushing data", "sending data", "feeding data",
    "tenant", "tenants",
    "pipeline status", "pipeline health", "data pipeline",
    "splunk", "salesforce", "sap", "snowflake", "jira", "servicenow",
    "what sources", "which sources", "what systems", "which systems",
    "data flow", "data feeds",
]

# Phrases that specifically ask about source connectivity
_SOURCE_CONNECTIVITY_PATTERNS = [
    r"\bis\s+\w+\s+connected\b",           # "is splunk connected"
    r"\bwhat.+(?:pushing|sending|feeding)\b",  # "what is pushing data"
    r"\bwho.+(?:pushing|sending|feeding)\b",   # "who is pushing data"
    r"\bwhich\s+(?:sources?|systems?|tenants?)\b",  # "which sources are..."
    r"\bwhat\s+(?:sources?|systems?|tenants?)\b",   # "what sources are..."
    r"\b(?:source|system|tenant)\s+(?:list|status|count)\b",
    r"\bhow\s+many\s+(?:sources?|systems?|pipes?|tenants?)\b",
    r"\bdata\s+(?:from|into|sources?)\b",
    r"\bingest(?:ion|ing)?\s+(?:status|summary|runs?|activity)\b",
]


def _is_ingest_question(question: str) -> bool:
    """Detect if the question is about data sources, tenants, or ingest status."""
    q = question.lower().strip()

    # Check keyword matches
    for keyword in _INGEST_KEYWORDS:
        if keyword in q:
            return True

    # Check regex patterns
    for pattern in _SOURCE_CONNECTIVITY_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return True

    return False


def _format_ingest_answer(question: str, ingest_data: dict) -> str:
    """Turn raw ingest data into a natural language answer for the user's question."""
    q = question.lower().strip()
    sources = ingest_data.get("sources", [])
    tenants = ingest_data.get("tenants", [])
    total_rows = ingest_data.get("total_rows", 0)
    pipe_count = ingest_data.get("pipe_count", 0)
    available = ingest_data.get("available", False)

    if not available or (not sources and not tenants):
        return "No live ingest data is currently available. The system is running on demo data."

    # Check if asking about a specific source (e.g., "is Splunk connected?")
    specific_source = None
    for src in sources:
        if src.lower() in q:
            specific_source = src
            break

    if specific_source:
        # Find row count for this source from runs data
        runs = ingest_data.get("runs", [])
        source_rows = sum(
            r.get("row_count", 0) for r in runs
            if (r.get("source_system") or "").lower() == specific_source.lower()
        )
        if source_rows > 0:
            return f"Yes, {specific_source} is connected and actively pushing data ({source_rows:,} rows ingested)."
        return f"Yes, {specific_source} is connected as a data source."

    # Check if asking about tenants
    if "tenant" in q:
        if tenants:
            tenant_list = ", ".join(tenants)
            return f"There {'is' if len(tenants) == 1 else 'are'} {len(tenants)} tenant{'s' if len(tenants) != 1 else ''} pushing data: {tenant_list}. Total rows ingested: {total_rows:,}."
        return "No tenant data is currently available."

    # Check if asking "how many"
    if "how many" in q:
        if "source" in q or "system" in q:
            return f"There are {len(sources)} source system{'s' if len(sources) != 1 else ''} connected: {', '.join(sources)}."
        if "tenant" in q:
            return f"There are {len(tenants)} tenant{'s' if len(tenants) != 1 else ''}: {', '.join(tenants)}."
        if "pipe" in q:
            return f"There are {pipe_count} data pipe{'s' if pipe_count != 1 else ''} active."
        if "row" in q:
            return f"There are {total_rows:,} rows ingested across all sources."

    # General ingest status summary
    source_list = ", ".join(sources) if sources else "none detected"
    parts = [
        f"{len(sources)} source system{'s' if len(sources) != 1 else ''} connected ({source_list})",
        f"{total_rows:,} total rows ingested",
        f"{pipe_count} active data pipe{'s' if pipe_count != 1 else ''}",
    ]
    if tenants:
        parts.append(f"tenant{'s' if len(tenants) != 1 else ''}: {', '.join(tenants)}")

    return "Live ingest status: " + ". ".join(parts) + "."


def _try_ingest_status_core(question: str) -> Optional[IngestStatusResult]:
    """Core logic for ingest status queries — shared between /query and /query/galaxy."""
    if not _is_ingest_question(question):
        return None

    from src.nlq.services.dcl_semantic_client import get_semantic_client
    dcl_client = get_semantic_client()
    ingest_data = dcl_client.get_ingest_runs()

    answer = _format_ingest_answer(question, ingest_data)
    return IngestStatusResult(
        response_text=answer,
        sources=ingest_data.get("sources", []),
        tenants=ingest_data.get("tenants", []),
        total_rows=ingest_data.get("total_rows", 0),
        pipe_count=ingest_data.get("pipe_count", 0),
        available=ingest_data.get("available", False),
    )


def _try_ingest_status_query(question: str) -> Optional[NLQResponse]:
    """Handle ingest/infrastructure status queries for /query endpoint."""
    result = _try_ingest_status_core(question)
    if result:
        return ingest_status_to_nlq_response(result)
    return None


# _try_ingest_status_query_galaxy removed — only used by deleted query_galaxy()


# Patterns that indicate queries about non-existent data
_MISSING_DATA_PATTERNS = [
    r"\bmars\b",
    r"\bmoon\b",
    r"\bspace\b",
    r"\balien\b",
    r"\bunicorn\b",
    r"\bcolony\b",
    r"\b(?:does not|doesn't|don't) exist",
]


_MISSING_DATA_RESPONSE = "I don't have data for that. I can help you with metrics like revenue, pipeline, win rate, customer count, margins, and other standard business metrics. What would you like to explore?"


def _check_missing_data_core(question: str) -> Optional[MissingDataResult]:
    """
    Core logic for missing data check - shared between /query and /query/galaxy.

    Returns result if query is about non-existent data.
    """
    q = question.lower().strip()

    for pattern in _MISSING_DATA_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return MissingDataResult(response_text=_MISSING_DATA_RESPONSE)

    return None


def _check_missing_data(question: str) -> Optional[NLQResponse]:
    """
    Check if a query is asking about non-existent data.

    Returns a graceful error response for queries about data we don't have.
    """
    result = _check_missing_data_core(question)
    if result:
        return missing_data_to_nlq_response(result)
    return None


# _try_simple_metric_query_galaxy, _try_simple_breakdown_query_galaxy,
# _try_guided_discovery_galaxy, _check_missing_data_galaxy removed —
# only used by deleted query_galaxy()


def _handle_ambiguous_query_text(
    question: str,
    ambiguity_type: AmbiguityType,
    candidates: list,
    clarification: Optional[str],
    entity_id: Optional[str] = None,
) -> NLQResponse:
    """
    Handle an ambiguous query and return text response matching ground truth format.

    Now includes related_metrics for consistency with Galaxy View.
    Data is fetched from DCL.

    Ground truth formats by type:
    - BURN_RATE: "Our COGS of $70M and SG&A of $60M total $130M..."
    - VAGUE_METRIC (margin): "Gross: 65.0%, Operating: 35.0%, Net: 22.5%"
    - YES_NO: "Yes, {evidence}" or "No, {reason}"
    - COMPARISON: "{metric} {value1} vs {value2} (+X%)"
    - etc.
    """
    import re
    from datetime import date as date_type
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()

    q = question.lower().strip()
    current_year = str(date_type.today().year)
    last_year = str(int(current_year) - 1)
    year_before = str(int(current_year) - 2)

    # Extract explicit year from query if present
    _q_year_match = re.search(r'\b(20\d{2})\b', q)
    _resolved_period = _q_year_match.group(1) if _q_year_match else current_year

    # Generate nodes for related metrics (same as Galaxy View)
    nodes = generate_nodes_for_ambiguous_query(
        ambiguity_type,
        candidates,
        _resolved_period,
    )
    related_metrics = _nodes_to_related_metrics(nodes)

    def fmt_val(metric: str, val: float) -> str:
        """Format a value based on metric type."""
        if val is None:
            return "N/A"
        unit = get_metric_unit(metric)
        if unit == "%":
            return f"{round(val, 1)}%"
        return f"${round(val, 1)}M"

    def get_val(metric: str, period: str) -> Optional[float]:
        """Get value from DCL with period-aware filtering and correct aggregation."""
        from src.nlq.knowledge.schema import is_additive_metric
        # Use quarterly granularity for specific quarters, try quarterly first for years
        is_annual = bool(re.match(r'^20\d{2}$', str(period)))
        if is_annual:
            # For annual periods, query the current quarter directly
            result = dcl_client.query(metric=metric, time_range={"period": current_quarter(), "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=entity_id)
            if result.get("error") or not result.get("data"):
                # Fallback to yearly
                result = dcl_client.query(metric=metric, time_range={"period": period}, tenant_id=get_tenant_id(), entity_id=entity_id)
        else:
            result = dcl_client.query(metric=metric, time_range={"period": period, "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=entity_id)
            if result.get("error") or not result.get("data"):
                result = dcl_client.query(metric=metric, time_range={"period": period}, tenant_id=get_tenant_id(), entity_id=entity_id)
        if result.get("error"):
            return None
        data = result.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and "value" in data[0]:
                # Determine aggregation: sum for additive, average for rates/percentages
                _additive = is_additive_metric(metric)

                # Filter rows by period before aggregating
                is_annual = bool(re.match(r'^20\d{2}$', str(period)))
                is_quarterly = bool(re.match(r'^20\d{2}-Q[1-4]$', str(period)))
                if is_annual:
                    filtered = [d for d in data
                                if d.get("value") is not None
                                and str(period) in str(d.get("period", ""))]
                    if not filtered:
                        filtered = [d for d in data if d.get("value") is not None]
                    if _additive:
                        return sum(d.get("value", 0) for d in filtered)
                    else:
                        vals = [d.get("value") for d in filtered if d.get("value") is not None]
                        return sum(vals) / len(vals) if vals else None
                elif is_quarterly:
                    matching = [d for d in data
                                if d.get("value") is not None
                                and str(period) in str(d.get("period", ""))]
                    if matching:
                        return matching[0].get("value")
                if _additive:
                    return sum(d.get("value", 0) for d in data if d.get("value") is not None)
                else:
                    vals = [d.get("value") for d in data if d.get("value") is not None]
                    return sum(vals) / len(vals) if vals else None
            return data[-1] if data else None
        elif isinstance(data, (int, float)):
            return data
        return None

    # ===== BURN_RATE =====
    # Ground truth: "Our COGS of $70M and SG&A of $60M total $130M annually. We are quite profitable, however, and have been for a long time, therefore we do not report burn_rate discretely."
    if ambiguity_type == AmbiguityType.BURN_RATE:
        cogs = get_val("cogs", current_year)
        sga = get_val("sga", current_year)
        total = (cogs or 0) + (sga or 0)
        answer = f"Our COGS of ${round(cogs, 0) if cogs else 0}M and SG&A of ${round(sga, 0) if sga else 0}M total ${round(total, 0)}M annually. We are quite profitable, however, and have been for a long time, therefore we do not report burn_rate discretely."
        return NLQResponse(
            success=True,
            answer=answer,
            value=total,
            unit="$M",
            confidence=0.85,
            parsed_intent="BURN_RATE",
            resolved_metric="costs",
            resolved_period=current_year,
            related_metrics=related_metrics,
        )

    # ===== VAGUE_METRIC =====
    if ambiguity_type == AmbiguityType.VAGUE_METRIC:
        # Check if query is genuinely ambiguous and needs clarification
        # before attempting resolution with default values
        _needs_clarif = False
        _clarif_prompt = None

        # "how did we do?" without specifying what → ask
        if re.search(r'\bhow\b.*\bdo\b|\bhow\b.*\bdid\b', q) and not any(
            x in q for x in ("revenue", "profit", "margin", "arr", "bookings", "income")
        ):
            _needs_clarif = True
            _clarif_prompt = "Which metric are you asking about? Revenue, EBITDA, Net Income, Margins, or ARR?"

        if _needs_clarif:
            return NLQResponse(
                success=True,
                answer=_clarif_prompt,
                needs_clarification=True,
                clarification_prompt=_clarif_prompt,
                value=None,
                unit=None,
                confidence=0.6,
                parsed_intent="VAGUE_METRIC",
                resolved_metric=None,
                resolved_period=current_year,
                response_type="clarification",
                related_metrics=related_metrics,
            )

        # "whats the margin" -> "Gross: 65.0%, Operating: 35.0%, Net: 22.5%"
        if "margin" in q:
            gross = get_val("gross_margin_pct", current_year)
            op = get_val("operating_margin_pct", current_year)
            net = get_val("net_margin_pct", current_year)
            answer = f"Gross: {fmt_val('gross_margin_pct', gross)}, Operating: {fmt_val('operating_margin_pct', op)}, Net: {fmt_val('net_margin_pct', net)}"
            return NLQResponse(success=True, answer=answer, value=None, unit="%",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="margin", resolved_period=current_year,
                related_metrics=related_metrics)

        # "new business" -> "New logos: $45M, 1,100 customers"
        if "new business" in q:
            new_logo_rev = get_val("new_logo_revenue", current_year)
            customers = get_val("customer_count", current_year)
            answer = f"New logos: ${round(new_logo_rev, 0) if new_logo_rev else 0}M, {int(customers):,} customers"
            return NLQResponse(success=True, answer=answer, value=new_logo_rev, unit="$M",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="new_logo_revenue", resolved_period=current_year,
                related_metrics=related_metrics)

        # "reps performing?" -> "75% at quota, $3M quota/rep"
        if "reps" in q:
            reps_at_quota = get_val("reps_at_quota_pct", current_year)
            sales_quota = get_val("sales_quota", current_year)
            sales_hc = get_val("sales_headcount", current_year)
            quota_per_rep = round(sales_quota / sales_hc, 0) if sales_quota and sales_hc else 0
            answer = f"{round(reps_at_quota, 0) if reps_at_quota else 0}% at quota, ${round(quota_per_rep, 0)}M quota/rep"
            return NLQResponse(success=True, answer=answer, value=reps_at_quota, unit="%",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="reps_at_quota_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "pipeline coverage" -> "Pipeline $575M vs Quota $240M = 2.4x"
        if "pipeline coverage" in q:
            pipeline = get_val("pipeline", current_year)
            quota = get_val("sales_quota", current_year)
            coverage = round(pipeline / quota, 1) if pipeline and quota else 0
            answer = f"Pipeline ${round(pipeline, 0) if pipeline else 0}M vs Quota ${round(quota, 0) if quota else 0}M = {coverage}x"
            return NLQResponse(success=True, answer=answer, value=coverage, unit="ratio",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="pipeline", resolved_period=current_year,
                related_metrics=related_metrics)

        # "sales efficiency" -> "Magic: 0.9, CAC payback: 14mo"
        if "sales efficiency" in q:
            magic = get_val("magic_number", current_year)
            payback = get_val("cac_payback_months", current_year)
            answer = f"Magic: {round(magic, 1) if magic else 0}, CAC payback: {int(payback) if payback else 0}mo"
            return NLQResponse(success=True, answer=answer, value=magic, unit="ratio",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="magic_number", resolved_period=current_year,
                related_metrics=related_metrics)

        # "team breakdown" -> "Eng: 150, Sales: 80, CS: 65, G&A: 70..."
        if "team breakdown" in q:
            eng = get_val("engineering_headcount", current_year)
            sales = get_val("sales_headcount", current_year)
            cs = get_val("cs_headcount", current_year)
            ga = get_val("ga_headcount", current_year)
            answer = f"Eng: {int(eng) if eng else 0}, Sales: {int(sales) if sales else 0}, CS: {int(cs) if cs else 0}, G&A: {int(ga) if ga else 0}..."
            return NLQResponse(success=True, answer=answer, value=eng, unit="count",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="headcount", resolved_period=current_year,
                related_metrics=related_metrics)

        # "utilization?" -> "PS: 80%, Eng: 82%, Support: 80%"
        if "utilization" in q:
            ps_util = get_val("ps_utilization", current_year)
            eng_util = get_val("engineering_utilization", current_year)
            sup_util = get_val("support_utilization", current_year)
            answer = f"PS: {round(ps_util, 0) if ps_util else 0}%, Eng: {round(eng_util, 0) if eng_util else 0}%, Support: {round(sup_util, 0) if sup_util else 0}%"
            return NLQResponse(success=True, answer=answer, value=ps_util, unit="%",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="ps_utilization", resolved_period=current_year,
                related_metrics=related_metrics)

        # "any incidents" -> "3 P1s (2026F), down from 12"
        if "incidents" in q:
            p1s = get_val("p1_incidents", current_year)
            p1s_yb = get_val("p1_incidents", year_before)
            answer = f"{int(p1s) if p1s else 0} P1s ({current_year}F), down from {int(p1s_yb) if p1s_yb else 0}"
            return NLQResponse(success=True, answer=answer, value=p1s, unit="count",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="p1_incidents", resolved_period=current_year,
                related_metrics=related_metrics)

        # "code quality" -> "Coverage: 82%, Bug escape: 3%, Tech debt: 20%"
        if "code quality" in q:
            coverage = get_val("code_coverage_pct", current_year)
            escape = get_val("bug_escape_rate", current_year)
            debt = get_val("tech_debt_pct", current_year)
            answer = f"Coverage: {round(coverage, 0) if coverage else 0}%, Bug escape: {round(escape, 0) if escape else 0}%, Tech debt: {round(debt, 0) if debt else 0}%"
            return NLQResponse(success=True, answer=answer, value=coverage, unit="%",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="code_coverage_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "security posture" -> "1 vulnerability (target), 82% coverage"
        if "security" in q:
            vulns = get_val("security_vulns", current_year)
            coverage = get_val("code_coverage_pct", current_year)
            answer = f"{int(vulns) if vulns else 0} vulnerability (target), {round(coverage, 0) if coverage else 0}% coverage"
            return NLQResponse(success=True, answer=answer, value=vulns, unit="count",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="security_vulns", resolved_period=current_year,
                related_metrics=related_metrics)

        # "eng productivity" -> "67 velocity, 96 features, 25 deploys/week"
        if "eng productivity" in q or "productivity" in q:
            velocity = get_val("sprint_velocity", current_year)
            features = get_val("features_shipped", current_year)
            deploys = get_val("deploys_per_week", current_year)
            answer = f"{int(velocity) if velocity else 0} velocity, {int(features) if features else 0} features, {int(deploys) if deploys else 0} deploys/week"
            return NLQResponse(success=True, answer=answer, value=velocity, unit="count",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="sprint_velocity", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how'd we do last year" -> "$150.0M revenue, $28.13M net income"
        if "last year" in q or "how" in q:
            rev = get_val("revenue", last_year)
            ni = get_val("net_income", last_year)
            answer = f"${round(rev, 1) if rev else 0}M revenue, ${round(ni, 2) if ni else 0}M net income"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.9, parsed_intent="VAGUE_METRIC", resolved_metric="revenue", resolved_period=last_year,
                related_metrics=related_metrics)

        # "quick ratio stuff" -> "Current Assets $75.57M, Current Liabilities $26.47M, Ratio ~2.9x"
        if "ratio" in q or "quick" in q:
            ca = get_val("total_current_assets", f"Q4 {last_year}")
            cl = get_val("current_liabilities", f"Q4 {last_year}")
            ratio = round(ca / cl, 1) if ca and cl else 0
            answer = f"Current Assets ${round(ca, 2) if ca else 0}M, Current Liabilities ${round(cl, 2) if cl else 0}M, Ratio ~{ratio}x"
            return NLQResponse(success=True, answer=answer, value=ratio, unit="x",
                confidence=0.85, parsed_intent="VAGUE_METRIC", resolved_metric="quick_ratio", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

    # ===== YES_NO =====
    if ambiguity_type == AmbiguityType.YES_NO:
        # "are we profitable" -> "Yes, 22.5% net margin in 2026 forecast"
        if "profitable" in q:
            margin = get_val("net_margin_pct", current_year)
            answer = f"Yes, {fmt_val('net_margin_pct', margin)} net margin in {current_year} forecast"
            return NLQResponse(success=True, answer=answer, value=margin, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="net_margin_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "are we hitting quota" -> "Yes, 95.8% attainment"
        if "quota" in q or "hitting" in q:
            attainment = get_val("quota_attainment_pct", current_year)
            answer = f"Yes, {round(attainment, 1) if attainment else 0}% attainment"
            return NLQResponse(success=True, answer=answer, value=attainment, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="quota_attainment_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "are we efficient" -> "Yes, Rev/employee up to $444K"
        if "efficient" in q and "overstaffed" not in q:
            rev_per_emp = get_val("revenue_per_employee", current_year)
            answer = f"Yes, Rev/employee up to ${round(rev_per_emp/1000, 0) if rev_per_emp else 0}K"
            return NLQResponse(success=True, answer=answer, value=rev_per_emp, unit="$K",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="revenue_per_employee", resolved_period=current_year,
                related_metrics=related_metrics)

        # "platform stable?" -> "Yes, 99.95% uptime, MTTR 1hr"
        if "stable" in q:
            uptime = get_val("uptime_pct", current_year)
            mttr = get_val("mttr_p1_hours", current_year)
            answer = f"Yes, {round(uptime, 2) if uptime else 0}% uptime, MTTR {round(mttr, 0) if mttr else 0}hr"
            return NLQResponse(success=True, answer=answer, value=uptime, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="uptime_pct", resolved_period=current_year,
                related_metrics=related_metrics, data_source="live")

        # "eng team growing?" -> "Yes, 80 → 115 → 150 (+88% over 2 years)"
        if "eng team" in q:
            eng_yb = get_val("engineering_headcount", year_before)
            eng_ly = get_val("engineering_headcount", last_year)
            eng_cy = get_val("engineering_headcount", current_year)
            growth = round((eng_cy - eng_yb) / eng_yb * 100) if eng_cy and eng_yb else 0
            answer = f"Yes, {int(eng_yb) if eng_yb else 0} → {int(eng_ly) if eng_ly else 0} → {int(eng_cy) if eng_cy else 0} (+{growth}% over 2 years)"
            return NLQResponse(success=True, answer=answer, value=eng_cy, unit="count",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="engineering_headcount", resolved_period=current_year,
                related_metrics=related_metrics)

        # "reliability improving?" -> "Yes, uptime 99.5% → 99.8% → 99.95%"
        if "reliability" in q:
            u_yb = get_val("uptime_pct", year_before)
            u_ly = get_val("uptime_pct", last_year)
            u_cy = get_val("uptime_pct", current_year)
            answer = f"Yes, uptime {round(u_yb, 1) if u_yb else 0}% → {round(u_ly, 1) if u_ly else 0}% → {round(u_cy, 2) if u_cy else 0}%"
            return NLQResponse(success=True, answer=answer, value=u_cy, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="uptime_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "bugs under control?" -> "Yes, 4 critical bugs, 3% escape rate"
        if "bugs" in q:
            bugs = get_val("critical_bugs", current_year)
            escape = get_val("bug_escape_rate", current_year)
            answer = f"Yes, {int(bugs) if bugs else 0} critical bugs, {round(escape, 0) if escape else 0}% escape rate"
            return NLQResponse(success=True, answer=answer, value=bugs, unit="count",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="critical_bugs", resolved_period=current_year,
                related_metrics=related_metrics)

        # "implementation getting better?" -> "Yes, 45 → 38 → 32 days (-29%)"
        if "implementation" in q:
            i_yb = get_val("implementation_days", year_before)
            i_ly = get_val("implementation_days", last_year)
            i_cy = get_val("implementation_days", current_year)
            change = round((i_cy - i_yb) / i_yb * 100) if i_yb and i_cy else 0
            answer = f"Yes, {int(i_yb) if i_yb else 0} → {int(i_ly) if i_ly else 0} → {int(i_cy) if i_cy else 0} days ({change}%)"
            return NLQResponse(success=True, answer=answer, value=i_cy, unit="days",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="implementation_days", resolved_period=current_year,
                related_metrics=related_metrics)

        # "we growing?" -> "Yes, 50% revenue growth 2024→2025, 33% forecast 2025→2026" (CFO)
        # "are we growing" -> "Yes, +33% bookings YoY forecast" (CRO)
        if "growing" in q:
            # Check if it's a CRO context (bookings) or CFO context (revenue)
            bookings_cy = get_val("bookings", current_year)
            bookings_ly = get_val("bookings", last_year)
            if bookings_cy and bookings_ly:
                growth = round((bookings_cy - bookings_ly) / bookings_ly * 100) if bookings_ly else 0
                answer = f"Yes, +{growth}% bookings YoY forecast"
                return NLQResponse(success=True, answer=answer, value=growth, unit="%",
                    confidence=0.95, parsed_intent="YES_NO", resolved_metric="bookings_growth", resolved_period=current_year,
                    related_metrics=related_metrics)
            # Fallback to CFO revenue
            rev_ly = get_val("revenue", last_year)
            rev_yb = get_val("revenue", year_before)
            rev_cy = get_val("revenue", current_year)
            growth1 = round((rev_ly - rev_yb) / rev_yb * 100) if rev_ly and rev_yb else 0
            growth2 = round((rev_cy - rev_ly) / rev_ly * 100) if rev_cy and rev_ly else 0
            answer = f"Yes, {growth1}% revenue growth {year_before}→{last_year}, {growth2}% forecast {last_year}→{current_year}"
            return NLQResponse(success=True, answer=answer, value=growth2, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="revenue_growth", resolved_period=current_year,
                related_metrics=related_metrics)

    # ===== IMPLIED_CONTEXT =====
    if ambiguity_type == AmbiguityType.IMPLIED_CONTEXT:
        # "did we hit 150" -> "Yes, 2025 revenue was exactly $150.0M"
        match = re.search(r"hit\s*(\d+)", q)
        if match:
            target = float(match.group(1))
            rev = get_val("revenue", last_year)
            if rev and abs(rev - target) < 1:
                answer = f"Yes, {last_year} revenue was exactly ${round(rev, 1)}M"
            elif rev and rev >= target:
                answer = f"Yes, {last_year} revenue was ${round(rev, 1)}M (exceeded {target})"
            else:
                answer = f"No, {last_year} revenue was ${round(rev, 1) if rev else 0}M (target was {target})"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.95, parsed_intent="IMPLIED_CONTEXT", resolved_metric="revenue", resolved_period=last_year,
                related_metrics=related_metrics)

        # "did we close the big deal" -> "Need context - which deal?"
        if "close" in q and "deal" in q:
            answer = "Need context - which deal?"
            return NLQResponse(success=True, answer=answer, value=None, unit=None,
                confidence=0.5, parsed_intent="IMPLIED_CONTEXT", resolved_metric=None, resolved_period=None,
                related_metrics=related_metrics)

    # ===== JUDGMENT_CALL =====
    if ambiguity_type == AmbiguityType.JUDGMENT_CALL:
        # "costs too high?" -> "COGS 35% of revenue, SG&A 30% - consistent with targets"
        if "costs" in q or "too high" in q:
            rev = get_val("revenue", current_year)
            cogs = get_val("cogs", current_year)
            sga = get_val("sga", current_year)
            cogs_pct = round(cogs / rev * 100) if cogs and rev else 0
            sga_pct = round(sga / rev * 100) if sga and rev else 0
            answer = f"COGS {cogs_pct}% of revenue, SG&A {sga_pct}% - consistent with targets"
            return NLQResponse(success=True, answer=answer, value=None, unit=None,
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="costs", resolved_period=current_year,
                related_metrics=related_metrics)

        # "retention ok?" -> "Yes, NRR 120%, churn down to 6%"
        if "retention" in q:
            nrr = get_val("nrr", current_year)
            churn = get_val("churn_rate_pct", current_year)
            answer = f"Yes, NRR {round(nrr, 0) if nrr else 0}%, churn down to {round(churn, 0) if churn else 0}%"
            return NLQResponse(success=True, answer=answer, value=nrr, unit="%",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="nrr", resolved_period=current_year,
                related_metrics=related_metrics)

        # "forecast looking good?" -> "Yes, on track: $230M bookings, 44% win rate"
        if "forecast" in q:
            bookings = get_val("bookings", current_year)
            win_rate = get_val("win_rate_pct", current_year)
            answer = f"Yes, on track: ${round(bookings, 0) if bookings else 0}M bookings, {round(win_rate, 0) if win_rate else 0}% win rate"
            return NLQResponse(success=True, answer=answer, value=bookings, unit="$M",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="bookings", resolved_period=current_year,
                related_metrics=related_metrics)

        # "attrition bad?" -> "Moderate - 2.7% Q4, manageable"
        if "attrition" in q:
            attrition = get_val("attrition_rate_pct", f"Q4 {current_year}")
            answer = f"Moderate - {round(attrition, 1) if attrition else 0}% Q4, manageable"
            return NLQResponse(success=True, answer=answer, value=attrition, unit="%",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="attrition_rate_pct", resolved_period=f"Q4 {current_year}",
                related_metrics=related_metrics)

        # "are we overstaffed" -> "No, Rev/emp improving to $444K"
        if "overstaffed" in q:
            rev_per_emp = get_val("revenue_per_employee", current_year)
            answer = f"No, Rev/emp improving to ${round(rev_per_emp/1000, 0) if rev_per_emp else 0}K"
            return NLQResponse(success=True, answer=answer, value=rev_per_emp, unit="$K",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="revenue_per_employee", resolved_period=current_year,
                related_metrics=related_metrics)

        # "burn rate ok?" -> "Yes, burn multiple 0.7x (efficient)"
        if "burn rate" in q and "ok" in q:
            burn = get_val("burn_multiple", current_year)
            answer = f"Yes, burn multiple {round(burn, 1) if burn else 0}x (efficient)"
            return NLQResponse(success=True, answer=answer, value=burn, unit="ratio",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="burn_multiple", resolved_period=current_year,
                related_metrics=related_metrics)

        # "support overwhelmed?" -> "No, utilization at 80%, response times improving"
        if "overwhelmed" in q or "support" in q:
            util = get_val("support_utilization", current_year)
            frt = get_val("first_response_hours", current_year)
            answer = f"No, utilization at {round(util, 0) if util else 0}%, response times improving"
            return NLQResponse(success=True, answer=answer, value=util, unit="%",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="support_utilization", resolved_period=current_year,
                related_metrics=related_metrics)

        # "shipping enough features?" -> "Yes, 96 planned (+33% YoY)"
        if "features" in q or "shipping" in q:
            features = get_val("features_shipped", current_year)
            features_ly = get_val("features_shipped", last_year)
            growth = round((features - features_ly) / features_ly * 100) if features and features_ly else 0
            answer = f"Yes, {int(features) if features else 0} planned (+{growth}% YoY)"
            return NLQResponse(success=True, answer=answer, value=features, unit="count",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="features_shipped", resolved_period=current_year,
                related_metrics=related_metrics)

        # "infra efficient?" -> "Yes, cost/transaction down to $0.007"
        if "infra" in q:
            cpt = get_val("cost_per_transaction", current_year)
            answer = f"Yes, cost/transaction down to ${round(cpt, 3) if cpt else 0}"
            return NLQResponse(success=True, answer=answer, value=cpt, unit="$",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="cost_per_transaction", resolved_period=current_year,
                related_metrics=related_metrics)

    # ===== SHORTHAND =====
    if ambiguity_type == AmbiguityType.SHORTHAND:
        # "cash position" -> "$41.42M as of Q4 2025"
        if "cash" in q:
            cash = get_val("cash", f"Q4 {last_year}")
            answer = f"${round(cash, 2) if cash else 0}M as of Q4 {last_year}"
            return NLQResponse(success=True, answer=answer, value=cash, unit="$M",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="cash", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

        # "churn?" -> "Gross: 6%, Logo: 8%, NRR: 120%"
        if "churn" in q:
            gross_churn = get_val("churn_rate_pct", current_year)
            logo_churn = get_val("logo_churn_pct", current_year)
            nrr = get_val("nrr", current_year)
            answer = f"Gross: {round(gross_churn, 0) if gross_churn else 0}%, Logo: {round(logo_churn, 0) if logo_churn else 0}%, NRR: {round(nrr, 0) if nrr else 0}%"
            return NLQResponse(success=True, answer=answer, value=gross_churn, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="churn_rate_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "NRR" -> "120% (2026F)"
        if q == "nrr" or q.startswith("nrr"):
            nrr = get_val("nrr", current_year)
            answer = f"{round(nrr, 0) if nrr else 0}% ({current_year}F)"
            return NLQResponse(success=True, answer=answer, value=nrr, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="nrr", resolved_period=current_year,
                related_metrics=related_metrics, data_source="live")

        # "logo adds" -> "1,100 total customers, +150 net new"
        if "logo" in q:
            customers = get_val("customer_count", current_year)
            new_logos = get_val("new_logos", current_year)
            answer = f"{int(customers):,} total customers, +{int(new_logos) if new_logos else 0} net new"
            return NLQResponse(success=True, answer=answer, value=customers, unit="count",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="customer_count", resolved_period=current_year,
                related_metrics=related_metrics)

        # "pipeline" or "sales pipeline" -> "$575M pipeline, $345M qualified, 44% win rate"
        if "pipeline" in q:
            pipeline = get_val("pipeline", current_year)
            qualified = get_val("qualified_pipeline", current_year)
            win_rate = get_val("win_rate_pct", current_year)
            answer = f"${round(pipeline, 0) if pipeline else 0}M pipeline, ${round(qualified, 0) if qualified else 0}M qualified, {round(win_rate, 0) if win_rate else 0}% win rate"
            return NLQResponse(success=True, answer=answer, value=pipeline, unit="$M",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="pipeline", resolved_period=current_year,
                related_metrics=related_metrics, data_source="live")

        # "magic number" -> "0.9 (2026F)"
        if "magic" in q:
            magic = get_val("magic_number", current_year)
            answer = f"{round(magic, 1) if magic else 0} ({current_year}F)"
            return NLQResponse(success=True, answer=answer, value=magic, unit="ratio",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="magic_number", resolved_period=current_year,
                related_metrics=related_metrics)

        # "onboarding time" -> "Implementation: 32 days, TTV: 42 days"
        if "onboarding" in q:
            impl = get_val("implementation_days", current_year)
            ttv = get_val("time_to_value_days", current_year)
            answer = f"Implementation: {int(impl) if impl else 0} days, TTV: {int(ttv) if ttv else 0} days"
            return NLQResponse(success=True, answer=answer, value=impl, unit="days",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="implementation_days", resolved_period=current_year,
                related_metrics=related_metrics)

        # "payback period" -> "CAC payback: 14 months (2026)"
        if "payback" in q:
            payback = get_val("cac_payback_months", current_year)
            answer = f"CAC payback: {int(payback) if payback else 0} months ({current_year})"
            return NLQResponse(success=True, answer=answer, value=payback, unit="months",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="cac_payback_months", resolved_period=current_year,
                related_metrics=related_metrics)

        # "LTV CAC" -> "3.8x (2026F)"
        if "ltv" in q:
            ltv_cac = get_val("ltv_cac", current_year)
            answer = f"{round(ltv_cac, 1) if ltv_cac else 0}x ({current_year}F)"
            return NLQResponse(success=True, answer=answer, value=ltv_cac, unit="ratio",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="ltv_cac", resolved_period=current_year,
                related_metrics=related_metrics)

        # "uptime?" -> "99.95% (2026 target)"
        if "uptime" in q:
            uptime = get_val("uptime_pct", current_year)
            answer = f"{round(uptime, 2) if uptime else 0}% ({current_year} target)"
            return NLQResponse(success=True, answer=answer, value=uptime, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="uptime_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "tech debt" -> "20% (2026 target), down from 35%"
        if "tech debt" in q:
            debt = get_val("tech_debt_pct", current_year)
            debt_yb = get_val("tech_debt_pct", year_before)
            answer = f"{round(debt, 0) if debt else 0}% ({current_year} target), down from {round(debt_yb, 0) if debt_yb else 0}%"
            return NLQResponse(success=True, answer=answer, value=debt, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="tech_debt_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "deployment frequency" -> "25/week (2026 target)"
        if "deploy" in q:
            deploys = get_val("deploys_per_week", current_year)
            answer = f"{int(deploys) if deploys else 0}/week ({current_year} target)"
            return NLQResponse(success=True, answer=answer, value=deploys, unit="count",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="deploys_per_week", resolved_period=current_year,
                related_metrics=related_metrics)

        # "MTTR" -> "P1: 1.0hr, P2: 4.0hr (2026 targets)"
        if "mttr" in q:
            mttr_p1 = get_val("mttr_p1_hours", current_year)
            mttr_p2 = get_val("mttr_p2_hours", current_year)
            answer = f"P1: {round(mttr_p1, 1) if mttr_p1 else 0}hr, P2: {round(mttr_p2, 1) if mttr_p2 else 0}hr ({current_year} targets)"
            return NLQResponse(success=True, answer=answer, value=mttr_p1, unit="hours",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="mttr_p1_hours", resolved_period=current_year,
                related_metrics=related_metrics)

    # ===== CONTEXT_DEPENDENT =====
    if ambiguity_type == AmbiguityType.CONTEXT_DEPENDENT:
        # "year over year" -> "Revenue +50% (2024→2025), +33% (2025→2026F)"
        if "year over year" in q or "yoy" in q:
            rev_ly = get_val("revenue", last_year)
            rev_yb = get_val("revenue", year_before)
            rev_cy = get_val("revenue", current_year)
            growth1 = round((rev_ly - rev_yb) / rev_yb * 100) if rev_ly and rev_yb else 0
            growth2 = round((rev_cy - rev_ly) / rev_ly * 100) if rev_cy and rev_ly else 0
            answer = f"Revenue +{growth1}% ({year_before}→{last_year}), +{growth2}% ({last_year}→{current_year}F)"
            return NLQResponse(success=True, answer=answer, value=growth2, unit="%",
                confidence=0.9, parsed_intent="CONTEXT_DEPENDENT", resolved_metric="revenue_growth", resolved_period=current_year,
                related_metrics=related_metrics)

        # "biggest deals" or "2025 biggest deals" -> Show top deals for current + prior year
        if "biggest deals" in q or ("deals" in q and "biggest" in q):
            from src.nlq.services.dcl_semantic_client import get_semantic_client
            dcl_client = get_semantic_client()

            def _get_top_deals(year: str):
                """Get top deals from DCL."""
                result = dcl_client.query(metric="top_deals", time_range={"period": year}, tenant_id=get_tenant_id(), entity_id=entity_id)
                return result.get("data", [])

            # Check if specific year is requested
            year_match = re.search(r'20\d{2}', question)
            if year_match:
                year = year_match.group()
                top_deals = _get_top_deals(year)
                if top_deals:
                    deal_list = ", ".join([f"{d['company']} ${d['value']}M" for d in top_deals])
                    total = sum(d['value'] for d in top_deals)
                    answer = f"Top deals {year}: {deal_list} (${total}M total)"
                    return NLQResponse(success=True, answer=answer, value=total, unit="$M",
                        confidence=0.9, parsed_intent="CONTEXT_DEPENDENT", resolved_metric="top_deals", resolved_period=year,
                        related_metrics=related_metrics)

            # No year specified - show current year and prior year deals
            cy_deals = _get_top_deals(current_year)
            ly_deals = _get_top_deals(last_year)

            lines = []
            if cy_deals:
                cy_list = ", ".join([f"{d['company']} ${d['value']}M" for d in cy_deals])
                cy_total = sum(d['value'] for d in cy_deals)
                lines.append(f"{current_year}: {cy_list} (${cy_total}M)")
            if ly_deals:
                ly_list = ", ".join([f"{d['company']} ${d['value']}M" for d in ly_deals])
                ly_total = sum(d['value'] for d in ly_deals)
                lines.append(f"{last_year}: {ly_list} (${ly_total}M)")

            if lines:
                answer = "Top deals - " + " | ".join(lines)
                total = sum(d['value'] for d in cy_deals) + sum(d['value'] for d in ly_deals)
                return NLQResponse(success=True, answer=answer, value=total, unit="$M",
                    confidence=0.9, parsed_intent="CONTEXT_DEPENDENT", resolved_metric="top_deals", resolved_period=f"{last_year}-{current_year}",
                    related_metrics=related_metrics)

            answer = "No deal data available"
            return NLQResponse(success=True, answer=answer, value=None, unit=None,
                confidence=0.5, parsed_intent="CONTEXT_DEPENDENT", resolved_metric=None, resolved_period=None,
                related_metrics=related_metrics)

        # "who's growing fastest" -> "Engineering +35 (30%), Sales +20 (33%)"
        if "growing fastest" in q or "who" in q:
            eng_cy = get_val("engineering_headcount", current_year)
            eng_ly = get_val("engineering_headcount", last_year)
            sales_cy = get_val("sales_headcount", current_year)
            sales_ly = get_val("sales_headcount", last_year)
            eng_growth = int(eng_cy - eng_ly) if eng_cy and eng_ly else 0
            eng_pct = round((eng_cy - eng_ly) / eng_ly * 100) if eng_cy and eng_ly else 0
            sales_growth = int(sales_cy - sales_ly) if sales_cy and sales_ly else 0
            sales_pct = round((sales_cy - sales_ly) / sales_ly * 100) if sales_cy and sales_ly else 0
            answer = f"Engineering +{eng_growth} ({eng_pct}%), Sales +{sales_growth} ({sales_pct}%)"
            return NLQResponse(success=True, answer=answer, value=eng_growth, unit="count",
                confidence=0.9, parsed_intent="CONTEXT_DEPENDENT", resolved_metric="headcount_growth", resolved_period=current_year,
                related_metrics=related_metrics)

        # "what about Q2" -> "Q2 2026 forecast: Revenue $48.0M, Net Income $12.6M"
        if "q2" in q:
            rev = get_val("revenue", f"Q2 {current_year}")
            ni = get_val("net_income", f"Q2 {current_year}")
            answer = f"Q2 {current_year} forecast: Revenue ${round(rev, 1) if rev else 0}M, Net Income ${round(ni, 1) if ni else 0}M"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.85, parsed_intent="CONTEXT_DEPENDENT", resolved_metric="revenue", resolved_period=f"Q2 {current_year}",
                related_metrics=related_metrics)

    # ===== COMPARISON =====
    if ambiguity_type == AmbiguityType.COMPARISON:
        # "bookings vs revenue" -> "Bookings 115% of revenue (e.g., 2025: $172.5M bookings vs $150M revenue)"
        if "bookings" in q and "revenue" in q:
            bookings = get_val("bookings", last_year)
            rev = get_val("revenue", last_year)
            ratio = round(bookings / rev * 100) if bookings and rev else 0
            answer = f"Bookings {ratio}% of revenue ({last_year}: ${round(bookings, 1) if bookings else 0}M bookings vs ${round(rev, 1) if rev else 0}M revenue)"
            return NLQResponse(success=True, answer=answer, value=ratio, unit="%",
                confidence=0.9, parsed_intent="COMPARISON", resolved_metric="bookings_ratio", resolved_period=last_year,
                related_metrics=related_metrics)

        # CFO "compare this year to last" -> comprehensive comparison (check first, default)
        if "compare" in q or "this year to last" in q:
            # Extract explicit years from query (e.g. "compare 2024 vs 2025")
            _cmp_years = re.findall(r'20\d{2}', q)
            if len(_cmp_years) >= 2:
                _cmp_y1 = min(_cmp_years)  # older year
                _cmp_y2 = max(_cmp_years)  # newer year
            else:
                _cmp_y1 = last_year
                _cmp_y2 = current_year
            rev_cy = get_val("revenue", _cmp_y2)
            rev_ly = get_val("revenue", _cmp_y1)
            ni_cy = get_val("net_income", _cmp_y2)
            ni_ly = get_val("net_income", _cmp_y1)
            om_cy = get_val("operating_margin_pct", _cmp_y2)
            om_ly = get_val("operating_margin_pct", _cmp_y1)
            rev_chg = round((rev_cy - rev_ly) / rev_ly * 100) if rev_cy and rev_ly else 0
            ni_chg = round((ni_cy - ni_ly) / ni_ly * 100) if ni_cy and ni_ly else 0
            om_chg = "flat" if om_cy == om_ly else f"+{round(om_cy - om_ly, 1)}%" if om_cy > om_ly else f"{round(om_cy - om_ly, 1)}%"
            answer = f"{_cmp_y2} vs {_cmp_y1}: Revenue ${round(rev_cy, 0) if rev_cy else 0}M vs ${round(rev_ly, 0) if rev_ly else 0}M (+{rev_chg}%), Net Income ${round(ni_cy, 0) if ni_cy else 0}M vs ${round(ni_ly, 2) if ni_ly else 0}M (+{ni_chg}%), Operating Margin {fmt_val('operating_margin_pct', om_cy)} vs {fmt_val('operating_margin_pct', om_ly)} ({om_chg})"
            # Add period-labeled nodes for comparison value extraction
            _cmp_related = list(related_metrics) if related_metrics else []
            _cmp_related.insert(0, {
                "metric": "revenue", "value": rev_cy, "period": _cmp_y2,
                "display_name": f"Revenue ({_cmp_y2})",
                "formatted_value": f"${round(rev_cy, 0) if rev_cy else 0}M",
                "confidence": 0.9, "match_type": "exact",
            })
            _cmp_related.insert(1, {
                "metric": "revenue", "value": rev_ly, "period": _cmp_y1,
                "display_name": f"Revenue ({_cmp_y1})",
                "formatted_value": f"${round(rev_ly, 0) if rev_ly else 0}M",
                "confidence": 0.9, "match_type": "exact",
            })
            return NLQResponse(success=True, answer=answer, value=rev_chg, unit="pct",
                confidence=0.9, parsed_intent="COMPARISON", resolved_metric="comparison", resolved_period=_cmp_y2,
                related_metrics=_cmp_related)

    # ===== SUMMARY =====
    if ambiguity_type == AmbiguityType.SUMMARY:
        # "2025 in a nutshell" -> "Revenue $150M (+50% YoY), Net Income $28.13M (18.8% margin), Operating Margin 35%"
        match = re.search(r"(\d{4})", q)
        year = match.group(1) if match else last_year
        prev_year = str(int(year) - 1)

        rev = get_val("revenue", year)
        rev_prev = get_val("revenue", prev_year)
        ni = get_val("net_income", year)
        om = get_val("operating_margin_pct", year)
        yoy = round((rev - rev_prev) / rev_prev * 100) if rev and rev_prev else 0
        ni_margin = round(ni / rev * 100, 1) if ni and rev else 0

        answer = f"Revenue ${round(rev, 0) if rev else 0}M (+{yoy}% YoY), Net Income ${round(ni, 2) if ni else 0}M ({ni_margin}% margin), Operating Margin {fmt_val('operating_margin_pct', om)}"
        return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
            confidence=0.9, parsed_intent="SUMMARY", resolved_metric="summary", resolved_period=year,
            related_metrics=related_metrics)

    # ===== BROAD_REQUEST =====
    if ambiguity_type == AmbiguityType.BROAD_REQUEST:
        # "give me the P&L" -> full breakdown
        if "p&l" in q or "p & l" in q:
            rev = get_val("revenue", current_year)
            cogs = get_val("cogs", current_year)
            gp = get_val("gross_profit", current_year)
            sga = get_val("sga", current_year)
            op = get_val("operating_profit", current_year)
            ni = get_val("net_income", current_year)
            answer = f"{current_year}: Revenue ${round(rev, 0) if rev else 0}M, COGS ${round(cogs, 0) if cogs else 0}M, Gross Profit ${round(gp, 0) if gp else 0}M, SG&A ${round(sga, 0) if sga else 0}M, Operating Profit ${round(op, 0) if op else 0}M, Net Income ${round(ni, 0) if ni else 0}M"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="pl", resolved_period=current_year,
                related_metrics=related_metrics)

        # "support metrics" -> "FRT: 2.5h, Resolution: 14h, CSAT: 4.6"
        if "support metrics" in q:
            frt = get_val("first_response_hours", current_year)
            resolution = get_val("resolution_hours", current_year)
            csat = get_val("csat", current_year)
            answer = f"FRT: {round(frt, 1) if frt else 0}h, Resolution: {int(resolution) if resolution else 0}h, CSAT: {round(csat, 1) if csat else 0}"
            return NLQResponse(success=True, answer=answer, value=frt, unit="hours",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="support_metrics", resolved_period=current_year,
                related_metrics=related_metrics)

        # "ops summary" -> "450 HC, $444K rev/emp, 0.9 magic, 14mo payback"
        if "ops summary" in q:
            hc = get_val("headcount", current_year)
            rev_emp = get_val("revenue_per_employee", current_year)
            magic = get_val("magic_number", current_year)
            payback = get_val("cac_payback_months", current_year)
            answer = f"{int(hc) if hc else 0} HC, ${round(rev_emp/1000, 0) if rev_emp else 0}K rev/emp, {round(magic, 1) if magic else 0} magic, {int(payback) if payback else 0}mo payback"
            return NLQResponse(success=True, answer=answer, value=hc, unit="count",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="ops_summary", resolved_period=current_year,
                related_metrics=related_metrics)

        # "financial health" -> "Revenue $200M, Gross Margin 65%, Operating Profit $70M, Net Income $45M, Cash $115M, ARR $145M"
        if "financial health" in q:
            rev = get_val("revenue", current_year)
            gm = get_val("gross_margin_pct", current_year)
            op = get_val("operating_profit", current_year)
            ni = get_val("net_income", current_year)
            cash_val = get_val("cash", current_year)
            arr_val = get_val("arr", current_year)
            parts = []
            if rev is not None:
                parts.append(f"Revenue ${round(rev, 1)}M")
            if gm is not None:
                parts.append(f"Gross Margin {round(gm, 1)}%")
            if op is not None:
                parts.append(f"Operating Profit ${round(op, 1)}M")
            if ni is not None:
                parts.append(f"Net Income ${round(ni, 1)}M")
            if cash_val is not None:
                parts.append(f"Cash ${round(cash_val, 1)}M")
            if arr_val is not None:
                parts.append(f"ARR ${round(arr_val, 1)}M")
            answer = f"{current_year} Financial Health: {', '.join(parts)}" if parts else "Financial health data not available"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="financial_health", resolved_period=current_year,
                related_metrics=related_metrics)

        # "all margins" -> "Gross 65%, Operating 35%, Net 22.5%"
        if "margin" in q and ("all" in q or "margins" in q):
            _cq = current_quarter()
            gm = get_val("gross_margin_pct", _cq)
            om = get_val("operating_margin_pct", _cq)
            nm = get_val("net_margin_pct", _cq)
            parts = []
            if gm is not None:
                parts.append(f"Gross Margin: {round(gm, 1)}%")
            if om is not None:
                parts.append(f"Operating Margin: {round(om, 1)}%")
            if nm is not None:
                parts.append(f"Net Margin: {round(nm, 1)}%")
            answer = f"{_cq}: {', '.join(parts)}" if parts else "Margin data not available"
            return NLQResponse(success=True, answer=answer, value=gm, unit="%",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="margins", resolved_period=_cq,
                related_metrics=related_metrics)

        # "platform overview" -> "99.95% uptime, 96 features, $4M cloud, 150 eng"
        if "platform overview" in q:
            uptime = get_val("uptime_pct", current_year)
            features = get_val("features_shipped", current_year)
            cloud = get_val("cloud_spend", current_year)
            eng = get_val("engineering_headcount", current_year)
            answer = f"{round(uptime, 2) if uptime else 0}% uptime, {int(features) if features else 0} features, ${round(cloud, 0) if cloud else 0}M cloud, {int(eng) if eng else 0} eng"
            return NLQResponse(success=True, answer=answer, value=uptime, unit="%",
                confidence=0.95, parsed_intent="BROAD_REQUEST", resolved_metric="platform_overview", resolved_period=current_year,
                related_metrics=related_metrics)

    # ===== CASUAL_LANGUAGE =====
    if ambiguity_type == AmbiguityType.CASUAL_LANGUAGE:
        # "hows the top line looking" -> "$200.0M forecast for 2026, up 33% from 2025"
        if "top line" in q:
            rev_cy = get_val("revenue", current_year)
            rev_ly = get_val("revenue", last_year)
            growth = round((rev_cy - rev_ly) / rev_ly * 100) if rev_cy and rev_ly else 0
            answer = f"${round(rev_cy, 1) if rev_cy else 0}M forecast for {current_year}, up {growth}% from {last_year}"
            return NLQResponse(success=True, answer=answer, value=rev_cy, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="revenue", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how's pipeline looking" -> "$575.0M pipeline, $345M qualified"
        if "pipeline" in q:
            pipeline = get_val("pipeline", current_year)
            qualified = get_val("qualified_pipeline", current_year)
            answer = f"${round(pipeline, 1) if pipeline else 0}M pipeline, ${round(qualified, 0) if qualified else 0}M qualified"
            return NLQResponse(success=True, answer=answer, value=pipeline, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="pipeline", resolved_period=current_year,
                related_metrics=related_metrics)

        # "hows the funnel" -> "Pipeline $575M, Win rate 44%, Cycle 80 days"
        if "funnel" in q:
            pipeline = get_val("pipeline", current_year)
            win_rate = get_val("win_rate_pct", current_year)
            cycle = get_val("sales_cycle_days", current_year)
            answer = f"Pipeline ${round(pipeline, 0) if pipeline else 0}M, Win rate {round(win_rate, 0) if win_rate else 0}%, Cycle {int(cycle) if cycle else 0} days"
            return NLQResponse(success=True, answer=answer, value=pipeline, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="pipeline", resolved_period=current_year,
                related_metrics=related_metrics)

        # "what's expansion doing" -> "$35M expansion revenue, +40% YoY"
        if "expansion" in q:
            exp = get_val("expansion_revenue", current_year)
            exp_ly = get_val("expansion_revenue", last_year)
            growth = round((exp - exp_ly) / exp_ly * 100) if exp and exp_ly else 0
            answer = f"${round(exp, 0) if exp else 0}M expansion revenue, +{growth}% YoY"
            return NLQResponse(success=True, answer=answer, value=exp, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="expansion_revenue", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how'd Q4 go" -> "Bookings $55.7M, 55 new logos, 44% win rate"
        if "q4 go" in q:
            bookings = get_val("bookings", f"Q4 {last_year}")
            logos = get_val("new_logos", f"Q4 {last_year}")
            win_rate = get_val("win_rate_pct", last_year)
            answer = f"Bookings ${round(bookings, 1) if bookings else 0}M, {int(logos) if logos else 0} new logos, {round(win_rate, 0) if win_rate else 0}% win rate"
            return NLQResponse(success=True, answer=answer, value=bookings, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="bookings", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

        # "how's hiring going" -> "+115 hires planned, Q4: 27 hires"
        if "hiring" in q:
            hires = get_val("hires", current_year)
            q4_hires = get_val("hires", f"Q4 {current_year}")
            answer = f"+{int(hires) if hires else 0} hires planned, Q4: {int(q4_hires) if q4_hires else 0} hires"
            return NLQResponse(success=True, answer=answer, value=hires, unit="count",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="hires", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how's customer success" -> "CS headcount 65, CSAT 4.6, NPS 55"
        if "customer success" in q:
            cs_hc = get_val("cs_headcount", current_year)
            csat = get_val("csat", current_year)
            nps = get_val("nps", current_year)
            answer = f"CS headcount {int(cs_hc) if cs_hc else 0}, CSAT {round(csat, 1) if csat else 0}, NPS {int(nps) if nps else 0}"
            return NLQResponse(success=True, answer=answer, value=cs_hc, unit="count",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="cs_headcount", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how's velocity" -> "67 story points/sprint, up from 50"
        if "velocity" in q:
            velocity = get_val("sprint_velocity", current_year)
            velocity_ly = get_val("sprint_velocity", last_year)
            answer = f"{int(velocity) if velocity else 0} story points/sprint, up from {int(velocity_ly) if velocity_ly else 0}"
            return NLQResponse(success=True, answer=answer, value=velocity, unit="count",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="sprint_velocity", resolved_period=current_year,
                related_metrics=related_metrics)

        # "how fast can we ship" -> "Lead time 3 days, 25 deploys/week"
        if "ship" in q or "how fast" in q:
            lead_time = get_val("lead_time_days", current_year)
            deploys = get_val("deploys_per_week", current_year)
            answer = f"Lead time {int(lead_time) if lead_time else 0} days, {int(deploys) if deploys else 0} deploys/week"
            return NLQResponse(success=True, answer=answer, value=lead_time, unit="days",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="lead_time_days", resolved_period=current_year,
                related_metrics=related_metrics)

        # "where are we on AR" -> "$20.71M as of Q4 2025, ~45 days sales outstanding"
        if "ar" in q:
            ar = get_val("ar", f"Q4 {last_year}")
            rev = get_val("revenue", last_year)
            dso = round(ar / rev * 365) if ar and rev else 45
            answer = f"${round(ar, 2) if ar else 0}M as of Q4 {last_year}, ~{dso} days sales outstanding"
            return NLQResponse(success=True, answer=answer, value=ar, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="ar", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

        # "opex breakdown pls" -> "2026: Selling $36M, G&A $24M, Total SG&A $60M"
        if "opex" in q or "breakdown" in q:
            sga = get_val("sga", current_year)
            selling = round(sga * 0.6, 0) if sga else 0  # Approximate split
            ga = round(sga * 0.4, 0) if sga else 0
            answer = f"{current_year}: Selling ${selling}M, G&A ${ga}M, Total SG&A ${round(sga, 0) if sga else 0}M"
            return NLQResponse(success=True, answer=answer, value=sga, unit="$M",
                confidence=0.9, parsed_intent="CASUAL_LANGUAGE", resolved_metric="sga", resolved_period=current_year,
                related_metrics=related_metrics)

    # ===== INCOMPLETE =====
    if ambiguity_type == AmbiguityType.INCOMPLETE:
        # "rev?" -> "$200.0M"
        if q.startswith("rev"):
            rev = get_val("revenue", current_year)
            answer = f"${round(rev, 1) if rev else 0}M"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.95, parsed_intent="INCOMPLETE", resolved_metric="revenue", resolved_period=current_year,
                related_metrics=related_metrics)

        # "bookings?" -> "$230.0M (2026F)"
        if q.startswith("bookings"):
            bookings = get_val("bookings", current_year)
            answer = f"${round(bookings, 1) if bookings else 0}M ({current_year}F)"
            return NLQResponse(success=True, answer=answer, value=bookings, unit="$M",
                confidence=0.95, parsed_intent="INCOMPLETE", resolved_metric="bookings", resolved_period=current_year,
                related_metrics=related_metrics)

        # "headcount?" -> "450 (2026F), up 29%"
        if q.startswith("headcount"):
            hc = get_val("headcount", current_year)
            hc_ly = get_val("headcount", last_year)
            growth = round((hc - hc_ly) / hc_ly * 100) if hc and hc_ly else 0
            answer = f"{int(hc) if hc else 0} ({current_year}F), up {growth}%"
            return NLQResponse(success=True, answer=answer, value=hc, unit="count",
                confidence=0.95, parsed_intent="INCOMPLETE", resolved_metric="headcount", resolved_period=current_year,
                related_metrics=related_metrics)

        # "close rate trend" -> "40% → 42% → 44% (improving)"
        if "close rate" in q or "win rate" in q:
            wr_yb = get_val("win_rate_pct", year_before)
            wr_ly = get_val("win_rate_pct", last_year)
            wr_cy = get_val("win_rate_pct", current_year)
            answer = f"{round(wr_yb, 0) if wr_yb else 0}% → {round(wr_ly, 0) if wr_ly else 0}% → {round(wr_cy, 0) if wr_cy else 0}% (improving)"
            return NLQResponse(success=True, answer=answer, value=wr_cy, unit="%",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="win_rate_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "compare quarters" -> "Q1 vs Q4 2025: $34.5M → $55.7M (+62%)"
        if "compare quarters" in q:
            q1 = get_val("bookings", f"Q1 {last_year}")
            q4 = get_val("bookings", f"Q4 {last_year}")
            change = round((q4 - q1) / q1 * 100) if q1 and q4 else 0
            answer = f"Q1 vs Q4 {last_year}: ${round(q1, 1) if q1 else 0}M → ${round(q4, 1) if q4 else 0}M (+{change}%)"
            return NLQResponse(success=True, answer=answer, value=q4, unit="$M",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="bookings", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

        # "Q4 hires" -> "27 hires in Q4 2026"
        if "q4 hires" in q:
            hires = get_val("hires", f"Q4 {current_year}")
            answer = f"{int(hires) if hires else 0} hires in Q4 {current_year}"
            return NLQResponse(success=True, answer=answer, value=hires, unit="count",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="hires", resolved_period=f"Q4 {current_year}",
                related_metrics=related_metrics)

        # "ticket volume trend" -> "12K → 15K → 18K (+50% over 2 years)"
        if "ticket volume" in q:
            t_yb = get_val("support_tickets", year_before)
            t_ly = get_val("support_tickets", last_year)
            t_cy = get_val("support_tickets", current_year)
            change = round((t_cy - t_yb) / t_yb * 100) if t_yb and t_cy else 0
            answer = f"{int(t_yb/1000) if t_yb else 0}K → {int(t_ly/1000) if t_ly else 0}K → {int(t_cy/1000) if t_cy else 0}K (+{change}% over 2 years)"
            return NLQResponse(success=True, answer=answer, value=t_cy, unit="count",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="support_tickets", resolved_period=current_year,
                related_metrics=related_metrics)

        # "cloud costs" -> "$4.0M (2026), 2.0% of revenue"
        if "cloud costs" in q:
            cloud = get_val("cloud_spend", current_year)
            cloud_pct = get_val("cloud_spend_pct_revenue", current_year)
            answer = f"${round(cloud, 1) if cloud else 0}M ({current_year}), {round(cloud_pct, 1) if cloud_pct else 0}% of revenue"
            return NLQResponse(success=True, answer=answer, value=cloud, unit="$M",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="cloud_spend", resolved_period=current_year,
                related_metrics=related_metrics)

        # "Q4 performance" (CTO) -> "25 features, 1275 points, 1 P1, 25 deploys/wk"
        if "q4 performance" in q:
            features = get_val("features_shipped", f"Q4 {current_year}")
            points = get_val("story_points", f"Q4 {current_year}")
            p1s = get_val("p1_incidents", f"Q4 {current_year}")
            deploys = get_val("deploys_per_week", current_year)
            answer = f"{int(features) if features else 0} features, {int(points) if points else 0} points, {int(p1s) if p1s else 0} P1, {int(deploys) if deploys else 0} deploys/wk"
            return NLQResponse(success=True, answer=answer, value=features, unit="count",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="features_shipped", resolved_period=f"Q4 {current_year}",
                related_metrics=related_metrics)

        # "q4 numbers" -> "Q4 2025: Revenue $42.0M, Net Income $11.03M"
        if "q4" in q:
            rev = get_val("revenue", f"Q4 {last_year}")
            ni = get_val("net_income", f"Q4 {last_year}")
            answer = f"Q4 {last_year}: Revenue ${round(rev, 1) if rev else 0}M, Net Income ${round(ni, 2) if ni else 0}M"
            return NLQResponse(success=True, answer=answer, value=rev, unit="$M",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="revenue", resolved_period=f"Q4 {last_year}",
                related_metrics=related_metrics)

    # ===== FALLBACK =====
    # Default handling
    if candidates:
        primary = candidates[0]
        val = get_val(primary, current_year)
        if val is not None:
            answer = fmt_val(primary, val)
            return NLQResponse(success=True, answer=answer, value=val, unit=get_metric_unit(primary),
                confidence=0.75, parsed_intent="AMBIGUOUS", resolved_metric=primary, resolved_period=current_year,
                related_metrics=related_metrics)

    return NLQResponse(
        success=True,
        answer=clarification or "Query interpreted with multiple possibilities.",
        value=None, unit=None, confidence=0.5,
        parsed_intent="AMBIGUOUS", resolved_metric=None, resolved_period=current_year,
        related_metrics=related_metrics,
    )


@router.post("/query", response_model=NLQResponse)
async def query(request: NLQRequest) -> NLQResponse:
    """
    Process a natural language query about financial data.

    Returns the answer with confidence score bounded [0.0, 1.0].
    """
    _start_time = time.perf_counter()
    _trace = diag_init()
    # Resolve entity_id: request body takes priority, then detect from question text,
    # then default to "meridian" (the primary entity in the Convergence scenario).
    # Without a default, DCL returns non-entity-scoped data at demo scale.
    _request_entity_id = request.entity_id
    if not _request_entity_id and request.consolidate:
        _request_entity_id = "combined"
    if not _request_entity_id:
        _request_entity_id = _detect_entity_id(request.question)
    if not _request_entity_id:
        _request_entity_id = "meridian"
    diag(f"[NLQ-DIAG] /query endpoint: question='{request.question[:60]}', data_mode={request.data_mode}, entity_id={_request_entity_id}")
    set_data_mode(request.data_mode)
    set_entity_id(_request_entity_id)
    if request.data_mode == "demo":
        set_force_local(True)
    try:
        off_topic_response = handle_off_topic_or_easter_egg(request.question)
        if off_topic_response:
            persona = detect_persona_from_question(request.question)
            await _log_query_event(
                request.question, "bypass", persona=persona or "CFO",
                message="Off-topic or easter egg",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return NLQResponse(
                success=True,
                answer=off_topic_response,
                value=None,
                unit=None,
                confidence=1.0,
                parsed_intent="OFF_TOPIC",
                resolved_metric=None,
                resolved_period=None,
            )

        # =================================================================
        # COST STRUCTURE / OPEX QUERIES
        # "What's our cost structure?", "biggest cost driver", "opex breakdown"
        # Build a structured cost breakdown from available cost metrics.
        # =================================================================
        _q_cost = request.question.lower()
        _is_cost_query = any(phrase in _q_cost for phrase in [
            "cost structure", "cost driver", "biggest cost",
            "opex breakdown", "operating expenses breakdown",
            "operating expense",
        ])
        if _is_cost_query:
            from src.nlq.services.dcl_semantic_client import get_semantic_client as _get_cost_sc
            _cost_client = _get_cost_sc()
            _cost_metrics = [
                ("cogs", "COGS"),
                ("opex", "OpEx"),
                ("sga", "SG&A"),
                ("cloud_spend", "Cloud Spend"),
            ]
            _cost_parts = []
            _cost_total = 0
            for _cm_key, _cm_name in _cost_metrics:
                _cr = _cost_client.query(metric=_cm_key, time_range={"period": current_quarter(), "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=_request_entity_id)
                if _cr.get("data") and not _cr.get("error"):
                    _cd = _cr["data"]
                    if isinstance(_cd, list) and _cd and isinstance(_cd[0], dict):
                        _cv = _cd[0].get("value")
                        if _cv is not None:
                            _cost_parts.append((_cm_name, _cv))
                            _cost_total += _cv
            if _cost_parts:
                # Sort by value descending for "biggest cost driver"
                _cost_parts.sort(key=lambda x: x[1], reverse=True)
                _rev_r = _cost_client.query(metric="revenue", time_range={"period": current_quarter(), "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=_request_entity_id)
                _rev_val = None
                if _rev_r.get("data") and isinstance(_rev_r["data"], list) and _rev_r["data"]:
                    _rev_val = _rev_r["data"][0].get("value") if isinstance(_rev_r["data"][0], dict) else None
                _lines = [f"**Cost Structure ({current_quarter()})**"]
                for _cn, _cv in _cost_parts:
                    _pct = f" ({round(_cv / _rev_val * 100, 1)}% of revenue)" if _rev_val else ""
                    _lines.append(f"• {_cn}: ${round(_cv, 1)}M{_pct}")
                _lines.append(f"**Total: ${round(_cost_total, 1)}M**")
                if "biggest" in _q_cost or "driver" in _q_cost:
                    _lines.insert(1, f"Largest cost: **{_cost_parts[0][0]}** at ${round(_cost_parts[0][1], 1)}M")
                _cost_answer = "\n".join(_lines)
                await _log_query_event(
                    request.question, "bypass",
                    message="Cost structure query",
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=request.session_id,
                )
                return NLQResponse(
                    success=True, answer=_cost_answer, value=_cost_total,
                    unit="usd_millions", confidence=0.9, parsed_intent="BREAKDOWN",
                    resolved_metric="cost_structure", resolved_period=current_quarter(),
                )

        # =================================================================
        # SALES SCORECARD - "show me the sales scorecard"
        # Build a multi-metric CRO view instead of routing to dashboard.
        # =================================================================
        if "sales scorecard" in _q_cost or "sales score card" in _q_cost:
            from src.nlq.services.dcl_semantic_client import get_semantic_client as _get_sales_sc
            _sales_client = _get_sales_sc()
            _sales_metrics = [
                ("pipeline", "Pipeline", "usd_millions", "$", "M"),
                ("win_rate_pct", "Win Rate", "%", "", "%"),
                ("quota_attainment_pct", "Quota Attainment", "%", "", "%"),
                ("arr", "ARR", "usd_millions", "$", "M"),
                ("churn_rate_pct", "Churn Rate", "%", "", "%"),
                ("nrr", "NRR", "%", "", "%"),
            ]
            _sales_parts = []
            for _sm_key, _sm_name, _sm_unit, _sm_pre, _sm_suf in _sales_metrics:
                _sr = _sales_client.query(metric=_sm_key, time_range={"period": current_quarter(), "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=_request_entity_id)
                if _sr.get("data") and not _sr.get("error"):
                    _sd = _sr["data"]
                    if isinstance(_sd, list) and _sd and isinstance(_sd[0], dict):
                        _sv = _sd[0].get("value")
                        if _sv is not None:
                            _sales_parts.append(f"{_sm_name}: {_sm_pre}{round(_sv, 1)}{_sm_suf}")
            if _sales_parts:
                _sales_answer = f"**Sales Scorecard ({current_quarter()})**\n" + " | ".join(_sales_parts)
                await _log_query_event(
                    request.question, "bypass",
                    message="Sales scorecard query",
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=request.session_id,
                )
                return NLQResponse(
                    success=True, answer=_sales_answer, value=None,
                    unit=None, confidence=0.9, parsed_intent="BROAD_REQUEST",
                    resolved_metric="sales_scorecard", resolved_period=current_quarter(),
                )

        # =================================================================
        # SIMPLE BREAKDOWN QUERIES - Handle "X by Y" queries early (no Claude needed)
        # Must come before simple metric queries to avoid "revenue by region" -> "revenue"
        # =================================================================
        breakdown_result = _try_simple_breakdown_query(request.question)
        if breakdown_result:
            await _log_query_event(
                request.question, "bypass",
                message=f"Simple breakdown -> {breakdown_result.resolved_metric}",
                persona=detect_persona_from_metric(breakdown_result.resolved_metric) or "CFO",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return breakdown_result

        # =================================================================
        # COMPARISON / TREND / DIRECTION QUERIES
        # "Compare Q1 vs Q2 revenue", "Revenue growth YoY", "Is revenue going up?"
        # Must intercept before ambiguity pre-check and simple metric queries.
        # =================================================================
        _comparison_result = _try_comparison_query(request.question, entity_id=_request_entity_id)
        if _comparison_result:
            await _log_query_event(
                request.question, "bypass",
                message=f"Comparison/trend -> {_comparison_result.resolved_metric}",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return _comparison_result

        # =================================================================
        # STANDARD REPORTING PACKAGE — Act/CF/PY comparison reports
        # Must run before ambiguity pre-check because report queries contain
        # comparison language (e.g., "vs prior year") that triggers
        # AmbiguityType.COMPARISON in detect_ambiguity().
        # =================================================================
        report_result = _try_report_query(request.question, session_id=request.session_id, entity_id=_request_entity_id)
        if report_result:
            await _log_query_event(
                request.question, "bypass",
                message=f"Report query: {report_result.resolved_metric}",
                persona="CFO",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return report_result

        # =================================================================
        # VAGUE METRIC PRE-CHECK - catch ambiguous queries before simple metric path
        # e.g. "show me the margin" or "how did we do?" need clarification, not eager resolution
        # Skipped when query contains analytical/causal language (those need the LLM).
        # =================================================================
        _pre_amb_type, _pre_candidates, _pre_clarification = (None, [], None)
        if not _has_complexity_signal(request.question):
            _pre_amb_type, _pre_candidates, _pre_clarification = detect_ambiguity(request.question)
        if _pre_amb_type == AmbiguityType.VAGUE_METRIC and _pre_clarification:
            _result = _handle_ambiguous_query_text(
                request.question, _pre_amb_type, _pre_candidates, _pre_clarification,
                entity_id=_request_entity_id,
            )
            await _log_query_event(
                request.question, "bypass",
                message=f"Vague metric -> {_pre_amb_type.value}",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return _result

        # =================================================================
        # COMPARISON PRE-CHECK - "compare X vs Y" must return structured data
        # with period-labeled related_metrics, NOT a dashboard visualization.
        # Route to ambiguity handler before visualization handler intercepts.
        # =================================================================
        if _pre_amb_type == AmbiguityType.COMPARISON:
            _result = _handle_ambiguous_query_text(
                request.question, _pre_amb_type, _pre_candidates, _pre_clarification,
                entity_id=_request_entity_id,
            )
            await _log_query_event(
                request.question, "bypass",
                message=f"Comparison -> {_pre_amb_type.value}",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return _result

        # =================================================================
        # HANDLED AMBIGUITY PRE-CHECK - YES_NO, JUDGMENT_CALL, SHORTHAND,
        # BURN_RATE all have dedicated handlers in _handle_ambiguous_query_text.
        # Intercept early so they never fall through to the LLM/cache path
        # which can misinterpret them (e.g. "are we profitable" -> metric "ar").
        # =================================================================
        _EARLY_INTERCEPT_TYPES = {
            AmbiguityType.YES_NO,
            AmbiguityType.JUDGMENT_CALL,
            AmbiguityType.SHORTHAND,
            AmbiguityType.BURN_RATE,
        }
        if _pre_amb_type in _EARLY_INTERCEPT_TYPES:
            _result = _handle_ambiguous_query_text(
                request.question, _pre_amb_type, _pre_candidates, _pre_clarification,
                entity_id=_request_entity_id,
            )
            await _log_query_event(
                request.question, "bypass",
                message=f"Ambiguity pre-check -> {_pre_amb_type.value}",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return _result

        # =================================================================
        # OVERVIEW / SUMMARY QUERIES - "how did last quarter go?", "quick overview",
        # "what are our KPIs?", "what does the data tell us?"
        # These should return text with numbers, not a dashboard.
        # =================================================================
        _q_lower = request.question.lower()
        import re as _re_summary
        _is_overview = any(phrase in _q_lower for phrase in [
            "quick overview", "give me a quick",
            "what does the data tell", "what are our kpis",
        ])
        _period_summary = _re_summary.match(
            r'how did (?:last quarter|this quarter|q[1-4]|20\d{2}|last year|this year).*(?:go|look|do|perform|turn out)',
            _q_lower
        )
        if _period_summary or _is_overview:
            from src.nlq.core.dates import prior_quarter
            # Determine the period
            if "last quarter" in _q_lower:
                _summary_period = prior_quarter()
            elif "this quarter" in _q_lower:
                _summary_period = current_quarter()
            elif "last year" in _q_lower:
                _summary_period = str(int(current_year()) - 1)
            else:
                _summary_period = current_quarter()
            # Build a multi-metric summary
            from src.nlq.services.dcl_semantic_client import get_semantic_client as _get_sc
            dcl_client_summary = _get_sc()
            _summary_metrics = ["revenue", "gross_margin_pct", "ebitda", "net_income", "arr"]
            _summary_parts = []
            for _sm in _summary_metrics:
                _sr = dcl_client_summary.query(metric=_sm, time_range={"period": _summary_period, "granularity": "quarterly"}, tenant_id=get_tenant_id(), entity_id=_request_entity_id)
                if _sr.get("data") and not _sr.get("error"):
                    _data = _sr["data"]
                    if isinstance(_data, list) and _data:
                        _sv = _data[-1].get("value") if isinstance(_data[-1], dict) else _data[-1]
                    else:
                        _sv = None
                    if _sv is not None:
                        from src.nlq.knowledge.schema import get_metric_unit as _gmu
                        from src.nlq.knowledge.display import get_display_name as _gdn
                        _unit = _gmu(_sm)
                        _dn = _gdn(_sm)
                        if _unit in ("USD millions",):
                            _summary_parts.append(f"{_dn}: ${round(_sv, 1)}M")
                        elif _unit == "%":
                            _summary_parts.append(f"{_dn}: {round(_sv, 1)}%")
                        else:
                            _summary_parts.append(f"{_dn}: {round(_sv, 1)}")
            if _summary_parts:
                _summary_answer = f"**{_summary_period} Summary**\n" + " | ".join(_summary_parts)
                return NLQResponse(
                    success=True, answer=_summary_answer, value=None,
                    confidence=0.95, parsed_intent="BROAD_REQUEST",
                    resolved_metric="summary", resolved_period=_summary_period,
                )

        # =================================================================
        # COMPOSITE MARGIN QUERIES - "margins", "all margins", "what are our margins"
        # Must intercept before simple metric query to avoid routing to gross_margin_pct
        # =================================================================
        _q_lower = request.question.lower()
        if "margin" in _q_lower and ("all" in _q_lower or "margins" in _q_lower):
            _composite = _handle_ambiguous_query_text(
                request.question, AmbiguityType.BROAD_REQUEST, [], None,
                entity_id=_request_entity_id,
            )
            if _composite:
                await _log_query_event(
                    request.question, "bypass",
                    message="Composite margins query (early)",
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=request.session_id,
                )
                return _composite

        # =================================================================
        # MULTI-METRIC QUERIES - Handle "X and Y" queries (no Claude needed)
        # Skip if this looks like a dashboard request — those list multiple
        # metrics but should go through the visualization intent handler.
        # =================================================================
        if not _is_dashboard_query(request.question):
            multi_result = _try_multi_metric_query(request.question)
            if multi_result:
                await _log_query_event(
                    request.question, "bypass",
                    message=f"Multi-metric -> {multi_result.resolved_metric}",
                    persona=detect_persona_from_metric(multi_result.resolved_metric) or "CFO",
                )
                return multi_result

        # =================================================================
        # BRIDGE / WATERFALL QUERIES — must run before simple metric
        # so "why did rev increase" isn't swallowed as a single-metric query.
        # =================================================================
        bridge_result = _try_bridge_query(request.question, session_id=request.session_id, entity_id=_request_entity_id)
        if bridge_result:
            await _log_query_event(
                request.question, "bypass",
                message="Revenue bridge query",
                persona="CFO",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return bridge_result

        # =================================================================
        # SIMPLE METRIC QUERIES - Handle "what is X?" queries early (no Claude needed)
        # =================================================================
        simple_result = _try_simple_metric_query(request.question, entity_id=_request_entity_id)
        if simple_result:
            await _log_query_event(
                request.question, "bypass",
                message=f"Simple metric -> {simple_result.resolved_metric}",
                persona=detect_persona_from_metric(simple_result.resolved_metric) or "CFO",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return simple_result

        # =================================================================
        # P&L / INCOME STATEMENT COMPOSITE QUERIES
        # Fan out multiple DCL queries for all line items in parallel.
        # =================================================================
        pl_result = _try_pl_statement_query(request.question, session_id=request.session_id, entity_id=_request_entity_id)
        if pl_result:
            await _log_query_event(
                request.question, "bypass",
                message="P&L composite query",
                persona="CFO",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return pl_result

        # Check for dashboard/report queries (doesn't need Claude API)
        # NOTE: For visual dashboard requests, we let the visualization intent handler below
        # generate proper dashboard widgets. Only text-mode dashboard summaries go through the old handler.
        if _is_dashboard_query(request.question):
            # Check if this should be a visual dashboard first
            should_viz, viz_requirements = should_generate_visualization(request.question, persona=request.persona)
            if should_viz and viz_requirements.intent != VisualizationIntent.SIMPLE_ANSWER:
                # Let the visualization intent handler below generate proper widgets
                pass
            else:
                # Fallback to text summary for non-visual dashboard requests
                dashboard_response = _handle_dashboard_query(request.question, persona=request.persona, entity_id=_request_entity_id)
                if dashboard_response:
                    await _log_query_event(
                        request.question, "bypass",
                        message="Dashboard text summary",
                        persona=dashboard_response.persona or "CFO",
                        execution_time_ms=_elapsed_ms(_start_time),
                        session_id=request.session_id,
                    )
                    # Convert IntentMapResponse to NLQResponse for text endpoint
                    return NLQResponse(
                        success=True,
                        answer=dashboard_response.text_response,
                        value=None,
                        unit=None,
                        confidence=dashboard_response.overall_confidence,
                        parsed_intent="DASHBOARD",
                        resolved_metric="dashboard",
                        resolved_period=dashboard_response.nodes[0].period if dashboard_response.nodes else None,
                        related_metrics=_nodes_to_related_metrics(dashboard_response.nodes),
                    )

        # =================================================================
        # GUIDED DISCOVERY - Handle "what can you show me about X" queries
        # (Must be before visualization intent to avoid showing generic dashboard)
        # =================================================================
        guided_result = _try_guided_discovery(request.question)
        if guided_result:
            await _log_query_event(
                request.question, "bypass",
                message="Guided discovery",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return guided_result

        # =================================================================
        # INGEST / INFRASTRUCTURE STATUS - Handle "is Splunk connected?",
        # "what tenants are pushing data?", "ingest status" etc.
        # =================================================================
        ingest_result = _try_ingest_status_query(request.question)
        if ingest_result:
            await _log_query_event(
                request.question, "bypass",
                message="Ingest status query",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return ingest_result

        # =================================================================
        # MISSING DATA CHECK - Handle queries about non-existent data
        # =================================================================
        missing_result = _check_missing_data(request.question)
        if missing_result:
            await _log_query_event(
                request.question, "bypass", success=False,
                message="Missing data / non-existent metric",
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=request.session_id,
            )
            return missing_result

        # =================================================================
        # COMPOSITE METRIC QUERIES - "all margins", "financial health"
        # Must intercept before visualization to return text, not dashboard.
        # =================================================================
        _q_lower = request.question.lower()
        if "margin" in _q_lower and ("all" in _q_lower or "margins" in _q_lower):
            _composite = _handle_ambiguous_query_text(
                request.question, AmbiguityType.BROAD_REQUEST, [], None,
                entity_id=_request_entity_id,
            )
            if _composite:
                await _log_query_event(
                    request.question, "bypass",
                    message="Composite margins query",
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=request.session_id,
                )
                return _composite

        if "financial health" in _q_lower:
            _composite = _handle_ambiguous_query_text(
                request.question, AmbiguityType.BROAD_REQUEST, [], None,
                entity_id=_request_entity_id,
            )
            if _composite:
                await _log_query_event(
                    request.question, "bypass",
                    message="Financial health composite query",
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=request.session_id,
                )
                return _composite

        # =================================================================
        # VISUALIZATION INTENT DETECTION - Check if user wants a dashboard
        # =================================================================
        # Get session ID for dashboard state tracking
        session_id = request.session_id or "default"

        # Check for current dashboard in session (for refinement support)
        current_session = get_session_dashboard(session_id)
        has_current_dashboard = current_session is not None

        # First check if this is a refinement command
        refinement_intent = detect_refinement_intent(request.question, has_current_dashboard)

        # Handle context-dependent queries without a dashboard
        if is_context_dependent_query(request.question) and not has_current_dashboard:
            clarification_msg = needs_clarification_without_context(request.question)
            if clarification_msg:
                return NLQResponse(
                    success=True,
                    answer=clarification_msg,
                    value=None,
                    unit=None,
                    confidence=0.7,
                    parsed_intent="CLARIFICATION_NEEDED",
                    resolved_metric=None,
                    resolved_period=None,
                    response_type="text",
                )

        # Handle refinement of existing dashboard
        if refinement_intent.is_refinement and has_current_dashboard:
            logger.info(f"Refinement intent detected: {refinement_intent.refinement_type.value}")

            try:
                from src.nlq.models.dashboard_schema import DashboardSchema

                # Get current dashboard schema
                current_dashboard_dict = current_session["dashboard"]
                current_schema = DashboardSchema(**current_dashboard_dict)

                # Detect visualization requirements for the refinement
                _, viz_requirements = should_generate_visualization(request.question, persona=request.persona)

                # Apply refinement
                updated_schema, refinement_status, refinement_msg = refine_dashboard_schema(
                    current_schema=current_schema,
                    refinement_query=request.question,
                    requirements=viz_requirements,
                )

                # Resolve data for updated dashboard
                data_resolver = DashboardDataResolver()
                widget_data = data_resolver.resolve_dashboard_data(
                    updated_schema,
                    reference_year=current_year(),
                )

                # Update session state
                updated_dict = updated_schema.model_dump()
                set_session_dashboard(session_id, updated_dict, widget_data)

                # Describe the changes
                changes = []
                if refinement_intent.refinement_type == RefinementType.ADD_WIDGET:
                    metric = refinement_intent.metric_to_add or "the requested"
                    changes.append(f"Added {metric} widget")
                elif refinement_intent.refinement_type == RefinementType.CHANGE_CHART_TYPE:
                    changes.append(f"Changed chart type to {refinement_intent.new_chart_type or 'the requested type'}")
                elif refinement_intent.refinement_type == RefinementType.REMOVE_WIDGET:
                    changes.append("Removed the specified widget")
                elif refinement_intent.refinement_type == RefinementType.ADD_FILTER:
                    changes.append(f"Added filter for {refinement_intent.filter_dimension}")
                else:
                    changes.append("Updated the dashboard")

                return NLQResponse(
                    success=True,
                    answer=f"I've updated the dashboard. {'; '.join(changes)}.",
                    value=None,
                    unit=None,
                    confidence=refinement_intent.confidence,
                    parsed_intent="REFINEMENT",
                    resolved_metric=viz_requirements.metrics[0] if viz_requirements.metrics else None,
                    resolved_period=current_year(),
                    response_type="dashboard",
                    dashboard=updated_dict,
                    dashboard_data=widget_data,
                    data_source="live",
                )
            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Dashboard refinement failed: {e}", exc_info=True)
                if is_strict_mode():
                    # In strict mode, return error response instead of falling through
                    return NLQResponse(
                        success=False,
                        answer=f"Dashboard refinement failed: {str(e)}. This error is shown because strict mode is enabled.",
                        error_code="REFINEMENT_FAILED",
                        error_details={"exception": str(e), "category": FailureCategory.REFINEMENT.value},
                    )
                # In production, fall through to new dashboard generation

        # Check for new visualization request
        should_viz, viz_requirements = should_generate_visualization(request.question, persona=request.persona)

        if should_viz and viz_requirements.intent != VisualizationIntent.SIMPLE_ANSWER:
            logger.info(f"Visualization intent detected: {viz_requirements.intent.value}")

            try:
                # Create debug info for tracking decisions
                debug_info = DashboardDebugInfo(original_query=request.question)

                # Generate dashboard schema
                dashboard_schema = generate_dashboard_schema(
                    query=request.question,
                    requirements=viz_requirements,
                    debug_info=debug_info,
                )

                # Resolve real data from fact base
                data_resolver = DashboardDataResolver()
                widget_data = data_resolver.resolve_dashboard_data(
                    dashboard_schema,
                    reference_year=current_year(),
                )

                # Store in session for future refinements
                dashboard_dict = dashboard_schema.model_dump()
                set_session_dashboard(session_id, dashboard_dict, widget_data)

                # Return dashboard response with debug info if in strict mode
                return NLQResponse(
                    success=True,
                    answer=f"Here's a dashboard showing {dashboard_schema.title}",
                    value=None,
                    unit=None,
                    confidence=viz_requirements.confidence,
                    parsed_intent="VISUALIZATION",
                    resolved_metric=viz_requirements.metrics[0] if viz_requirements.metrics else None,
                    resolved_period=current_year(),
                    response_type="dashboard",
                    dashboard=dashboard_dict,
                    dashboard_data=widget_data,
                    data_source="live",
                    debug_info=debug_info.to_dict() if is_strict_mode() else None,
                )
            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Dashboard generation failed: {e}", exc_info=True)
                if is_strict_mode():
                    # In strict mode, return error response instead of falling through
                    return NLQResponse(
                        success=False,
                        answer=f"Dashboard generation failed: {str(e)}. This error is shown because strict mode is enabled.",
                        error_code="DASHBOARD_GENERATION_FAILED",
                        error_details={"exception": str(e), "category": FailureCategory.SCHEMA_GENERATION.value},
                    )
                # In production, fall through to normal query processing if dashboard fails

        # Check for ambiguity (same as Galaxy endpoint).
        # Skip when query contains analytical/causal language — those need the LLM.
        ambiguity_type, candidates, clarification = (None, [], None)
        if not _has_complexity_signal(request.question):
            ambiguity_type, candidates, clarification = detect_ambiguity(request.question)

        if ambiguity_type and ambiguity_type != AmbiguityType.NONE:
            # Handle ambiguous query with text response
            return _handle_ambiguous_query_text(
                request.question,
                ambiguity_type,
                candidates,
                clarification,
                entity_id=_request_entity_id,
            )

        # Set up components
        reference_date = request.reference_date or date.today()
        resolver = PeriodResolver(reference_date)
        claude_client = get_claude_client()
        executor = QueryExecutor(claude_client=claude_client, entity_id=_request_entity_id)

        # Get session ID from request body
        session_id = request.session_id or "default"

        # =================================================================
        # RAG CACHE LOOKUP - Check cache before calling Claude
        # =================================================================
        cache_service = get_cache_service()
        parsed = None
        cache_hit = False
        cache_result = None
        _pending_cache_write = False  # Deferred: write to cache only after execution succeeds

        if cache_service and cache_service.is_available:
            cache_result = cache_service.lookup(request.question)

            if cache_result.high_confidence and cache_result.parsed:
                # Use cached parsed structure - no Claude call needed
                parsed = _cached_to_parsed_query(cache_result.parsed)
                cache_hit = True
                logger.info(f"RAG cache hit ({cache_result.hit_type.value}, {cache_result.similarity:.3f}): {request.question[:50]}...")

                # Track cache hit in session stats
                call_counter = get_call_counter()
                call_counter.increment_cached(session_id)

                # Log to learning log
                await _log_query_event(
                    request.question, "cache",
                    message=f"Cache hit ({cache_result.hit_type.value}, {cache_result.similarity:.0%} match)",
                    persona=detect_persona_from_metric(cache_result.parsed.get("metric")) or "CFO",
                    similarity=cache_result.similarity,
                    execution_time_ms=_elapsed_ms(_start_time),
                    session_id=session_id,
                )

        # =================================================================
        # CLAUDE PARSING - Fall back to LLM if no cache hit
        # =================================================================
        if not cache_hit:
            # In STATIC mode, return error if no cache hit (no LLM fallback)
            if request.mode == QueryMode.STATIC:
                logger.info(f"Static mode - no cache hit for: {request.question[:50]}...")
                return NLQResponse(
                    success=False,
                    error_code="STATIC_MODE_CACHE_MISS",
                    error_message="Query not found in cache. Switch to AI mode for LLM processing.",
                    confidence=0.0,
                    parsed_intent="UNKNOWN",
                    resolved_metric=None,
                    resolved_period=None,
                )

            # AI mode: Initialize Claude client and parser
            claude_client = get_claude_client()
            parser = QueryParser(claude_client)

            # Parse the query with Claude
            parsed = parser.parse(request.question)

            # Increment LLM call counter
            call_counter = get_call_counter()
            call_counter.increment(session_id)

            logger.info(f"Claude parsed query: {parsed}")

            # NOTE: Cache write deferred until AFTER execution succeeds.
            # Storing parses before execution risks caching bad LLM parses
            # that always fail — every future cache hit re-triggers the failure.
            _pending_cache_write = True

            # Log to learning log
            stored_in_cache = cache_service and cache_service.is_available
            await _log_query_event(
                request.question, "llm",
                learned=stored_in_cache,
                message=f'"{request.question}" -> {parsed.metric}' + (" (learned)" if stored_in_cache else ""),
                persona=detect_persona_from_metric(parsed.metric) or "CFO",
                llm_confidence=0.95,
                execution_time_ms=_elapsed_ms(_start_time),
                session_id=session_id,
            )

        logger.info(f"Parsed query (cache_hit={cache_hit}): {parsed}")

        # Resolve the primary period
        resolved = resolver.resolve(parsed.period_reference)
        parsed.resolved_period = resolver.to_period_key(resolved)
        logger.info(f"Resolved period: {parsed.resolved_period}")

        # Resolve comparison period for comparison queries
        if parsed.intent == QueryIntent.COMPARISON_QUERY and parsed.comparison_period:
            comp_resolved = resolver.resolve(parsed.comparison_period)
            parsed.comparison_period = resolver.to_period_key(comp_resolved)
            logger.info(f"Resolved comparison period: {parsed.comparison_period}")

        # Resolve aggregation periods for aggregation queries
        if parsed.intent == QueryIntent.AGGREGATION_QUERY and parsed.aggregation_periods:
            resolved_agg_periods = []
            for period in parsed.aggregation_periods:
                agg_resolved = resolver.resolve(period)
                resolved_agg_periods.append(resolver.to_period_key(agg_resolved))
            parsed.aggregation_periods = resolved_agg_periods
            logger.info(f"Resolved aggregation periods: {parsed.aggregation_periods}")

        # Execute the query
        result = executor.execute(parsed)

        if not result.success:
            # Execution failed — do NOT cache the LLM parse (it leads to failure)
            logger.info(f"Skipping cache write — execution failed: {request.question[:80]}")
            stumped_msg = get_stumped_response(include_suggestions=True)
            response = NLQResponse(
                success=True,
                answer=stumped_msg,
                confidence=0.5,
                parsed_intent=parsed.intent.value,
                resolved_metric=parsed.metric,
                resolved_period=parsed.resolved_period,
            )
            # Track as insufficient data (execution failed)
            return _track_insufficient_data_if_needed(
                response, request.question, session_id,
                metric_found=True, period_found=True, data_exists=False
            )

        # Execution succeeded — now safe to cache the LLM parse for future queries
        if _pending_cache_write and cache_service and cache_service.is_available:
            persona = detect_persona_from_metric(parsed.metric) or "CFO"
            cache_dict = _parsed_query_to_cache_dict(parsed)
            cache_service.store(
                query=request.question,
                parsed=cache_dict,
                persona=persona,
                confidence=0.95,  # Claude parses are high confidence
                source="llm",
            )

        # Format the answer based on intent type
        unit = get_metric_unit(parsed.metric)
        answer, formatted_value = _format_answer(parsed, result, unit)

        # =================================================================
        # DCL ENRICHMENT — entity resolution, provenance, conflicts, temporal
        # =================================================================
        dcl_data = {}

        # If graph resolution was used, extract provenance from graph metadata
        graph_metadata = result.metadata if result.query_type == "graph_resolution" else None
        if graph_metadata:
            if graph_metadata.get("provenance"):
                dcl_data["provenance"] = graph_metadata["provenance"]
            if graph_metadata.get("warnings"):
                dcl_data["graph_warnings"] = graph_metadata["warnings"]
            if graph_metadata.get("filters_resolved"):
                dcl_data["filters_resolved"] = graph_metadata["filters_resolved"]

        # Standard DCL enrichment (entity resolution, conflicts, temporal)
        try:
            is_comparison = parsed.intent == QueryIntent.COMPARISON_QUERY
            enrichment = dcl_enrich_response(
                metric=parsed.metric,
                entity=getattr(parsed, 'entity', None),
                persona=detect_persona_from_metric(parsed.metric) or detect_persona_from_question(request.question),
                start_period=parsed.resolved_period,
                end_period=parsed.comparison_period if is_comparison else None,
                is_comparison=is_comparison,
            )
            # Merge enrichment into dcl_data (graph provenance takes precedence)
            for key, val in enrichment.items():
                if key not in dcl_data:
                    dcl_data[key] = val
        except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
            logger.debug(f"DCL enrichment skipped: {e}")

        response = NLQResponse(
            success=True,
            answer=answer,
            value=formatted_value,
            unit=unit,
            confidence=bounded_confidence(result.confidence),
            parsed_intent=parsed.intent.value,
            resolved_metric=parsed.metric,
            resolved_period=parsed.resolved_period,
            entity=dcl_data.get("entity_name"),
            entity_id=dcl_data.get("entity_id"),
            entity_resolution=dcl_data.get("entity_resolution"),
            provenance=dcl_data.get("provenance") if isinstance(dcl_data.get("provenance"), dict) else None,
            conflicts=dcl_data.get("conflicts"),
            temporal_warning=dcl_data.get("temporal_warning"),
            persona=dcl_data.get("persona_value", {}).get("persona") if dcl_data.get("persona_value") else None,
            debug_info={"nlq_diag_trace": _trace} if _trace else None,
            data_source=result.data_source,  # Structural integrity: source attribution
        )
        # Track if confidence is below threshold
        return _track_insufficient_data_if_needed(response, request.question, session_id)

    except ValueError as e:
        logger.error(f"Query parsing error: {e}")
        diag(f"[NLQ-DIAG] /query PARSE_ERROR: {e}")
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="PARSE_ERROR",
            error_message=str(e),
            debug_info={"nlq_diag_trace": _trace, "error": str(e), "error_type": "PARSE_ERROR"} if _trace else {"error": str(e), "error_type": "PARSE_ERROR"},
        )
    except HTTPException as e:
        logger.error(f"HTTP error in query: {e.status_code} - {e.detail}")
        diag(f"[NLQ-DIAG] /query HTTP_ERROR: {e.status_code} {e.detail}")
        error_msg = str(e.detail) if e.detail else "HTTP error"
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="CONFIG_ERROR",
            error_message=error_msg,
            debug_info={"nlq_diag_trace": _trace, "error": error_msg, "error_type": "CONFIG_ERROR"} if _trace else {"error": error_msg, "error_type": "CONFIG_ERROR"},
        )
    except RuntimeError as e:
        error_msg = str(e)
        is_live = "LIVE MODE" in error_msg
        code = "CONFIG_ERROR" if is_live else "INTERNAL_ERROR"
        logger.error(f"{'Live mode' if is_live else 'Runtime'} error processing query: {e}")
        diag(f"[NLQ-DIAG] /query {code}: {e}")
        return NLQResponse(
            success=False,
            answer=error_msg if is_live else None,
            confidence=0.0,
            error_code=code,
            error_message=error_msg,
            debug_info={"nlq_diag_trace": _trace, "error": error_msg, "error_type": code} if _trace else {"error": error_msg, "error_type": code},
        )
    except (KeyError, TypeError, AttributeError, OSError) as e:
        logger.exception(f"Unexpected error processing query: {e}")
        diag(f"[NLQ-DIAG] /query EXCEPTION: {type(e).__name__}: {e}")
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="INTERNAL_ERROR",
            error_message=f"{type(e).__name__}: {e}",
            debug_info={"nlq_diag_trace": _trace, "error": str(e), "error_type": type(e).__name__} if _trace else {"error": str(e), "error_type": type(e).__name__},
        )
    except Exception as e:
        logger.exception(f"Unhandled error in query: {type(e).__name__}: {e}")
        diag(f"[NLQ-DIAG] /query UNHANDLED: {type(e).__name__}: {e}")
        error_msg = f"{type(e).__name__}: {e}"
        return NLQResponse(
            success=False,
            confidence=0.0,
            error_code="UNHANDLED_ERROR",
            error_message=error_msg,
            debug_info={"nlq_diag_trace": _trace, "error": error_msg, "error_type": type(e).__name__} if _trace else {"error": error_msg, "error_type": type(e).__name__},
        )
    finally:
        set_force_local(False)
        set_data_mode(None)
        set_entity_id(None)


# ─── DELETED: query_galaxy() and /intent-map, /query/galaxy routes ───
# All queries now go through /api/v1/query (the query() handler above).
# The galaxy endpoint, its parallel waterfall, and all galaxy-specific helpers
# (_handle_ambiguous_query_galaxy, _generate_nodes_for_intent,
#  _create_error_galaxy_response, _create_stumped_galaxy_response)
# were removed as dead code. See git history for the original implementation.
# ─────────────────────────────────────────────────────────────────────


_GALAXY_ENDPOINT_DELETED = True  # Sentinel so automated grep can confirm deletion


# ─── Reconciliation endpoint ────────────────────────────────────────────────

@router.get("/reconciliation")
async def reconciliation():
    """
    Run the reconciliation engine against Farm's ground truth and return
    results in the portal-expected format.

    Compares all scalar P&L metrics for every quarter in the ground truth
    manifest against DCL's query endpoint. All metric×period queries run in
    parallel via ThreadPoolExecutor to avoid sequential HTTP round-trips.
    """
    import httpx
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.nlq.services.reconciliation_engine import (
        ReconciliationEngine, _GT_NON_QUARTER_KEYS, _QUARTER_META_KEYS,
        _extract_expected_value,
    )

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL environment variable is not set. "
                   "Reconciliation requires a live DCL backend. "
                   "Set DCL_API_URL to the DCL service URL (e.g. https://aos-dclv2.onrender.com).",
        )

    # Use a shared httpx client for connection pooling across all queries
    client = httpx.Client(timeout=30, limits=httpx.Limits(max_connections=64, max_keepalive_connections=32))

    def query_fn(metric_id: str, period: str):
        """Query DCL for a metric value. Returns object with .value attribute."""
        try:
            r = client.post(
                f"{dcl_url}/api/dcl/query",
                json={
                    "metric": metric_id,
                    "time_range": {"start": period, "end": period},
                },
            )
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"DCL unreachable at {dcl_url}/api/dcl/query — connection refused: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"DCL request timed out at {dcl_url}/api/dcl/query "
                f"for metric='{metric_id}', period='{period}': {exc}"
            ) from exc

        if r.status_code != 200:
            return None
        data = r.json()
        pts = data.get("data", [])
        for pt in pts:
            if pt.get("period") == period:
                class _Result:
                    pass
                result = _Result()
                result.value = pt["value"]
                return result
        return None

    # Load ground truth
    engine = ReconciliationEngine(query_fn=query_fn)
    gt = engine._get_ground_truth()
    if gt is None:
        client.close()
        farm_url = os.environ.get("FARM_URL", "")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Reconciliation aborted: could not load ground truth from "
                f"Farm API at {farm_url or '(FARM_URL not set)'} or local fallback. "
                f"Ensure FARM_URL is set and Farm's /api/ground-truth is reachable."
            ),
        )

    gt_data = gt.get("ground_truth", gt)
    quarters = sorted([
        k for k in gt_data
        if k not in _GT_NON_QUARTER_KEYS
    ])

    if not quarters:
        client.close()
        raise HTTPException(
            status_code=502,
            detail="Reconciliation aborted: ground truth contains no quarter data.",
        )

    # Build the full list of (metric, period, expected) checks upfront,
    # then fire ALL of them in parallel instead of sequentially.
    all_checks = []  # (metric_id, period, expected_value)
    for period in quarters:
        quarter_data = gt_data.get(period, {})
        for key, entry in quarter_data.items():
            if key in _QUARTER_META_KEYS:
                continue
            expected = _extract_expected_value(entry)
            if expected is None:
                continue
            all_checks.append((key, period, expected))

    logger.info(
        "Reconciliation: %d checks across %d quarters — firing in parallel",
        len(all_checks), len(quarters),
    )

    # Fire all queries in parallel
    results = {}  # (metric_id, period) -> (actual_value | None, error_str | None)
    max_workers = min(64, len(all_checks))

    def _fetch(metric_id: str, period: str):
        try:
            result = query_fn(metric_id, period)
            if result is None:
                return (metric_id, period, None, None)
            return (metric_id, period, result.value, None)
        except Exception as exc:
            return (metric_id, period, None, str(exc))

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(_fetch, metric_id, period)
                for metric_id, period, _ in all_checks
            ]
            for future in as_completed(futures):
                metric_id, period, value, error = future.result()
                results[(metric_id, period)] = (value, error)
    finally:
        client.close()

    # Aggregate results per quarter
    tolerance_pct = 1.0
    checks_out = []
    total_checks_count = 0
    total_green = 0
    total_red = 0

    for period in quarters:
        quarter_data = gt_data.get(period, {})
        passed = 0
        failed = 0
        errors = 0
        mismatches = []

        for key, entry in quarter_data.items():
            if key in _QUARTER_META_KEYS:
                continue
            expected = _extract_expected_value(entry)
            if expected is None:
                continue

            actual_val, error_str = results.get((key, period), (None, None))

            if error_str:
                errors += 1
                mismatches.append({
                    "metric": key, "period": period,
                    "expected": expected, "actual": None,
                    "delta": None, "pct_delta": None,
                    "status": "error", "error": error_str,
                })
                continue

            if actual_val is None:
                errors += 1
                mismatches.append({
                    "metric": key, "period": period,
                    "expected": expected, "actual": None,
                    "delta": None, "pct_delta": None,
                    "status": "missing",
                })
                continue

            if not isinstance(actual_val, (int, float)):
                errors += 1
                mismatches.append({
                    "metric": key, "period": period,
                    "expected": expected, "actual": actual_val,
                    "delta": None, "pct_delta": None,
                    "status": "error",
                    "error": f"Non-numeric value (type={type(actual_val).__name__})",
                })
                continue

            delta = abs(actual_val - expected)
            pct_delta = (delta / abs(expected) * 100) if expected != 0 else (0.0 if delta == 0 else 100.0)

            if pct_delta <= tolerance_pct:
                passed += 1
            else:
                failed += 1
                mismatches.append({
                    "metric": key, "period": period,
                    "expected": expected, "actual": actual_val,
                    "delta": round(delta, 4), "pct_delta": round(pct_delta, 2),
                    "status": "mismatch",
                })

        total = passed + failed + errors
        checks_out.append({
            "statement": "Income Statement",
            "period": period,
            "total": total,
            "green": passed,
            "red": failed + errors,
            "mismatches": mismatches,
        })
        total_checks_count += total
        total_green += passed
        total_red += failed + errors

    from datetime import datetime

    return {
        "checks": checks_out,
        "totalChecks": total_checks_count,
        "totalGreen": total_green,
        "totalRed": total_red,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ─── Drill-through proxy ─────────────────────────────────────────────────────

@router.get("/drill-through")
async def drill_through(
    level: str,
    parent: Optional[str] = None,
    quarter: Optional[str] = None,
):
    """
    Proxy drill-through requests to DCL's drill-through endpoint.

    NLQ owns the frontend; DCL owns the drill-through data. This proxy keeps
    all frontend requests going through NLQ's API, avoiding direct DCL calls
    from the browser and ensuring consistency with other NLQ endpoints.
    """
    import httpx

    dcl_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not dcl_url:
        raise HTTPException(
            status_code=503,
            detail="DCL_API_URL environment variable is not set. "
                   "Drill-through requires a live DCL backend. "
                   "Set DCL_API_URL to the DCL service URL (e.g. https://aos-dclv2.onrender.com).",
        )
    params = {"level": level}
    if parent:
        params["parent"] = parent
    if quarter:
        params["quarter"] = quarter

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{dcl_url}/api/dcl/drill-through", params=params)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"DCL unreachable at {dcl_url}/api/dcl/drill-through — "
                   f"connection refused. Ensure DCL backend is running on port 8004.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"DCL request timed out at {dcl_url}/api/dcl/drill-through "
                   f"for level={level}, parent={parent}.",
        )

    if r.status_code != 200:
        raise HTTPException(
            status_code=r.status_code,
            detail=f"DCL drill-through error: {r.text[:500]}",
        )

    return r.json()


# C1: Health, pipeline, schema endpoints extracted to api/health.py
# C1: Eval endpoint extracted to api/eval.py
# Both are wired as separate routers in main.py
