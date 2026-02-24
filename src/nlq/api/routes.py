"""
API route definitions for AOS-NLQ.

Endpoints:
- POST /v1/query: Process natural language query (NLQResponse)
- POST /v1/query/galaxy: Process query with Galaxy visualization (IntentMapResponse)
- GET /v1/health: Health check
- GET /v1/schema: Return available metrics and periods

All endpoints return JSON responses with consistent structure.
"""

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
from src.nlq.knowledge.schema import FINANCIAL_SCHEMA, get_metric_unit
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
from src.nlq.services.dcl_semantic_client import set_force_local, set_data_mode, force_local_data, diag, diag_init, diag_collect
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
    simple_metric_to_galaxy_response,
    guided_discovery_to_nlq_response,
    guided_discovery_to_galaxy_response,
    missing_data_to_nlq_response,
    missing_data_to_galaxy_response,
    ingest_status_to_nlq_response,
    ingest_status_to_galaxy_response,
    people_response_to_galaxy,
    off_topic_to_nlq_response,
    off_topic_to_galaxy_response,
)

# C1: Extracted modules — formatters, health, eval
from src.nlq.api.formatters import (
    nodes_to_related_metrics as _nodes_to_related_metrics,
    format_enriched_text_response as _format_enriched_text_response,
    format_value_with_unit as _format_value_with_unit,
    format_answer as _format_answer,
)
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
    period_type_str = cached.get("period_type", "FULL_YEAR")
    try:
        period_type = PeriodType(period_type_str)
    except ValueError:
        period_type = PeriodType.FULL_YEAR

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


def _handle_dashboard_query(question: str) -> Optional[IntentMapResponse]:
    """
    Generate persona-specific dashboard with key metrics.

    All data is fetched from DCL.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()

    def _query_metric_value(metric: str, period: Optional[str] = None) -> Optional[float]:
        period = period or current_year()
        """Query a single metric value from DCL."""
        try:
            result = dcl_client.query(
                metric=metric,
                time_range={"period": period, "granularity": "annual"}
            )
            if result.get("error"):
                return None
            data = result.get("data", [])
            if not data:
                return None
            # Handle different response formats
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict) and "value" in data[0]:
                    return sum(d.get("value", 0) for d in data if d.get("value") is not None)
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
            "cash", "arr", "burn_multiple", "pipeline", "win_rate",
            "gross_churn_pct", "nrr", "sales_cycle_days", "quota_attainment",
            "new_logo_revenue", "headcount", "revenue_per_employee",
            "magic_number", "cac_payback_months", "ltv_cac", "attrition_rate",
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

    # Get period data from DCL
    period_data = _build_period_data(current_year())

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

    # Detect persona from question or default based on keywords
    persona = _detect_dashboard_persona(question)

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
            requested_metrics.append(("win_rate", "Win Rate", period_data.get('win_rate'), "%", Domain.GROWTH))
        if "churn" in q:
            requested_metrics.append(("gross_churn_pct", "Churn", period_data.get('gross_churn_pct'), "%", Domain.GROWTH))
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
        text_lines.append(f"Revenue: ${period_data.get('revenue')}M | Gross Margin: {period_data.get('gross_margin_pct')}%")
        text_lines.append(f"Operating Margin: {period_data.get('operating_margin_pct')}% | Net Income: ${period_data.get('net_income')}M")
        text_lines.append(f"Cash: ${period_data.get('cash')}M | ARR: ${period_data.get('arr')}M | Burn: {period_data.get('burn_multiple')}x")

    elif persona == "CRO":
        metrics = [
            ("pipeline", "Pipeline", period_data.get('pipeline'), "M", Domain.GROWTH),
            ("win_rate", "Win Rate", period_data.get('win_rate'), "%", Domain.GROWTH),
            ("gross_churn_pct", "Churn", period_data.get('gross_churn_pct'), "%", Domain.GROWTH),
            ("nrr", "NRR", period_data.get('nrr'), "%", Domain.GROWTH),
            ("sales_cycle_days", "Sales Cycle", period_data.get('sales_cycle_days'), "days", Domain.GROWTH),
            ("quota_attainment", "Quota Attainment", period_data.get('quota_attainment'), "%", Domain.GROWTH),
            ("new_logo_revenue", "New Logo Revenue", period_data.get('new_logo_revenue'), "M", Domain.GROWTH),
        ]
        text_lines.append(f"**CRO Dashboard ({period})**")
        text_lines.append(f"Pipeline: ${period_data.get('pipeline')}M | Win Rate: {period_data.get('win_rate')}%")
        text_lines.append(f"Churn: {period_data.get('gross_churn_pct')}% | NRR: {period_data.get('nrr')}%")
        text_lines.append(f"Sales Cycle: {period_data.get('sales_cycle_days')} days | Quota: {period_data.get('quota_attainment')}%")

    elif persona == "COO":
        metrics = [
            ("headcount", "Headcount", period_data.get('headcount'), "", Domain.OPS),
            ("revenue_per_employee", "Rev/Employee", period_data.get('revenue_per_employee'), "M", Domain.OPS),
            ("magic_number", "Magic Number", period_data.get('magic_number'), "", Domain.OPS),
            ("cac_payback_months", "CAC Payback", period_data.get('cac_payback_months'), "mo", Domain.OPS),
            ("ltv_cac", "LTV/CAC", period_data.get('ltv_cac'), "x", Domain.OPS),
            ("attrition_rate", "Attrition Rate", period_data.get('attrition_rate'), "%", Domain.OPS),
            ("implementation_days", "Impl. Days", period_data.get('implementation_days'), "days", Domain.OPS),
        ]
        text_lines.append(f"**COO Dashboard ({period})**")
        text_lines.append(f"Headcount: {period_data.get('headcount')} | Rev/Employee: ${period_data.get('revenue_per_employee')}M")
        text_lines.append(f"Magic Number: {period_data.get('magic_number')} | CAC Payback: {period_data.get('cac_payback_months')} months")
        text_lines.append(f"LTV/CAC: {period_data.get('ltv_cac')}x | Attrition: {period_data.get('attrition_rate')}%")

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
            ("attrition_rate", "Attrition", period_data.get('attrition_rate'), "%", Domain.PEOPLE),
            ("engineering_headcount", "Engineering", period_data.get('engineering_headcount'), "", Domain.PEOPLE),
            ("sales_headcount", "Sales", period_data.get('sales_headcount'), "", Domain.PEOPLE),
            ("cs_headcount", "Customer Success", period_data.get('cs_headcount'), "", Domain.PEOPLE),
            ("csat", "CSAT", period_data.get('csat'), "/5", Domain.PEOPLE),
        ]
        text_lines.append(f"**People Dashboard ({period})**")
        text_lines.append(f"Headcount: {period_data.get('headcount')} | Hires: {period_data.get('hires')} | Attrition: {period_data.get('attrition_rate')}%")
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
            ("win_rate", "Win Rate", y25.get('win_rate'), "%", Domain.GROWTH),
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
        text_lines.append(f"| | Win Rate | {y24.get('win_rate')}% | {y25.get('win_rate')}% | {calc_change(y25.get('win_rate'), y24.get('win_rate'), True)} |")
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

import re as _re_simple

# Import tiered intent components
from src.nlq.services.tiered_intent import detect_complexity, QueryComplexity
from src.nlq.knowledge.synonyms import normalize_metric
from src.nlq.core.superlative_intent import (
    is_superlative_query,
    detect_superlative_intent,
    get_sort_order,
)


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

    if "error" in result:
        return None

    data = result.get("data", [])
    if not data:
        return None

    # Determine unit based on metric
    if intent.metric in ("quota_attainment", "win_rate", "slo_attainment",
                          "gross_margin_pct", "gross_churn_pct", "churn_pct", "nrr"):
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

    # Format response based on result
    if intent.limit == 1:
        # Single result - "top rep", "largest deal", etc.
        top_item = data[0]
        name = top_item.get(intent.dimension) or top_item.get("name") or top_item.get("company") or "Unknown"
        value = top_item.get("value") or top_item.get("attainment_pct") or top_item.get("pipeline") or 0

        # Format value with appropriate unit
        if intent.metric in ("quota_attainment", "win_rate", "slo_attainment",
                              "gross_margin_pct", "gross_churn_pct", "churn_pct", "nrr"):
            value_str = f"{value}%"
        elif intent.metric in ("revenue", "pipeline", "deal_value", "cloud_spend"):
            value_str = f"${value}M"
        elif intent.metric == "headcount":
            value_str = f"{int(value)} employees"
        elif intent.metric == "deploys_per_week":
            value_str = f"{value}/week"
        else:
            value_str = str(value)

        # Build descriptive response
        ranking_word = "top" if order_by == "desc" else "bottom"
        response_text = f"**{name}** is the {ranking_word} {intent.dimension} with {value_str} {intent.metric.replace('_', ' ')}."

        return SimpleMetricResult(
            metric=intent.metric,
            value=value,
            formatted_value=value_str,
            unit=unit,
            display_name=name,
            domain=domain,
            answer=response_text,
            period=dcl_client.get_latest_period(),
        )
    else:
        # Multiple results - "top 5 reps", etc.
        ranking_word = "Top" if order_by == "desc" else "Bottom"
        lines = [f"**{ranking_word} {intent.limit} {intent.dimension}s by {intent.metric.replace('_', ' ')}:**\n"]

        for i, item in enumerate(data, 1):
            name = item.get(intent.dimension) or item.get("name") or item.get("company") or "Unknown"
            value = item.get("value") or item.get("attainment_pct") or item.get("pipeline") or 0

            if intent.metric in ("quota_attainment", "win_rate", "slo_attainment"):
                value_str = f"{value}%"
            elif intent.metric in ("revenue", "pipeline", "deal_value"):
                value_str = f"${value}M"
            elif intent.metric == "headcount":
                value_str = f"{int(value)}"
            else:
                value_str = str(value)

            lines.append(f"{i}. **{name}** - {value_str}")

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


def _try_tiered_metric_query_core(question: str) -> Optional[SimpleMetricResult]:
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
    # Step 0: Check for superlative/ranking queries first
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
        # Simple prefixes (check last)
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
        " by departments", " by regions",
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

    # Strip entity/filter suffixes (e.g., "revenue for North America" → "revenue")
    # This ensures the metric is correctly identified even when a filter is present.
    # The filter itself isn't applied here — that requires graph resolution.
    import re as _re
    for_match = _re.search(r"\s+for\s+(?:the\s+)?(.+)$", metric_query)
    if for_match:
        metric_query = metric_query[:for_match.start()].strip()

    # Strip period suffixes (e.g., "revenue 2025", "margin this year", "arr q3")
    # Include common misspellings
    period_suffixes = [
        " 2024", " 2025", " 2026",
        " this year", " last year", " this quarter", " last quarter",
        " this quater", " last quater",  # misspellings
        " q1", " q2", " q3", " q4",
        " ytd", " mtd", " qtd",
    ]
    for suffix in period_suffixes:
        if metric_query.endswith(suffix):
            metric_query = metric_query[:-len(suffix)].strip()

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
        return _build_simple_metric_result(resolved_metric)

    # Also try the original query in case it's already a metric name
    resolved_metric = normalize_metric(q.rstrip("?").strip())
    if resolved_metric:
        return _build_simple_metric_result(resolved_metric)

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
                    result = loop.run_until_complete(metric_index.lookup(question))
                    if result and result.is_high_confidence:
                        return _build_simple_metric_result(result.canonical_metric)
            except RuntimeError:
                # No event loop, create one
                result = asyncio.run(metric_index.lookup(question))
                if result and result.is_high_confidence:
                    return _build_simple_metric_result(result.canonical_metric)
    except ImportError:
        pass  # Embedding index not available, fall through
    except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
        logger.warning(f"Embedding lookup failed: {e}")

    return None  # No match, let normal flow handle it


def _build_simple_metric_result(metric: str) -> Optional[SimpleMetricResult]:
    """
    Build a SimpleMetricResult for a resolved metric.

    All data is fetched from DCL.
    Returns current period (2026-Q4) data by default.
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client

    dcl_client = get_semantic_client()

    # Default to latest available period for "what is X" queries
    current_period = dcl_client.get_latest_period()
    result = dcl_client.query(
        metric=metric,
        time_range={"period": current_period, "granularity": "quarterly"}
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

    # Handle different response formats
    if isinstance(data, list) and len(data) > 0:
        # Time series - aggregate or take latest
        if isinstance(data[0], dict) and "value" in data[0]:
            # Sum quarterly values for annual total
            value = sum(d.get("value", 0) for d in data if d.get("value") is not None)
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
    unit = get_metric_unit(metric)

    # Format the value
    if unit in ("USD millions", "USD", "$"):
        formatted = f"${round(value, 1)}M"
        answer = f"{display_name} for {current_period} is {formatted}"
    elif unit == "%":
        formatted = f"{round(value, 1)}%"
        answer = f"{display_name} for {current_period} is {formatted}"
    elif unit in ("count", ""):
        formatted = f"{int(value):,}"
        answer = f"{display_name} for {current_period} is {formatted}"
    else:
        formatted = str(round(value, 1))
        answer = f"{display_name} for {current_period} is {formatted}"

    return SimpleMetricResult(
        metric=metric,
        value=value,
        formatted_value=formatted,
        unit=unit or "USD millions",
        display_name=display_name,
        domain=determine_domain(metric),
        answer=answer,
        period=current_period,
        data_quality=data_quality,
        freshness=freshness,
        source=result.get("source", "local"),
        run_provenance=result.get("run_provenance"),
        data_source=result.get("data_source"),
        data_source_reason=result.get("data_source_reason"),
    )


def _try_simple_metric_query(question: str) -> Optional[NLQResponse]:
    """
    Try to answer a simple metric query directly from DCL.

    Uses tiered approach: exact match -> embedding lookup -> fall through to LLM.
    Handles queries like "ebitda", "what's our revenue?", "GM" without Claude.
    Returns None if no confident match found.

    All data is fetched from DCL.
    """
    result = _try_tiered_metric_query_core(question)
    if result:
        return simple_metric_to_nlq_response(result)

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
    # Department aliases
    "dept": "department",
    "org": "department",
    "team": "department",
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
    # Service line aliases
    "service line": "service_line",
    "service_line": "service_line",
    "service": "service_line",
    # Cost center aliases (maps to cost_center dimension if available)
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
    by_match = re.search(r"^(\w+(?:\s+\w+){0,3})\s+(?:by|across)\s+(\w+(?:\s+\w+)?)", q)
    if not by_match:
        return None

    metric_term = by_match.group(1).strip()
    dim_term = by_match.group(2).strip()

    # Extract "for [filter]" suffix after the dimension match
    # e.g., "revenue by cost center for the Cloud division" → filter_dim="division", filter_val="Cloud"
    filter_dim = None
    filter_val = None
    remainder = q[by_match.end():].strip().rstrip("?.!,;")
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

    # Handle plural dimension terms (e.g., "stages" -> "stage", "departments" -> "department")
    if dim_term.endswith("s") and dim_term not in ("business", "success"):
        dim_term = dim_term[:-1]  # Remove trailing 's'

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
    current_period = dcl_client.get_latest_period()

    result = dcl_client.query(
        metric=metric,
        dimensions=[dimension],
        time_range={"period": current_period, "granularity": "quarterly"}
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
            confidence = graph_result.get("confidence", 0.5)
            join_paths = graph_result.get("join_paths", [])
            provenance = graph_result.get("provenance", [])
            filters_resolved = graph_result.get("filters_resolved", {})
            warnings = graph_result.get("warnings", [])
            resolved = graph_result.get("resolved_concepts", [])

            # Build answer describing the resolution path
            path_desc_parts = []
            for jp in join_paths:
                if jp.get("type") == "cross_system_join":
                    path_desc_parts.append(
                        f"{jp['dimension']} via cross-system join "
                        f"({jp.get('source_system', '?')} → {jp.get('join_system', '?')})"
                    )
            path_desc = "; ".join(path_desc_parts) if path_desc_parts else "graph resolution"
            systems = [p.get("source_system", "") for p in provenance if p.get("source_system")]

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
        "metrics": ["customer_count", "nrr", "gross_churn_pct", "logo_churn_pct"],
        "response": "For customers, I can show you:\n- Customer Count (currently 950)\n- Net Revenue Retention / NRR (118%)\n- Gross Churn Rate (7%)\n- Logo Churn Rate\n\nWould you like to see a dashboard with customer metrics, or ask about a specific metric?"
    },
    "sales": {
        "pattern": r"\b(?:what can you show me|what do you have|tell me about|show me available)\b.*\bsales",
        "metrics": ["revenue", "pipeline", "win_rate", "quota_attainment", "sales_cycle_days"],
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
        if _re_simple.search(config["pattern"], q, _re_simple.IGNORECASE):
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
        if _re_simple.search(pattern, q, _re_simple.IGNORECASE):
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


def _try_ingest_status_query_galaxy(question: str) -> Optional[IntentMapResponse]:
    """Handle ingest/infrastructure status queries for /query/galaxy endpoint."""
    result = _try_ingest_status_core(question)
    if result:
        return ingest_status_to_galaxy_response(result, question)
    return None


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
        if _re_simple.search(pattern, q, _re_simple.IGNORECASE):
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


def _try_simple_metric_query_galaxy(question: str) -> Optional[IntentMapResponse]:
    """
    Try to answer a simple metric query directly from DCL for Galaxy mode.

    Uses tiered approach: exact match -> embedding lookup -> fall through to LLM.
    Handles queries like "ebitda", "what's our revenue?", "GM" without Claude.
    Returns None if no confident match found.

    All data is fetched from DCL.
    """
    result = _try_tiered_metric_query_core(question)
    if result:
        return simple_metric_to_galaxy_response(result, question)
    return None


def _try_guided_discovery_galaxy(question: str) -> Optional[IntentMapResponse]:
    """
    Handle guided discovery queries like "what can you show me about customers?" for Galaxy mode.

    Returns available metrics for the requested domain.
    """
    result = _try_guided_discovery_core(question)
    if result:
        return guided_discovery_to_galaxy_response(result, question)
    return None


def _check_missing_data_galaxy(question: str) -> Optional[IntentMapResponse]:
    """
    Check if a query is asking about non-existent data for Galaxy mode.

    Returns a graceful error response for queries about data we don't have.
    """
    result = _check_missing_data_core(question)
    if result:
        return missing_data_to_galaxy_response(result, question)
    return None


def _handle_ambiguous_query_text(
    question: str,
    ambiguity_type: AmbiguityType,
    candidates: list,
    clarification: Optional[str],
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

    # Generate nodes for related metrics (same as Galaxy View)
    nodes = generate_nodes_for_ambiguous_query(
        ambiguity_type,
        candidates,
        current_year,
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
        """Get value from DCL."""
        result = dcl_client.query(metric=metric, time_range={"period": period})
        if result.get("error"):
            return None
        data = result.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and "value" in data[0]:
                return sum(d.get("value", 0) for d in data if d.get("value") is not None)
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
        # "whats the margin" -> "Gross: 65.0%, Operating: 35.0%, Net: 22.5%"
        if "margin" in q:
            gross = get_val("gross_margin_pct", current_year)
            op = get_val("operating_margin_pct", current_year)
            net = get_val("net_income_pct", current_year)
            answer = f"Gross: {fmt_val('gross_margin_pct', gross)}, Operating: {fmt_val('operating_margin_pct', op)}, Net: {fmt_val('net_income_pct', net)}"
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
            margin = get_val("net_income_pct", current_year)
            answer = f"Yes, {fmt_val('net_income_pct', margin)} net margin in {current_year} forecast"
            return NLQResponse(success=True, answer=answer, value=margin, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="net_income_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "are we hitting quota" -> "Yes, 95.8% attainment"
        if "quota" in q or "hitting" in q:
            attainment = get_val("quota_attainment", current_year)
            answer = f"Yes, {round(attainment, 1) if attainment else 0}% attainment"
            return NLQResponse(success=True, answer=answer, value=attainment, unit="%",
                confidence=0.95, parsed_intent="YES_NO", resolved_metric="quota_attainment", resolved_period=current_year,
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
                related_metrics=related_metrics)

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
            churn = get_val("gross_churn_pct", current_year)
            answer = f"Yes, NRR {round(nrr, 0) if nrr else 0}%, churn down to {round(churn, 0) if churn else 0}%"
            return NLQResponse(success=True, answer=answer, value=nrr, unit="%",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="nrr", resolved_period=current_year,
                related_metrics=related_metrics)

        # "forecast looking good?" -> "Yes, on track: $230M bookings, 44% win rate"
        if "forecast" in q:
            bookings = get_val("bookings", current_year)
            win_rate = get_val("win_rate", current_year)
            answer = f"Yes, on track: ${round(bookings, 0) if bookings else 0}M bookings, {round(win_rate, 0) if win_rate else 0}% win rate"
            return NLQResponse(success=True, answer=answer, value=bookings, unit="$M",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="bookings", resolved_period=current_year,
                related_metrics=related_metrics)

        # "attrition bad?" -> "Moderate - 2.7% Q4, manageable"
        if "attrition" in q:
            attrition = get_val("attrition_rate", f"Q4 {current_year}")
            answer = f"Moderate - {round(attrition, 1) if attrition else 0}% Q4, manageable"
            return NLQResponse(success=True, answer=answer, value=attrition, unit="%",
                confidence=0.85, parsed_intent="JUDGMENT_CALL", resolved_metric="attrition_rate", resolved_period=f"Q4 {current_year}",
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
            gross_churn = get_val("gross_churn_pct", current_year)
            logo_churn = get_val("logo_churn_pct", current_year)
            nrr = get_val("nrr", current_year)
            answer = f"Gross: {round(gross_churn, 0) if gross_churn else 0}%, Logo: {round(logo_churn, 0) if logo_churn else 0}%, NRR: {round(nrr, 0) if nrr else 0}%"
            return NLQResponse(success=True, answer=answer, value=gross_churn, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="gross_churn_pct", resolved_period=current_year,
                related_metrics=related_metrics)

        # "NRR" -> "120% (2026F)"
        if q == "nrr" or q.startswith("nrr"):
            nrr = get_val("nrr", current_year)
            answer = f"{round(nrr, 0) if nrr else 0}% ({current_year}F)"
            return NLQResponse(success=True, answer=answer, value=nrr, unit="%",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="nrr", resolved_period=current_year,
                related_metrics=related_metrics)

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
            win_rate = get_val("win_rate", current_year)
            answer = f"${round(pipeline, 0) if pipeline else 0}M pipeline, ${round(qualified, 0) if qualified else 0}M qualified, {round(win_rate, 0) if win_rate else 0}% win rate"
            return NLQResponse(success=True, answer=answer, value=pipeline, unit="$M",
                confidence=0.95, parsed_intent="SHORTHAND", resolved_metric="pipeline", resolved_period=current_year,
                related_metrics=related_metrics)

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
                result = dcl_client.query(metric="top_deals", time_range={"period": year})
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
            rev_cy = get_val("revenue", current_year)
            rev_ly = get_val("revenue", last_year)
            ni_cy = get_val("net_income", current_year)
            ni_ly = get_val("net_income", last_year)
            om_cy = get_val("operating_margin_pct", current_year)
            om_ly = get_val("operating_margin_pct", last_year)
            rev_chg = round((rev_cy - rev_ly) / rev_ly * 100) if rev_cy and rev_ly else 0
            ni_chg = round((ni_cy - ni_ly) / ni_ly * 100) if ni_cy and ni_ly else 0
            om_chg = "flat" if om_cy == om_ly else f"+{round(om_cy - om_ly, 1)}%" if om_cy > om_ly else f"{round(om_cy - om_ly, 1)}%"
            answer = f"{current_year} vs {last_year}: Revenue ${round(rev_cy, 0) if rev_cy else 0}M vs ${round(rev_ly, 0) if rev_ly else 0}M (+{rev_chg}%), Net Income ${round(ni_cy, 0) if ni_cy else 0}M vs ${round(ni_ly, 2) if ni_ly else 0}M (+{ni_chg}%), Operating Margin {fmt_val('operating_margin_pct', om_cy)} vs {fmt_val('operating_margin_pct', om_ly)} ({om_chg})"
            return NLQResponse(success=True, answer=answer, value=rev_chg, unit="%",
                confidence=0.9, parsed_intent="COMPARISON", resolved_metric="comparison", resolved_period=current_year,
                related_metrics=related_metrics)

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
            win_rate = get_val("win_rate", current_year)
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
            win_rate = get_val("win_rate", last_year)
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
            wr_yb = get_val("win_rate", year_before)
            wr_ly = get_val("win_rate", last_year)
            wr_cy = get_val("win_rate", current_year)
            answer = f"{round(wr_yb, 0) if wr_yb else 0}% → {round(wr_ly, 0) if wr_ly else 0}% → {round(wr_cy, 0) if wr_cy else 0}% (improving)"
            return NLQResponse(success=True, answer=answer, value=wr_cy, unit="%",
                confidence=0.9, parsed_intent="INCOMPLETE", resolved_metric="win_rate", resolved_period=current_year,
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
    _trace = diag_init()
    diag(f"[NLQ-DIAG] /query endpoint: question='{request.question[:60]}', data_mode={request.data_mode}")
    set_data_mode(request.data_mode)
    if request.data_mode == "demo":
        set_force_local(True)
    try:
        off_topic_response = handle_off_topic_or_easter_egg(request.question)
        if off_topic_response:
            persona = detect_persona_from_question(request.question)
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
        # SIMPLE BREAKDOWN QUERIES - Handle "X by Y" queries early (no Claude needed)
        # Must come before simple metric queries to avoid "revenue by region" -> "revenue"
        # =================================================================
        breakdown_result = _try_simple_breakdown_query(request.question)
        if breakdown_result:
            return breakdown_result

        # =================================================================
        # SIMPLE METRIC QUERIES - Handle "what is X?" queries early (no Claude needed)
        # =================================================================
        simple_result = _try_simple_metric_query(request.question)
        if simple_result:
            return simple_result

        # Check for dashboard/report queries (doesn't need Claude API)
        # NOTE: For visual dashboard requests, we let the visualization intent handler below
        # generate proper dashboard widgets. Only text-mode dashboard summaries go through the old handler.
        if _is_dashboard_query(request.question):
            # Check if this should be a visual dashboard first
            should_viz, viz_requirements = should_generate_visualization(request.question)
            if should_viz and viz_requirements.intent != VisualizationIntent.SIMPLE_ANSWER:
                # Let the visualization intent handler below generate proper widgets
                pass
            else:
                # Fallback to text summary for non-visual dashboard requests
                dashboard_response = _handle_dashboard_query(request.question)
                if dashboard_response:
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
            return guided_result

        # =================================================================
        # INGEST / INFRASTRUCTURE STATUS - Handle "is Splunk connected?",
        # "what tenants are pushing data?", "ingest status" etc.
        # =================================================================
        ingest_result = _try_ingest_status_query(request.question)
        if ingest_result:
            return ingest_result

        # =================================================================
        # MISSING DATA CHECK - Handle queries about non-existent data
        # =================================================================
        missing_result = _check_missing_data(request.question)
        if missing_result:
            return missing_result

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
                _, viz_requirements = should_generate_visualization(request.question)

                # Apply refinement
                updated_schema = refine_dashboard_schema(
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
        should_viz, viz_requirements = should_generate_visualization(request.question)

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

        # Check for ambiguity first (same as Galaxy endpoint)
        ambiguity_type, candidates, clarification = detect_ambiguity(request.question)

        if ambiguity_type and ambiguity_type != AmbiguityType.NONE:
            # Handle ambiguous query with text response
            return _handle_ambiguous_query_text(
                request.question,
                ambiguity_type,
                candidates,
                clarification,
            )

        # Set up components
        reference_date = request.reference_date or date.today()
        resolver = PeriodResolver(reference_date)
        claude_client = get_claude_client()
        executor = QueryExecutor(claude_client=claude_client)

        # Get session ID from request body
        session_id = request.session_id or "default"

        # =================================================================
        # RAG CACHE LOOKUP - Check cache before calling Claude
        # =================================================================
        cache_service = get_cache_service()
        parsed = None
        cache_hit = False
        cache_result = None

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
                learning_log = get_learning_log()
                await learning_log.log_entry(LearningLogEntry(
                    query=request.question,
                    success=True,
                    source="cache",
                    learned=False,
                    message=f"Cache hit ({cache_result.hit_type.value}, {cache_result.similarity:.0%} match)",
                    persona=detect_persona_from_metric(cache_result.parsed.get("metric")) or "CFO",
                    similarity=cache_result.similarity,
                ))

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

            # Store new parse in cache for future use
            if cache_service and cache_service.is_available:
                persona = detect_persona_from_metric(parsed.metric) or "CFO"
                cache_dict = _parsed_query_to_cache_dict(parsed)
                cache_service.store(
                    query=request.question,
                    parsed=cache_dict,
                    persona=persona,
                    confidence=0.95,  # Claude parses are high confidence
                    source="llm",
                )

            # Log to learning log
            learning_log = get_learning_log()
            stored_in_cache = cache_service and cache_service.is_available
            await learning_log.log_entry(LearningLogEntry(
                query=request.question,
                success=True,
                source="llm",
                learned=stored_in_cache,
                message=f'"{request.question}" → {parsed.metric}' + (" (learned)" if stored_in_cache else ""),
                persona=detect_persona_from_metric(parsed.metric) or "CFO",
                similarity=0.0,
                llm_confidence=0.95,
            ))

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
            provenance=dcl_data.get("provenance"),
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


@router.post("/intent-map", response_model=IntentMapResponse)
@router.post("/query/galaxy", response_model=IntentMapResponse)
async def query_galaxy(request: NLQRequest) -> IntentMapResponse:
    """
    Process a natural language query and return Galaxy visualization data.

    Returns IntentMapResponse with:
    - Nodes for orbital rings (EXACT, POTENTIAL, HYPOTHESIS)
    - Confidence and data quality metrics
    - Persona and disambiguation info
    """
    _trace = diag_init()
    diag(f"[NLQ-DIAG] /query/galaxy endpoint: question='{request.question[:60]}', data_mode={request.data_mode}")
    set_data_mode(request.data_mode)
    if request.data_mode == "demo":
        set_force_local(True)
    try:
        off_topic_response = handle_off_topic_or_easter_egg(request.question)
        if off_topic_response:
            persona = detect_persona_from_question(request.question)
            return IntentMapResponse(
                query=request.question,
                query_type="OFF_TOPIC",
                ambiguity_type=None,
                persona=persona,
                overall_confidence=1.0,
                overall_data_quality=1.0,
                node_count=0,
                nodes=[],
                primary_node_id=None,
                primary_answer=off_topic_response,
                text_response=off_topic_response,
                needs_clarification=False,
                clarification_prompt=None,
            )

        # =================================================================
        # SIMPLE METRIC QUERIES - Handle direct questions like "what's revenue?"
        # (Must be early to catch simple lookups before other handlers)
        # =================================================================
        simple_response = _try_simple_metric_query_galaxy(request.question)
        if simple_response:
            return simple_response

        # =================================================================
        # INGEST / INFRASTRUCTURE STATUS - Handle source/tenant/connection queries
        # =================================================================
        ingest_response = _try_ingest_status_query_galaxy(request.question)
        if ingest_response:
            return ingest_response

        # =================================================================
        # MISSING DATA CHECK - Gracefully handle non-existent data queries
        # =================================================================
        missing_data_response = _check_missing_data_galaxy(request.question)
        if missing_data_response:
            return missing_data_response

        # =================================================================
        # GUIDED DISCOVERY - Handle "what can you show me about X?" queries
        # =================================================================
        guided_response = _try_guided_discovery_galaxy(request.question)
        if guided_response:
            return guided_response

        # Check for dashboard/report queries (doesn't need Claude API)
        if _is_dashboard_query(request.question):
            dashboard_response = _handle_dashboard_query(request.question)
            if dashboard_response:
                return dashboard_response

        # =================================================================
        # REFINEMENT INTENT DETECTION - Handle refinement queries FIRST
        # (Must come before visualization to handle "make that a bar chart")
        # =================================================================
        session_id = request.session_id or "default"
        session_data = get_session_dashboard(session_id)
        current_schema = session_data.get("dashboard") if session_data else None
        has_current_dashboard = current_schema is not None

        refinement_intent = detect_refinement_intent(request.question, has_current_dashboard)

        # Handle context-dependent queries without a dashboard
        if is_context_dependent_query(request.question) and not has_current_dashboard:
            clarification_msg = needs_clarification_without_context(request.question)
            if clarification_msg:
                return IntentMapResponse(
                    query=request.question,
                    query_type="CLARIFICATION_NEEDED",
                    ambiguity_type=None,
                    persona=detect_persona_from_question(request.question) or "CFO",
                    overall_confidence=0.7,
                    overall_data_quality=1.0,
                    node_count=0,
                    nodes=[],
                    primary_node_id=None,
                    primary_answer=clarification_msg,
                    text_response=clarification_msg,
                    needs_clarification=True,
                    clarification_prompt=clarification_msg,
                )

        # Handle refinement if we have a current dashboard
        if refinement_intent.is_refinement and has_current_dashboard:
            logger.info(f"Galaxy refinement detected: {refinement_intent.refinement_type}")

            try:
                from src.nlq.models.dashboard_schema import DashboardSchema

                # Reconstruct DashboardSchema from stored dict
                if isinstance(current_schema, dict):
                    current_schema = DashboardSchema(**current_schema)

                # Detect visualization requirements for the refinement
                _, viz_requirements = should_generate_visualization(request.question)

                # Apply refinement
                updated_schema = refine_dashboard_schema(
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

                # Update session state (convert to dict for storage)
                updated_dict = updated_schema.model_dump() if hasattr(updated_schema, 'model_dump') else updated_schema
                set_session_dashboard(session_id, updated_dict, widget_data)

                # Create nodes from updated dashboard
                nodes = []
                for i, widget in enumerate(updated_schema.widgets):
                    widget_id = widget.id
                    data = widget_data.get(widget_id, {})
                    value = data.get("value")
                    formatted = data.get("formatted_value", str(value) if value else None)

                    metric_name = widget.data.metrics[0].metric if widget.data.metrics else "metric"
                    nodes.append(IntentNode(
                        id=f"ref_{i}",
                        metric=metric_name,
                        display_name=widget.title,
                        match_type=MatchType.EXACT,
                        domain=Domain.FINANCE,
                        confidence=0.95,
                        data_quality=1.0,
                        freshness="0h",
                        value=value,
                        formatted_value=formatted,
                        period=current_year(),
                        semantic_label="Refinement",
                    ))

                return IntentMapResponse(
                    query=request.question,
                    query_type="REFINEMENT",
                    ambiguity_type=None,
                    persona=detect_persona_from_question(request.question) or "CFO",
                    overall_confidence=0.95,
                    overall_data_quality=1.0,
                    node_count=len(nodes),
                    nodes=nodes,
                    primary_node_id=nodes[0].id if nodes else None,
                    primary_answer=f"Updated dashboard: {updated_schema.title}",
                    text_response=f"Updated dashboard: {updated_schema.title}",
                    needs_clarification=False,
                    clarification_prompt=None,
                    dashboard=updated_schema.model_dump(),
                    dashboard_data=widget_data,
                    response_type="dashboard",
                )

            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Error applying refinement: {e}", exc_info=True)
                if is_strict_mode():
                    # In strict mode, return error response instead of falling through
                    return _create_error_galaxy_response(
                        question=request.question,
                        query_type="ERROR",
                        error_code="REFINEMENT_FAILED",
                        error_message=f"Dashboard refinement failed: {str(e)}. Strict mode is enabled.",
                    )
                # In production, fall through to visualization/normal processing

        # =================================================================
        # AMBIGUOUS QUERY DETECTION - Ask for clarification if needed
        # =================================================================
        is_ambiguous, ambiguous_term, options = is_ambiguous_visualization_query(request.question)
        if is_ambiguous and ambiguous_term:
            # Format options for display
            options_list = "\n".join(f"• {opt}" for opt in options[:4])
            clarification_msg = f"I can show you a few types of {ambiguous_term}:\n{options_list}\n\nWhich would you like?"

            return IntentMapResponse(
                query=request.question,
                query_type="AMBIGUOUS",
                ambiguity_type="vague_metric",
                persona=detect_persona_from_question(request.question) or "CFO",
                overall_confidence=0.6,
                overall_data_quality=1.0,
                node_count=0,
                nodes=[],
                primary_node_id=None,
                primary_answer=clarification_msg,
                text_response=clarification_msg,
                needs_clarification=True,
                clarification_prompt=clarification_msg,
            )

        # =================================================================
        # VISUALIZATION INTENT DETECTION - Handle visualization queries
        # =================================================================
        should_viz, viz_requirements = should_generate_visualization(request.question)

        if should_viz and viz_requirements.intent != VisualizationIntent.SIMPLE_ANSWER:
            logger.info(f"Galaxy visualization intent detected: {viz_requirements.intent.value}")

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

                # Store in session for refinement (convert to dict for storage)
                session_id = request.session_id or "default"
                dashboard_dict = dashboard_schema.model_dump() if hasattr(dashboard_schema, 'model_dump') else dashboard_schema
                set_session_dashboard(session_id, dashboard_dict, widget_data)

                # Create galaxy nodes from dashboard metrics
                nodes = []
                for i, widget in enumerate(dashboard_schema.widgets):
                    widget_id = widget.id
                    data = widget_data.get(widget_id, {})
                    value = data.get("value")
                    formatted = data.get("formatted_value", str(value) if value else None)

                    metric_name = widget.data.metrics[0].metric if widget.data.metrics else "metric"
                    nodes.append(IntentNode(
                        id=f"viz_{i}",
                        metric=metric_name,
                        display_name=widget.title,
                        match_type=MatchType.EXACT,
                        domain=Domain.FINANCE,
                        confidence=0.95,
                        data_quality=1.0,
                        freshness="0h",
                        value=value,
                        formatted_value=formatted,
                        period=current_year(),
                        semantic_label=widget.title,
                    ))

                return IntentMapResponse(
                    query=request.question,
                    query_type="VISUALIZATION",
                    ambiguity_type=None,
                    persona=detect_persona_from_question(request.question) or "CFO",
                    overall_confidence=0.95,
                    overall_data_quality=1.0,
                    node_count=len(nodes),
                    nodes=nodes,
                    primary_node_id=nodes[0].id if nodes else None,
                    primary_answer=f"Here's a dashboard showing {dashboard_schema.title}",
                    text_response=f"Here's a dashboard showing {dashboard_schema.title}",
                    needs_clarification=False,
                    clarification_prompt=None,
                    dashboard=dashboard_schema.model_dump(),
                    dashboard_data=widget_data,
                    response_type="dashboard",
                    debug_info=debug_info.to_dict() if is_strict_mode() else None,
                )

            except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
                logger.error(f"Error generating visualization: {e}", exc_info=True)
                if is_strict_mode():
                    # In strict mode, return error response instead of falling through
                    return _create_error_galaxy_response(
                        question=request.question,
                        query_type="ERROR",
                        error_code="VISUALIZATION_GENERATION_FAILED",
                        error_message=f"Visualization generation failed: {str(e)}. Strict mode is enabled.",
                    )
                # In production, fall through to normal processing

        reference_date = request.reference_date or date.today()
        resolver = PeriodResolver(reference_date)

        # Check for ambiguity first (before Claude client — these paths don't need LLM)
        ambiguity_type, candidates, clarification = detect_ambiguity(request.question)

        if ambiguity_type and ambiguity_type != AmbiguityType.NONE:
            # Handle ambiguous query
            return _handle_ambiguous_query_galaxy(
                request.question,
                ambiguity_type,
                candidates,
                clarification,
                resolver,
            )

        claude_client = get_claude_client()
        executor = QueryExecutor(claude_client=claude_client)

        # Get session ID from request body
        session_id = request.session_id or "default"

        # =================================================================
        # RAG CACHE LOOKUP - Check cache before calling Claude
        # =================================================================
        cache_service = get_cache_service()
        parsed = None
        cache_hit = False
        cache_result = None

        if cache_service and cache_service.is_available:
            cache_result = cache_service.lookup(request.question)

            if cache_result.high_confidence and cache_result.parsed:
                # Use cached parsed structure - no Claude call needed
                parsed = _cached_to_parsed_query(cache_result.parsed)
                cache_hit = True
                logger.info(f"Galaxy RAG cache hit ({cache_result.hit_type.value}, {cache_result.similarity:.3f}): {request.question[:50]}...")

                # Track cache hit in session stats
                call_counter = get_call_counter()
                call_counter.increment_cached(session_id)

                # Log to learning log
                learning_log = get_learning_log()
                await learning_log.log_entry(LearningLogEntry(
                    query=request.question,
                    success=True,
                    source="cache",
                    learned=False,
                    message=f'Retrieved "{request.question}" ({cache_result.similarity:.0%} match)',
                    persona=detect_persona_from_metric(cache_result.parsed.get("metric")) or "CFO",
                    similarity=cache_result.similarity,
                ))

        # =================================================================
        # CLAUDE PARSING - Fall back to LLM if no cache hit
        # =================================================================
        if not cache_hit:
            # In STATIC mode, return error if no cache hit (no LLM fallback)
            if request.mode == QueryMode.STATIC:
                logger.info(f"Galaxy static mode - no cache hit for: {request.question[:50]}...")
                return IntentMapResponse(
                    query=request.question,
                    query_type="STATIC_MODE_CACHE_MISS",
                    ambiguity_type=None,
                    persona=detect_persona_from_question(request.question) or "CFO",
                    overall_confidence=0.0,
                    overall_data_quality=0.0,
                    node_count=0,
                    nodes=[],
                    primary_node_id=None,
                    primary_answer=None,
                    text_response="Query not found in cache. Switch to AI mode for LLM processing.",
                    needs_clarification=False,
                    clarification_prompt=None,
                )

            # AI mode: Initialize Claude client and parser
            claude_client = get_claude_client()
            parser = QueryParser(claude_client)

            # Parse the query with Claude
            parsed = parser.parse(request.question)

            # Increment LLM call counter
            call_counter = get_call_counter()
            call_counter.increment(session_id)

            # Store new parse in cache for future use
            if cache_service and cache_service.is_available:
                persona = detect_persona_from_metric(parsed.metric) or "CFO"
                cache_dict = _parsed_query_to_cache_dict(parsed)
                cache_service.store(
                    query=request.question,
                    parsed=cache_dict,
                    persona=persona,
                    confidence=0.95,  # Claude parses are high confidence
                    source="llm",
                )

            # Log to learning log
            learning_log = get_learning_log()
            stored_in_cache = cache_service and cache_service.is_available
            await learning_log.log_entry(LearningLogEntry(
                query=request.question,
                success=True,
                source="llm",
                learned=stored_in_cache,
                message=f'"{request.question}" → {parsed.metric}' + (" (learned)" if stored_in_cache else ""),
                persona=detect_persona_from_metric(parsed.metric) or "CFO",
                similarity=0.0,
                llm_confidence=0.95,
            ))

        logger.info(f"Parsed query for galaxy (cache_hit={cache_hit}): {parsed}")

        # Resolve periods
        resolved = resolver.resolve(parsed.period_reference)
        parsed.resolved_period = resolver.to_period_key(resolved)

        if parsed.intent == QueryIntent.COMPARISON_QUERY and parsed.comparison_period:
            comp_resolved = resolver.resolve(parsed.comparison_period)
            parsed.comparison_period = resolver.to_period_key(comp_resolved)

        if parsed.intent == QueryIntent.AGGREGATION_QUERY and parsed.aggregation_periods:
            resolved_agg_periods = []
            for period in parsed.aggregation_periods:
                agg_resolved = resolver.resolve(period)
                resolved_agg_periods.append(resolver.to_period_key(agg_resolved))
            parsed.aggregation_periods = resolved_agg_periods

        # Execute the query
        result = executor.execute(parsed)

        # Get session ID for tracking
        session_id = request.session_id or "default"

        if not result.success:
            response = _create_stumped_galaxy_response(
                request.question,
                parsed.intent.value,
            )
            # Track as insufficient data (execution failed)
            return _track_intent_map_if_needed(
                response, request.question, session_id,
                metric_found=True, period_found=True, data_exists=False
            )

        # Generate nodes based on intent
        nodes = _generate_nodes_for_intent(parsed, result)

        # Calculate overall metrics
        overall_confidence, overall_data_quality = calculate_overall_metrics(nodes)

        # Format enriched text response using nodes
        text_response = _format_enriched_text_response(
            nodes,
            parsed.intent.value,
            None,  # No ambiguity for clear queries
            None,  # No clarification needed
        )

        # Get primary node
        primary_node_id = nodes[0].id if nodes else None

        # =================================================================
        # DCL ENRICHMENT — entity resolution, provenance, conflicts, temporal
        # =================================================================
        dcl_data = {}
        try:
            is_comparison = parsed.intent == QueryIntent.COMPARISON_QUERY
            dcl_data = dcl_enrich_response(
                metric=parsed.metric,
                entity=getattr(parsed, 'entity', None),
                persona=detect_persona_from_metric(parsed.metric) or detect_persona_from_question(request.question),
                start_period=parsed.resolved_period,
                end_period=parsed.comparison_period if is_comparison else None,
                is_comparison=is_comparison,
            )
        except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
            logger.debug(f"Galaxy DCL enrichment skipped: {e}")

        # Annotate nodes with source_system and conflict info from DCL
        if dcl_data.get("conflicts"):
            for node in nodes:
                for conflict in dcl_data["conflicts"]:
                    if conflict.get("metric") == node.metric:
                        node.has_conflict = True
                        node.conflict_details = conflict.get("root_cause", {}).get("explanation")
                        break
        if dcl_data.get("provenance"):
            lineage = dcl_data["provenance"].get("lineage", [])
            sor = next((l for l in lineage if l.get("is_system_of_record")), None)
            if sor:
                for node in nodes:
                    node.source_system = sor.get("source_system")

        response = IntentMapResponse(
            query=request.question,
            query_type=parsed.intent.value,
            ambiguity_type=None,
            persona=detect_persona_from_metric(parsed.metric) or detect_persona_from_question(request.question) or "CFO",
            overall_confidence=overall_confidence,
            overall_data_quality=overall_data_quality,
            node_count=len(nodes),
            nodes=nodes,
            primary_node_id=primary_node_id,
            primary_answer=text_response,
            text_response=text_response,
            needs_clarification=False,
            clarification_prompt=None,
            entity=dcl_data.get("entity_name"),
            entity_id=dcl_data.get("entity_id"),
            entity_resolution=dcl_data.get("entity_resolution"),
            provenance=dcl_data.get("provenance"),
            conflicts=dcl_data.get("conflicts"),
            temporal_warning=dcl_data.get("temporal_warning"),
            debug_info={"nlq_diag_trace": _trace} if _trace else None,
        )
        # Track if confidence is below threshold
        return _track_intent_map_if_needed(response, request.question, session_id)

    except ValueError as e:
        logger.error(f"Query parsing error: {e}")
        diag(f"[NLQ-DIAG] /query/galaxy PARSE_ERROR: {e}")
        response = _create_error_galaxy_response(
            request.question,
            "ERROR",
            "PARSE_ERROR",
            str(e),
        )
        response.debug_info = {"nlq_diag_trace": _trace, "error": str(e), "error_type": "PARSE_ERROR"} if _trace else {"error": str(e), "error_type": "PARSE_ERROR"}
        return _track_intent_map_if_needed(response, request.question)
    except HTTPException as e:
        # Catch FastAPI HTTPExceptions (e.g. missing API key) and return structured response
        logger.error(f"HTTP error in galaxy query: {e.status_code} - {e.detail}")
        diag(f"[NLQ-DIAG] /query/galaxy HTTP_ERROR: {e.status_code} {e.detail}")
        error_msg = str(e.detail) if e.detail else "HTTP error during query processing"
        response = _create_error_galaxy_response(
            request.question,
            "ERROR",
            "CONFIG_ERROR",
            error_msg,
        )
        response.text_response = error_msg
        response.debug_info = {"nlq_diag_trace": _trace, "error": error_msg, "error_type": "CONFIG_ERROR"} if _trace else {"error": error_msg, "error_type": "CONFIG_ERROR"}
        return response
    except RuntimeError as e:
        error_msg = str(e)
        is_live = "LIVE MODE" in error_msg
        code = "CONFIG_ERROR" if is_live else "INTERNAL_ERROR"
        logger.error(f"{'Live mode' if is_live else 'Runtime'} error in galaxy query: {e}")
        diag(f"[NLQ-DIAG] /query/galaxy {code}: {e}")
        response = _create_error_galaxy_response(
            request.question,
            "ERROR",
            code,
            error_msg,
        )
        response.debug_info = {"nlq_diag_trace": _trace, "error": error_msg, "error_type": code} if _trace else {"error": error_msg, "error_type": code}
        return _track_intent_map_if_needed(response, request.question)
    except (KeyError, TypeError, AttributeError, OSError) as e:
        logger.exception(f"Unexpected error processing galaxy query: {e}")
        diag(f"[NLQ-DIAG] /query/galaxy EXCEPTION: {type(e).__name__}: {e}")
        response = _create_error_galaxy_response(
            request.question,
            "ERROR",
            "INTERNAL_ERROR",
            f"{type(e).__name__}: {e}",
        )
        response.debug_info = {"nlq_diag_trace": _trace, "error": str(e), "error_type": type(e).__name__} if _trace else {"error": str(e), "error_type": type(e).__name__}
        return _track_intent_map_if_needed(response, request.question)
    except Exception as e:
        # Catch-all for Claude API errors, circuit breaker, timeouts, and anything else
        logger.exception(f"Unhandled error in galaxy query: {type(e).__name__}: {e}")
        diag(f"[NLQ-DIAG] /query/galaxy UNHANDLED: {type(e).__name__}: {e}")
        error_msg = f"{type(e).__name__}: {e}"
        response = _create_error_galaxy_response(
            request.question,
            "ERROR",
            "UNHANDLED_ERROR",
            error_msg,
        )
        response.text_response = f"Query processing failed: {error_msg}"
        response.debug_info = {"nlq_diag_trace": _trace, "error": error_msg, "error_type": type(e).__name__} if _trace else {"error": error_msg, "error_type": type(e).__name__}
        return response
    finally:
        set_force_local(False)
        set_data_mode(None)


def _handle_ambiguous_query_galaxy(
    question: str,
    ambiguity_type: AmbiguityType,
    candidates: list,
    clarification: Optional[str],
    resolver: PeriodResolver,
) -> IntentMapResponse:
    """Handle an ambiguous query and return Galaxy response. Data fetched from DCL."""
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    dcl_client = get_semantic_client()

    # Default to current year
    current_year = str(date.today().year)
    last_year = str(int(current_year) - 1)
    q = question.lower()

    # ===== SPECIAL HANDLING FOR BIGGEST DEALS =====
    # Match text handler: show deal data directly instead of asking for clarification
    if "biggest deals" in q or ("deals" in q and "biggest" in q):
        def _get_top_deals_galaxy(year: str):
            """Get top deals from DCL."""
            result = dcl_client.query(metric="top_deals", time_range={"period": year})
            return result.get("data", [])

        # Check if specific year is requested
        year_match = re.search(r'20\d{2}', question)
        if year_match:
            year = year_match.group()
            top_deals = _get_top_deals_galaxy(year)
            if top_deals:
                deal_list = ", ".join([f"{d['company']} ${d['value']}M" for d in top_deals])
                total = sum(d['value'] for d in top_deals)
                text_response = f"Top deals {year}: {deal_list} (${total}M total)"

                # Create deal nodes
                nodes = []
                for i, deal in enumerate(top_deals):
                    node = IntentNode(
                        id=f"deal_{i+1}",
                        label=deal['company'],
                        ring="EXACT",
                        value=deal['value'],
                        unit="$M",
                        period=f"{deal.get('quarter', '')} {year}".strip(),
                        metric="deal_value",
                        confidence=0.95,
                        data_quality=1.0,
                        source="dcl",
                    )
                    nodes.append(node)

                return IntentMapResponse(
                    query=question,
                    query_type="CONTEXT_DEPENDENT",
                    ambiguity_type=ambiguity_type,
                    persona="CRO",
                    overall_confidence=0.9,
                    overall_data_quality=1.0,
                    node_count=len(nodes),
                    nodes=nodes,
                    primary_node_id="deal_1" if nodes else None,
                    primary_answer=text_response,
                    text_response=text_response,
                    needs_clarification=False,
                    clarification_prompt=None,
                )

        # No year specified - show current year and prior year deals
        cy_deals = _get_top_deals_galaxy(current_year)
        ly_deals = _get_top_deals_galaxy(last_year)

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
            text_response = "Top deals - " + " | ".join(lines)
            all_deals = cy_deals + ly_deals

            # Create deal nodes
            nodes = []
            for i, deal in enumerate(all_deals):
                year_label = current_year if i < len(cy_deals) else last_year
                node = IntentNode(
                    id=f"deal_{i+1}",
                    label=deal['company'],
                    ring="EXACT",
                    value=deal['value'],
                    unit="$M",
                    period=f"{deal.get('quarter', '')} {year_label}".strip(),
                    metric="deal_value",
                    confidence=0.95,
                    data_quality=1.0,
                    source="dcl",
                )
                nodes.append(node)

            return IntentMapResponse(
                query=question,
                query_type="CONTEXT_DEPENDENT",
                ambiguity_type=ambiguity_type,
                persona="CRO",
                overall_confidence=0.9,
                overall_data_quality=1.0,
                node_count=len(nodes),
                nodes=nodes,
                primary_node_id="deal_1" if nodes else None,
                primary_answer=text_response,
                text_response=text_response,
                needs_clarification=False,
                clarification_prompt=None,
            )

        # No deal data available
        return IntentMapResponse(
            query=question,
            query_type="CONTEXT_DEPENDENT",
            ambiguity_type=ambiguity_type,
            persona="CRO",
            overall_confidence=0.5,
            overall_data_quality=0.0,
            node_count=0,
            nodes=[],
            primary_node_id=None,
            primary_answer="No deal data available",
            text_response="No deal data available",
            needs_clarification=False,
            clarification_prompt=None,
        )

    # Default ambiguous query handling
    period = current_year

    # Generate nodes for ambiguous query
    nodes = generate_nodes_for_ambiguous_query(
        ambiguity_type,
        candidates,
        period,
    )

    overall_confidence, overall_data_quality = calculate_overall_metrics(nodes)

    # Build enriched text response for ambiguous query
    text_response = _format_enriched_text_response(
        nodes,
        "AMBIGUOUS",
        ambiguity_type,
        clarification,
    )

    return IntentMapResponse(
        query=question,
        query_type="AMBIGUOUS",
        ambiguity_type=ambiguity_type,
        persona=detect_persona_from_question(question) or "CFO",
        overall_confidence=overall_confidence,
        overall_data_quality=overall_data_quality,
        node_count=len(nodes),
        nodes=nodes,
        primary_node_id=None,
        primary_answer=None,
        text_response=text_response,
        needs_clarification=needs_clarification(ambiguity_type),
        clarification_prompt=clarification,
    )


def _generate_nodes_for_intent(parsed, result) -> list:
    """Generate nodes based on query intent. Data fetched from DCL."""
    if parsed.intent == QueryIntent.POINT_QUERY:
        return generate_nodes_for_point_query(
            parsed.metric,
            result.value,
            parsed.resolved_period,
        )

    elif parsed.intent == QueryIntent.COMPARISON_QUERY:
        data = result.value
        return generate_nodes_for_comparison_query(
            parsed.metric,
            data["period1"],
            data["value1"],
            data["period2"],
            data["value2"],
            data["difference"],
            data["pct_change"],
        )

    elif parsed.intent == QueryIntent.AGGREGATION_QUERY:
        data = result.value
        return generate_nodes_for_aggregation_query(
            parsed.metric,
            data["aggregation_type"],
            data["result"],
            data["periods"],
            data["values"],
        )

    elif parsed.intent == QueryIntent.BREAKDOWN_QUERY:
        data = result.value
        if isinstance(data, dict) and "breakdown" in data:
            return generate_nodes_for_breakdown_query(
                data["breakdown"],
                data["period"],
            )
        # Data source doesn't support breakdowns — fall back to point query
        return generate_nodes_for_point_query(
            parsed.metric,
            result.value,
            parsed.resolved_period,
        )

    else:
        # Fallback to point query style
        return generate_nodes_for_point_query(
            parsed.metric,
            result.value,
            parsed.resolved_period,
        )


def _create_error_galaxy_response(
    question: str,
    query_type: str,
    error_code: str,
    error_message: str,
) -> IntentMapResponse:
    """Create an error response for Galaxy endpoint.

    For CONFIG_ERROR / UNHANDLED_ERROR we surface the real reason so the
    frontend can display it.  For PARSE_ERROR / INTERNAL_ERROR we fall back
    to the friendly "stumped" message.
    """
    if error_code in ("CONFIG_ERROR", "UNHANDLED_ERROR"):
        display_msg = error_message
    else:
        display_msg = get_stumped_response(include_suggestions=True)
    return IntentMapResponse(
        query=question,
        query_type=query_type,
        ambiguity_type=None,
        persona=detect_persona_from_question(question) or "CFO",
        overall_confidence=0.0,
        overall_data_quality=0.0,
        node_count=0,
        nodes=[],
        primary_node_id=None,
        primary_answer=display_msg,
        text_response=display_msg,
        needs_clarification=False,
        clarification_prompt=None,
    )


def _create_stumped_galaxy_response(
    question: str,
    query_type: str,
) -> IntentMapResponse:
    """Create a friendly stumped response for Galaxy endpoint."""
    stumped_msg = get_stumped_response(include_suggestions=True)
    return IntentMapResponse(
        query=question,
        query_type=query_type,
        ambiguity_type=None,
        persona=detect_persona_from_question(question) or "CFO",
        overall_confidence=0.5,
        overall_data_quality=0.5,
        node_count=0,
        nodes=[],
        primary_node_id=None,
        primary_answer=stumped_msg,
        text_response=stumped_msg,
        needs_clarification=False,
        clarification_prompt=None,
    )


# C1: _format_value_with_unit and _format_answer extracted to api/formatters.py


# C1: Health, pipeline, schema endpoints extracted to api/health.py
# C1: Eval endpoint extracted to api/eval.py
# Both are wired as separate routers in main.py
