"""
Superlative Intent Detection for NLQ queries.

Detects ranking/superlative queries like:
- "Who is our top rep?"
- "What's our largest deal?"
- "Which region has the most revenue?"
- "What's our worst performing service?"

This module extracts:
- superlative_type: max, min, top_n, bottom_n
- metric: what to rank by (quota_attainment, win_rate, revenue, etc.)
- dimension: what entities to rank (rep, region, service, etc.)
- limit: how many results (default 1 for superlatives, N for "top N")
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class SuperlativeType(str, Enum):
    """Type of superlative/ranking query."""
    MAX = "max"           # highest, largest, best, top, #1
    MIN = "min"           # lowest, smallest, worst, bottom
    TOP_N = "top_n"       # top 5, top 10
    BOTTOM_N = "bottom_n" # bottom 5, bottom 10


@dataclass
class RankingIntent:
    """Structured ranking intent extracted from query."""
    metric: str                    # e.g., "quota_attainment_pct", "win_rate_pct", "pipeline"
    dimension: str                 # e.g., "rep", "region", "service", "department"
    ranking_type: SuperlativeType  # "max", "min", "top_n", "bottom_n"
    limit: int = 1                 # How many results
    time_range: Optional[Dict[str, Any]] = None  # Optional: {"period": "2026-Q4"}
    raw_query: str = ""            # Original query text


# Metrics where lower is better (for "best"/"worst" interpretation)
LOWER_IS_BETTER_METRICS = {
    "churn", "churn_pct", "gross_churn_pct", "logo_churn_pct",
    "attrition", "attrition_rate_pct",
    "cycle_time", "sales_cycle_days",
    "mttr", "mttr_p1_hours", "mttr_p2_hours",
    "incidents", "p1_incidents", "p2_incidents",
    "tech_debt", "tech_debt_pct",
    "bug_escape_rate", "critical_bugs",
    "time_to_fill_days", "lead_time_days",
    "downtime_hours",
}

# Pattern mapping for superlative keywords
SUPERLATIVE_PATTERNS = {
    # Max patterns (descending order, return highest)
    SuperlativeType.MAX: [
        r"(?:who|which|what)(?:'s| is) (?:the |our )?(?:top|best|highest|#1|leading|number one) (.+)",
        r"(?:who|which|what) (?:has|have) the (?:most|highest|largest|biggest|best) (.+)",
        r"which (.+) has the (?:most|highest|largest|biggest) (.+)",
        r"which (.+) is (?:largest|biggest|highest|best)",
        r"which (.+) (?:\w+s) the most",
        r"what (?:is|was) (?:the |our )?(?:largest|biggest|highest|best) (.+)",
        r"largest (.+)",
        r"biggest (.+)",
        r"highest (.+)",
        r"best (.+)",
        r"top (.+)",
        r"leading (.+)",
        r"(?:who|what|which)(?:'s| is) crushing it",
        r"(?:who|what|which)(?:'s| is) (?:our |the )?mvp",
        r"(?:who|what|which)(?:'s| is) (?:our |the )?star performer",
    ],
    # Min patterns (ascending order, return lowest)
    SuperlativeType.MIN: [
        r"(?:who|which|what)(?:'s| is) (?:the |our )?(?:worst|lowest|bottom|weakest|lagging) (.+)",
        r"(?:who|which|what) (?:has|have) the (?:least|lowest|smallest|fewest|worst) (.+)",
        r"which (.+) has the (?:least|lowest|smallest|fewest) (.+)",
        r"which (.+) is (?:smallest|lowest|worst)",
        r"lowest (.+)",
        r"smallest (.+)",
        r"worst (.+)",
        r"weakest (.+)",
        r"(?:what|which)(?:'s| is) (?:our |the )?(?:biggest )?problem (.+)",
    ],
    # Top N patterns
    SuperlativeType.TOP_N: [
        r"top (\d+) (.+)",
        r"(\d+) (?:best|top|highest) (.+)",
        r"(?:show|list|get|give)(?: me)? (?:the )?top (\d+) (.+)",
        r"(?:who|what|which) are the top (\d+) (.+)",
    ],
    # Bottom N patterns
    SuperlativeType.BOTTOM_N: [
        r"bottom (\d+) (.+)",
        r"(\d+) (?:worst|lowest|bottom) (.+)",
        r"(?:show|list|get|give)(?: me)? (?:the )?bottom (\d+) (.+)",
        r"(?:who|what|which) are the bottom (\d+) (.+)",
    ],
}

# Dimension aliases - map user terms to canonical dimension names
DIMENSION_ALIASES = {
    # Rep/salesperson
    "rep": "rep", "reps": "rep",
    "sales rep": "rep", "sales reps": "rep",
    "salesperson": "rep", "salespeople": "rep",
    "representative": "rep", "representatives": "rep",
    "performer": "rep", "performers": "rep",
    "seller": "rep", "sellers": "rep",
    # Region
    "region": "region", "regions": "region",
    "territory": "region", "territories": "region",
    "geo": "region", "geography": "region",
    "area": "region", "areas": "region",
    # Segment
    "segment": "segment", "segments": "segment",
    "market": "segment", "markets": "segment",
    "vertical": "segment", "verticals": "segment",
    # Service
    "service": "service", "services": "service",
    "system": "service", "systems": "service",
    # Department
    "department": "department", "departments": "department",
    "org": "department",
    # Team (engineering teams — distinct from department)
    "team": "team", "teams": "team",
    # Deal
    "deal": "deal", "deals": "deal",
    "opportunity": "deal", "opportunities": "deal",
    # Stage
    "stage": "stage", "stages": "stage",
    "pipeline stage": "stage",
    # Customer / Account
    "customer": "customer", "customers": "customer",
    "account": "customer", "accounts": "customer",
    "client": "customer", "clients": "customer",
    # Product
    "product": "product", "products": "product",
    # Category
    "category": "category", "categories": "category",
    # Cohort → segment
    "cohort": "segment", "cohorts": "segment",
}

# Metric aliases for ranking queries
METRIC_ALIASES = {
    # Quota/Performance
    "quota attainment": "quota_attainment_pct",
    "quota": "quota_attainment_pct",
    "attainment": "quota_attainment_pct",
    "performance": "quota_attainment_pct",
    # Win rate
    "win rate": "win_rate_pct",
    "close rate": "win_rate_pct",
    "conversion": "win_rate_pct",
    # Pipeline
    "pipeline": "pipeline",
    "pipe": "pipeline",
    "opportunities": "pipeline",
    # Revenue
    "revenue": "revenue",
    "sales": "revenue",
    # SLO
    "slo": "slo_attainment_pct",
    "slo attainment": "slo_attainment_pct",
    "uptime": "slo_attainment_pct",
    "reliability": "slo_attainment_pct",
    # Headcount
    "headcount": "headcount",
    "employees": "headcount",
    "people": "headcount",
    "staff": "headcount",
    # Deal value
    "deal value": "deal_value",
    "value": "deal_value",
    "deal size": "deal_value",
    # Churn — use DCL's canonical ID directly (avoids crossmap hop)
    "churn": "churn_rate_pct",
    "churn rate": "churn_rate_pct",
    "customer churn": "churn_rate_pct",
    "gross churn": "gross_churn_pct",
    "logo churn": "logo_churn_pct",
    "churn risk": "churn_risk",
    # Gross margin
    "gross margin": "gross_margin_pct",
    "margin": "gross_margin_pct",
    # Deploy frequency
    "deploy frequency": "deploys_per_week",
    "deploys": "deploys_per_week",
    "deployments": "deploys_per_week",
    # SLA / SLO
    "sla compliance": "slo_attainment_pct",
    "sla": "slo_attainment_pct",
    # Throughput / Velocity
    "throughput": "sprint_velocity",
    "velocity": "sprint_velocity",
    # DSO
    "dso": "dso",
    "days sales outstanding": "dso",
    # NRR
    "nrr": "nrr",
    "net revenue retention": "nrr",
    "net retention": "nrr",
}


def is_superlative_query(query: str) -> bool:
    """
    Check if a query is a superlative/ranking query.

    Args:
        query: Natural language query

    Returns:
        True if query contains superlative patterns
    """
    query_lower = query.lower().strip()

    # Exclude known metric synonyms that contain superlative words
    # "top line" = revenue, "bottom line" = net income — NOT ranking queries
    metric_phrases = ["top line", "top-line", "topline", "bottom line", "bottom-line", "bottomline"]
    for phrase in metric_phrases:
        if phrase in query_lower:
            return False

    # Check for superlative keywords
    superlative_keywords = [
        "top", "best", "highest", "largest", "biggest", "most", "leading", "#1",
        "worst", "lowest", "smallest", "least", "bottom", "weakest", "lagging",
        "top 3", "top 5", "top 10", "bottom 3", "bottom 5", "bottom 10",
        "crushing it", "mvp", "star performer",
    ]

    for keyword in superlative_keywords:
        if keyword in query_lower:
            return True

    # Check for "who is our" patterns that often indicate ranking
    who_patterns = [
        r"who(?:'s| is) (?:our|the) (?:top|best|worst|#1)",
        r"which .+ has the (?:most|highest|lowest|least)",
        r"what(?:'s| is) (?:our|the) (?:largest|biggest|smallest)",
    ]

    for pattern in who_patterns:
        if re.search(pattern, query_lower):
            return True

    return False


def detect_superlative_intent(query: str) -> Optional[RankingIntent]:
    """
    Detect and extract ranking intent from a query.

    Args:
        query: Natural language query

    Returns:
        RankingIntent if superlative detected, None otherwise
    """
    query_lower = query.lower().strip()

    # First, check for Top N / Bottom N patterns (need to extract N)
    for ranking_type in [SuperlativeType.TOP_N, SuperlativeType.BOTTOM_N]:
        for pattern in SUPERLATIVE_PATTERNS[ranking_type]:
            match = re.search(pattern, query_lower)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    limit = int(groups[0])
                    remainder = groups[1]
                else:
                    limit = int(groups[0]) if groups[0].isdigit() else 5
                    remainder = groups[-1] if len(groups) > 0 else ""

                dimension, metric = _extract_dimension_and_metric(remainder, query_lower)

                return RankingIntent(
                    metric=metric,
                    dimension=dimension,
                    ranking_type=ranking_type,
                    limit=limit,
                    raw_query=query,
                )

    # Check for Max/Min patterns
    for ranking_type in [SuperlativeType.MAX, SuperlativeType.MIN]:
        for pattern in SUPERLATIVE_PATTERNS[ranking_type]:
            match = re.search(pattern, query_lower)
            if match:
                # Handle special patterns like "crushing it", "mvp"
                if "crushing it" in query_lower or "mvp" in query_lower or "star performer" in query_lower:
                    return RankingIntent(
                        metric="quota_attainment_pct",
                        dimension="rep",
                        ranking_type=SuperlativeType.MAX,
                        limit=1,
                        raw_query=query,
                    )

                groups = match.groups()

                # Handle patterns with two groups like "which (region) has the most (revenue)"
                if len(groups) >= 2:
                    dimension_part = groups[0].strip()
                    metric_part = groups[1].strip()

                    # Resolve dimension from first group
                    dimension = "rep"  # default
                    for alias, canonical in DIMENSION_ALIASES.items():
                        if alias in dimension_part:
                            dimension = canonical
                            break

                    # Resolve metric from second group
                    metric = "quota_attainment_pct"  # default
                    for alias, canonical in METRIC_ALIASES.items():
                        if alias in metric_part:
                            metric = canonical
                            break

                    return RankingIntent(
                        metric=metric,
                        dimension=dimension,
                        ranking_type=ranking_type,
                        limit=1,
                        raw_query=query,
                    )

                # Single group - check if it's a "which X is largest/smallest" pattern
                remainder = groups[0] if groups else ""

                # Check if the captured group is just a dimension (e.g., "segment" in "which segment is largest")
                dimension_only = False
                for alias, canonical in DIMENSION_ALIASES.items():
                    if remainder.strip() == alias or remainder.strip() == canonical:
                        dimension_only = True
                        dimension = canonical
                        # Infer metric from dimension
                        if dimension == "segment":
                            metric = "revenue"
                        elif dimension == "region":
                            metric = "revenue"
                        elif dimension == "department":
                            metric = "headcount"
                        elif dimension == "team":
                            metric = "sprint_velocity"
                        elif dimension == "service":
                            metric = "slo_attainment_pct"
                        elif dimension == "rep":
                            metric = "quota_attainment_pct"
                        elif dimension == "deal":
                            metric = "deal_value"
                        elif dimension == "stage":
                            metric = "pipeline"
                        elif dimension == "customer":
                            metric = "churn_risk"
                        elif dimension == "product":
                            metric = "gross_margin_pct"
                        elif dimension == "category":
                            metric = "cloud_spend"
                        else:
                            metric = "revenue"  # default
                        break

                if not dimension_only:
                    dimension, metric = _extract_dimension_and_metric(remainder, query_lower)

                # Handle "best"/"worst" inversion for metrics where lower is better
                actual_type = ranking_type
                if any(m in metric for m in LOWER_IS_BETTER_METRICS):
                    if ranking_type == SuperlativeType.MAX and "best" in query_lower:
                        actual_type = SuperlativeType.MIN  # "best churn" means lowest
                    elif ranking_type == SuperlativeType.MIN and "worst" in query_lower:
                        actual_type = SuperlativeType.MAX  # "worst churn" means highest

                return RankingIntent(
                    metric=metric,
                    dimension=dimension,
                    ranking_type=actual_type,
                    limit=1,
                    raw_query=query,
                )

    return None


def _extract_dimension_and_metric(
    remainder: str,
    full_query: str
) -> Tuple[str, str]:
    """
    Extract dimension and metric from the matched remainder.

    Args:
        remainder: The captured text after the superlative keyword
        full_query: The full query for context

    Returns:
        Tuple of (dimension, metric)
    """
    remainder = remainder.strip()

    # Default dimension and metric
    dimension = "rep"
    metric = "quota_attainment_pct"

    # Check for explicit metric mentions FIRST (higher priority)
    metric_found = False
    for alias, canonical in METRIC_ALIASES.items():
        if alias in remainder or alias in full_query:
            metric = canonical
            metric_found = True
            break

    # Check for explicit dimension mentions
    for alias, canonical in DIMENSION_ALIASES.items():
        if alias in remainder or alias in full_query:
            dimension = canonical
            break

    # Infer metric from dimension if not explicitly mentioned
    if not metric_found:
        if dimension == "rep":
            metric = "quota_attainment_pct"
            if "win rate" in full_query or "close rate" in full_query:
                metric = "win_rate_pct"
            elif "pipeline" in full_query or "pipe" in full_query:
                metric = "pipeline"
            elif "revenue" in full_query or "sales" in full_query:
                metric = "revenue"
        elif dimension == "service":
            metric = "slo_attainment_pct"
        elif dimension == "region":
            metric = "revenue"
            if "pipeline" in full_query:
                metric = "pipeline"
        elif dimension == "segment":
            metric = "revenue"
        elif dimension == "department":
            metric = "headcount"
        elif dimension == "team":
            metric = "sprint_velocity"
        elif dimension == "deal":
            metric = "deal_value"
        elif dimension == "stage":
            metric = "pipeline"
        elif dimension == "customer":
            metric = "churn_risk"
        elif dimension == "product":
            metric = "gross_margin_pct"
        elif dimension == "category":
            metric = "cloud_spend"

    return dimension, metric


def get_sort_order(ranking_type: SuperlativeType) -> str:
    """
    Get the sort order for a ranking type.

    Args:
        ranking_type: The type of ranking

    Returns:
        "desc" for max/top_n, "asc" for min/bottom_n
    """
    if ranking_type in (SuperlativeType.MAX, SuperlativeType.TOP_N):
        return "desc"
    return "asc"


def format_ranking_result(
    ranking_intent: RankingIntent,
    data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Format ranking query results.

    Args:
        ranking_intent: The detected ranking intent
        data: The ranked data from DCL

    Returns:
        Formatted result dict
    """
    return {
        "query": ranking_intent.raw_query,
        "ranking_type": ranking_intent.ranking_type.value,
        "dimension": ranking_intent.dimension,
        "metric": ranking_intent.metric,
        "limit": ranking_intent.limit,
        "data": [
            {
                "rank": i + 1,
                **item
            }
            for i, item in enumerate(data[:ranking_intent.limit])
        ],
        "metadata": {
            "total_count": len(data),
            "order": get_sort_order(ranking_intent.ranking_type),
        }
    }
