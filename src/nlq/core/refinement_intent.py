"""
Refinement Intent Detection for Self-Developing Dashboards.

Detects when a user's query is a refinement command that should modify an
existing dashboard rather than create a new one.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class RefinementType(str, Enum):
    """Types of dashboard refinements."""
    ADD_WIDGET = "add_widget"
    REMOVE_WIDGET = "remove_widget"
    CHANGE_CHART_TYPE = "change_chart_type"
    ADD_FILTER = "add_filter"
    REMOVE_FILTER = "remove_filter"
    ADD_COMPARISON = "add_comparison"
    CHANGE_TIME_RANGE = "change_time_range"
    CHANGE_DIMENSION = "change_dimension"
    NOT_REFINEMENT = "not_refinement"


@dataclass
class RefinementIntent:
    """Extracted refinement intent from a query."""
    is_refinement: bool
    refinement_type: RefinementType
    target_widget: Optional[str]  # Widget ID or "all" or None
    new_chart_type: Optional[str]
    metric_to_add: Optional[str]
    metric_to_remove: Optional[str]
    filter_dimension: Optional[str]
    filter_value: Optional[str]
    confidence: float


# Refinement trigger patterns with types
REFINEMENT_PATTERNS = {
    # Add widget patterns - specific keywords
    r"\badd\s+(?:a\s+)?(?:new\s+)?(?:kpi|card|metric|widget)\b": (RefinementType.ADD_WIDGET, 0.95),
    r"\badd\s+(?:a\s+)?(?:new\s+)?(?:chart|graph|visualization)\b": (RefinementType.ADD_WIDGET, 0.90),
    r"\binclude\s+(?:a\s+)?(?:kpi|metric)\b": (RefinementType.ADD_WIDGET, 0.85),
    r"\bshow\s+(?:me\s+)?(?:also|as well)\b": (RefinementType.ADD_WIDGET, 0.80),
    r"\bcan\s+you\s+add\b": (RefinementType.ADD_WIDGET, 0.90),

    # Add widget patterns - metric by name (e.g., "add csat trend", "add revenue card")
    r"\badd\s+(?:a\s+)?(?:\w+)\s+(?:trend|card|chart|graph)\b": (RefinementType.ADD_WIDGET, 0.90),
    r"\badd\s+(?:a\s+)?(?:\w+\s+\w+)\s+(?:trend|card|chart|graph)\b": (RefinementType.ADD_WIDGET, 0.90),
    r"\badd\s+(?:a\s+)?(?:\w+)\s+(?:kpi|widget|metric)\b": (RefinementType.ADD_WIDGET, 0.90),

    # Remove widget patterns
    r"\bremove\s+(?:the\s+)?(?:kpi|card|chart|widget)\b": (RefinementType.REMOVE_WIDGET, 0.95),
    r"\bdelete\s+(?:the\s+)?(?:kpi|card|chart|widget)\b": (RefinementType.REMOVE_WIDGET, 0.95),
    r"\bget\s+rid\s+of\b": (RefinementType.REMOVE_WIDGET, 0.90),
    r"\bhide\s+(?:the\s+)?\b": (RefinementType.REMOVE_WIDGET, 0.80),

    # Change chart type patterns
    r"\bmake\s+(?:that|it|this)\s+(?:a\s+)?(?:bar|line|pie|donut|area|table)\b": (RefinementType.CHANGE_CHART_TYPE, 0.95),
    r"\bchange\s+(?:to|it\s+to)\s+(?:a\s+)?(?:bar|line|pie|donut|area|table)\b": (RefinementType.CHANGE_CHART_TYPE, 0.95),
    r"\bconvert\s+(?:to|it\s+to)\s+(?:a\s+)?(?:bar|line|pie|donut|area|table)\b": (RefinementType.CHANGE_CHART_TYPE, 0.95),
    r"\bswitch\s+to\s+(?:a\s+)?(?:bar|line|pie|donut|area|table)\b": (RefinementType.CHANGE_CHART_TYPE, 0.90),
    r"\bas\s+a\s+(?:bar|line|pie|donut|area|table)\s+chart\b": (RefinementType.CHANGE_CHART_TYPE, 0.85),

    # Filter patterns
    r"\bfilter\s+(?:by|to|for)\b": (RefinementType.ADD_FILTER, 0.90),
    r"\bonly\s+show\s+(?:me\s+)?\b": (RefinementType.ADD_FILTER, 0.85),
    r"\bjust\s+(?:show|include)\b": (RefinementType.ADD_FILTER, 0.80),
    r"\bfor\s+(?:amer|emea|apac|enterprise|smb)\b": (RefinementType.ADD_FILTER, 0.85),

    # Remove filter patterns
    r"\bremove\s+(?:the\s+)?filter\b": (RefinementType.REMOVE_FILTER, 0.95),
    r"\bclear\s+(?:the\s+)?filter\b": (RefinementType.REMOVE_FILTER, 0.95),
    r"\bshow\s+all\b": (RefinementType.REMOVE_FILTER, 0.80),

    # Comparison patterns
    r"\bcompare\s+(?:to|with)\s+(?:last|prior|previous)\b": (RefinementType.ADD_COMPARISON, 0.90),
    r"\badd\s+(?:a\s+)?comparison\b": (RefinementType.ADD_COMPARISON, 0.90),
    r"\bversus\s+(?:last|prior|previous)\b": (RefinementType.ADD_COMPARISON, 0.85),
    r"\bvs\s+(?:last|prior|previous)\b": (RefinementType.ADD_COMPARISON, 0.85),

    # Time range patterns
    r"\bchange\s+(?:the\s+)?(?:time|period|range)\b": (RefinementType.CHANGE_TIME_RANGE, 0.90),
    r"\bfor\s+(?:last|this)\s+(?:year|quarter|month)\b": (RefinementType.CHANGE_TIME_RANGE, 0.80),
    r"\bshow\s+(?:me\s+)?(?:last|this)\s+(?:year|quarter|month)\b": (RefinementType.CHANGE_TIME_RANGE, 0.75),

    # Change dimension patterns
    r"\bby\s+(?:region|rep|product|segment|stage)\s+instead\b": (RefinementType.CHANGE_DIMENSION, 0.90),
    r"\bchange\s+(?:it\s+)?to\s+by\s+\b": (RefinementType.CHANGE_DIMENSION, 0.85),
    r"\bbreak\s+(?:it\s+)?down\s+by\b": (RefinementType.CHANGE_DIMENSION, 0.85),
    r"\bbreak\s+(?:that|this)\s+down\s+by\b": (RefinementType.CHANGE_DIMENSION, 0.90),
}

# Pronoun patterns that indicate referencing existing dashboard
PRONOUN_PATTERNS = [
    r"\b(?:make|change|convert)\s+(?:that|it|this)\b",
    r"\b(?:to|into)\s+(?:the|a)\s+\w+\s+(?:chart|graph)\b",
    r"\bthe\s+(?:chart|graph|dashboard|widget|kpi)\b",
    r"\bcurrent\s+(?:dashboard|view|chart)\b",
]

# Chart type extraction patterns
CHART_TYPE_PATTERNS = {
    r"\bbar\s*(?:chart|graph)?\b": "bar_chart",
    r"\bline\s*(?:chart|graph)?\b": "line_chart",
    r"\bpie\s*(?:chart)?\b": "donut_chart",
    r"\bdonut\s*(?:chart)?\b": "donut_chart",
    r"\barea\s*(?:chart)?\b": "area_chart",
    r"\btable\b": "data_table",
    r"\bkpi\b": "kpi_card",
    r"\bstacked\b": "stacked_bar",
}

# Metric extraction patterns (simplified)
METRIC_PATTERNS = {
    r"\brevenue\b": "revenue",
    r"\bpipeline\b": "pipeline",
    r"\bwin\s*rate\b": "win_rate",
    r"\bmargin\b": "gross_margin_pct",
    r"\bgross\s*margin\b": "gross_margin_pct",
    r"\bnet\s*income\b": "net_income",
    r"\bchurn\b": "gross_churn_pct",
    r"\bnrr\b": "nrr",
    r"\bnet\s*retention\b": "nrr",
    r"\bretention\b": "nrr",
    r"\bheadcount\b": "headcount",
    r"\bhiring\b": "headcount",
    r"\barr\b": "arr",
    r"\bcustomer\s*count\b": "customer_count",
    r"\bcustomers\b": "customer_count",
    r"\bquota\b": "quota_attainment",
    r"\bsales\s*cycle\b": "sales_cycle_days",
    r"\bcsat\b": "csat",
    r"\btech\s*debt\b": "tech_debt_pct",
    r"\buptime\b": "uptime_pct",
    r"\btraining\s*hours\b": "training_hours_per_employee",
    r"\bfeatures\b": "features_shipped",
}


def detect_refinement_intent(query: str, has_current_dashboard: bool = False) -> RefinementIntent:
    """
    Detect if a query is a refinement command.

    Args:
        query: The user's natural language query
        has_current_dashboard: Whether there's a current dashboard to refine

    Returns:
        RefinementIntent with detected refinement type and parameters
    """
    q = query.lower().strip()

    # Check for pronoun patterns that reference existing dashboard
    has_pronoun_reference = any(re.search(p, q) for p in PRONOUN_PATTERNS)

    # If no current dashboard and uses pronouns, this needs context
    if has_pronoun_reference and not has_current_dashboard:
        return RefinementIntent(
            is_refinement=False,
            refinement_type=RefinementType.NOT_REFINEMENT,
            target_widget=None,
            new_chart_type=None,
            metric_to_add=None,
            metric_to_remove=None,
            filter_dimension=None,
            filter_value=None,
            confidence=0.0,
        )

    # Find best matching refinement pattern
    best_type = RefinementType.NOT_REFINEMENT
    best_confidence = 0.0

    for pattern, (ref_type, confidence) in REFINEMENT_PATTERNS.items():
        if re.search(pattern, q, re.IGNORECASE):
            if confidence > best_confidence:
                best_type = ref_type
                best_confidence = confidence

    # If we found a refinement pattern, this is a refinement
    is_refinement = best_type != RefinementType.NOT_REFINEMENT

    # Extract additional details based on refinement type
    new_chart_type = None
    metric_to_add = None
    metric_to_remove = None
    filter_dimension = None
    filter_value = None

    if best_type == RefinementType.CHANGE_CHART_TYPE:
        new_chart_type = _extract_chart_type(q)

    if best_type in [RefinementType.ADD_WIDGET, RefinementType.REMOVE_WIDGET]:
        metric_to_add = _extract_metric(q)
        metric_to_remove = _extract_metric(q) if best_type == RefinementType.REMOVE_WIDGET else None

    if best_type == RefinementType.ADD_FILTER:
        filter_dimension, filter_value = _extract_filter(q)

    # Boost confidence if there's a current dashboard and pronoun reference
    if has_current_dashboard and has_pronoun_reference:
        best_confidence = min(1.0, best_confidence + 0.1)

    return RefinementIntent(
        is_refinement=is_refinement and has_current_dashboard,
        refinement_type=best_type,
        target_widget=None,  # Would need more context to determine specific widget
        new_chart_type=new_chart_type,
        metric_to_add=metric_to_add,
        metric_to_remove=metric_to_remove,
        filter_dimension=filter_dimension,
        filter_value=filter_value,
        confidence=best_confidence,
    )


def _extract_chart_type(query: str) -> Optional[str]:
    """Extract the target chart type from a query."""
    for pattern, chart_type in CHART_TYPE_PATTERNS.items():
        if re.search(pattern, query, re.IGNORECASE):
            return chart_type
    return None


def _extract_metric(query: str) -> Optional[str]:
    """Extract a metric name from a query using DCL semantic client."""
    try:
        from src.nlq.services.dcl_semantic_client import get_semantic_client
        semantic_client = get_semantic_client()

        # Try to find a metric in the query
        words = query.lower().split()
        for i in range(len(words)):
            # Try 2-word phrases
            if i + 1 < len(words):
                phrase = " ".join(words[i:i+2])
                resolved = semantic_client.resolve_metric(phrase)
                if resolved:
                    return resolved.id

            # Try single words
            resolved = semantic_client.resolve_metric(words[i])
            if resolved:
                return resolved.id
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"DCL metric extraction failed, using legacy patterns: {e}")

    # Legacy fallback - use pattern matching
    for pattern, metric in METRIC_PATTERNS.items():
        if re.search(pattern, query, re.IGNORECASE):
            return metric
    return None


def _extract_filter(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract filter dimension and value from a query."""
    # Region filters
    region_match = re.search(r"\b(amer|emea|apac)\b", query, re.IGNORECASE)
    if region_match:
        return "region", region_match.group(1).upper()

    # Segment filters
    segment_match = re.search(r"\b(enterprise|mid-market|smb)\b", query, re.IGNORECASE)
    if segment_match:
        return "segment", segment_match.group(1).title()

    # Product filters
    product_match = re.search(r"\b(professional|team|starter)\b", query, re.IGNORECASE)
    if product_match:
        return "product", product_match.group(1).title()

    return None, None


def is_context_dependent_query(query: str) -> bool:
    """
    Check if a query requires context to understand.

    Returns True for queries like "make it a bar chart" that reference
    something not specified in the query itself.
    """
    q = query.lower()

    # Pronoun references without object specification
    if re.search(r"\b(?:make|change|convert)\s+(?:that|it|this)\b", q):
        return True

    # "break that/it down by" patterns - references previous context
    if re.search(r"\bbreak\s+(?:that|it|this)\s+down\b", q):
        return True

    # "drill into that" or "dig into that" patterns
    if re.search(r"\b(?:drill|dig)\s+(?:into|down)\s+(?:that|it|this)\b", q):
        return True

    # "the chart" without specifying which
    if re.search(r"\bthe\s+(?:chart|graph|dashboard)\b", q) and "show" not in q:
        return True

    return False


def needs_clarification_without_context(query: str) -> Optional[str]:
    """
    Generate a clarification prompt for context-dependent queries.

    Returns a prompt asking what the user wants to modify, or None if
    the query doesn't need clarification.
    """
    if not is_context_dependent_query(query):
        return None

    q = query.lower()

    if "bar" in q:
        return "I'd be happy to create a bar chart. What data would you like to visualize? For example, 'Show me revenue by region as a bar chart'."

    if "line" in q:
        return "I can create a line chart for you. What metric would you like to see over time? For example, 'Show me pipeline trend as a line chart'."

    if re.search(r"\bmake\s+(?:that|it)\b", q):
        return "What would you like me to change? Please describe what visualization you'd like to create or modify."

    # Handle "break that down by" without context
    if re.search(r"\bbreak\s+(?:that|it|this)\s+down\b", q):
        # Extract the dimension if present
        dim_match = re.search(r"\bby\s+(region|rep|product|segment|stage)\b", q)
        if dim_match:
            dim = dim_match.group(1)
            return f"I don't have a current visualization to break down by {dim}. What would you like to see? For example, 'Show me pipeline by {dim}' or 'Show me revenue by {dim}'."
        return "I don't have a current visualization to break down. What would you like to see? For example, 'Show me pipeline by stage' or 'Show me revenue by region'."

    return "I don't have a current dashboard to modify. What would you like to visualize? For example, 'Show me revenue over time' or 'Build me a sales dashboard'."
