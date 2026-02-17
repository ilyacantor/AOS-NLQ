"""
Tiered Intent Recognition for NLQ queries.

This module implements a cost-optimized intent resolution strategy:

    Tier 1: FREE (no API calls)
    ├── RAG Cache hit (>0.85 similarity)
    ├── Off-topic filter (keyword-based)
    └── Canonical metric lookup (exact string match)

    Tier 2: CHEAP (~$0.0001/query)
    └── Embedding-based metric classification

    Tier 3: EXPENSIVE (~$0.003+/query)
    └── Full LLM parse (Claude)

The goal is to resolve simple queries without expensive LLM calls while
ensuring complex queries still get proper handling.

Usage:
    resolver = TieredIntentResolver(cache_service, query_parser)
    result = await resolver.resolve("what is our ebitda")

    if result.tier == 1:
        print(f"Cache hit! Saved ${0.003}")
    elif result.tier == 2:
        print(f"Embedding match! Cost: ~$0.0001")
    else:
        print(f"LLM parse required, cost: ~$0.003+")
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from src.nlq.services.query_cache_service import QueryCacheService
    from src.nlq.llm.parser import QueryParser

logger = logging.getLogger(__name__)


class ResolutionTier(int, Enum):
    """Which tier resolved the query."""
    TIER_1_FREE = 1      # Cache hit or exact match
    TIER_2_EMBEDDING = 2  # Embedding-based metric lookup
    TIER_3_LLM = 3       # Full LLM parse


class QueryComplexity(str, Enum):
    """Detected query complexity."""
    SIMPLE_METRIC = "simple_metric"      # "ebitda", "revenue"
    METRIC_WITH_PERIOD = "metric_period" # "Q3 revenue", "2024 margin"
    COMPARISON = "comparison"            # "vs last year", "compared to"
    TREND = "trend"                      # "over time", "trend"
    BREAKDOWN = "breakdown"              # "by region", "breakdown"
    SUPERLATIVE = "superlative"          # "top rep", "largest deal", "worst service"
    COMPLEX = "complex"                  # Anything else


@dataclass
class IntentResolutionResult:
    """Result from tiered intent resolution."""
    tier: ResolutionTier
    success: bool
    intent: Optional[str] = None
    metric: Optional[str] = None
    period: Optional[str] = None
    parsed_query: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    cost_estimate: float = 0.0  # Estimated API cost in dollars
    source: str = ""  # "cache", "embedding", "llm", "exact_match"
    complexity: QueryComplexity = QueryComplexity.SIMPLE_METRIC
    error: Optional[str] = None

    # For embedding tier
    embedding_similarity: Optional[float] = None
    matched_term: Optional[str] = None


# Keywords that indicate complex queries requiring LLM
COMPLEXITY_INDICATORS = {
    QueryComplexity.COMPARISON: [
        "vs", "versus", "compared to", "compare", "vs.", "against",
        "relative to", "difference", "change from", "grew", "declined",
    ],
    QueryComplexity.TREND: [
        "trend", "over time", "historical", "trajectory", "growth rate",
        "quarter over quarter", "qoq", "yoy", "year over year", "monthly",
    ],
    QueryComplexity.BREAKDOWN: [
        "breakdown", "by region", "by segment", "by product", "by team",
        "split", "composition", "drivers", "what's driving", "components",
    ],
    QueryComplexity.SUPERLATIVE: [
        # Max/best patterns
        "top rep", "best rep", "top sales", "best sales", "#1 rep",
        "top performer", "best performer", "leading performer",
        "highest", "largest", "biggest", "most", "best",
        "top 3", "top 5", "top 10",
        # Min/worst patterns
        "worst", "lowest", "smallest", "least", "bottom",
        "weakest", "lagging", "bottom 3", "bottom 5", "bottom 10",
        # Casual patterns
        "crushing it", "mvp", "star performer",
    ],
    QueryComplexity.COMPLEX: [
        # Bridge/analysis queries - explain why metrics changed
        "why did", "why has", "why is", "explain why", "explain how",
        "what caused", "what drove", "what factors",
        "increase", "decrease", "drop", "rise", "fell", "grew",
        "declined", "improved", "worsened", "changed",
        "bridge", "waterfall",
    ],
}


def detect_complexity(query: str) -> QueryComplexity:
    """
    Detect query complexity to determine if LLM is needed.

    Simple metric queries can be resolved with embeddings.
    Complex queries need LLM for proper parsing.
    """
    query_lower = query.lower()

    for complexity_type, indicators in COMPLEXITY_INDICATORS.items():
        for indicator in indicators:
            if indicator in query_lower:
                return complexity_type

    # Check for period references (still simple if just current period)
    period_words = ["q1", "q2", "q3", "q4", "2024", "2025", "last quarter",
                    "this quarter", "last year", "this year", "ytd"]
    has_period = any(p in query_lower for p in period_words)

    if has_period:
        return QueryComplexity.METRIC_WITH_PERIOD

    return QueryComplexity.SIMPLE_METRIC


class TieredIntentResolver:
    """
    Resolves query intent using a tiered approach.

    Tries cheaper methods first, falling back to LLM only when necessary.
    """

    def __init__(
        self,
        cache_service: Optional["QueryCacheService"] = None,
        query_parser: Optional["QueryParser"] = None,
    ):
        self.cache_service = cache_service
        self.query_parser = query_parser
        self._metric_index = None

    async def _get_metric_index(self):
        """Lazy-load metric embedding index."""
        if self._metric_index is None:
            from src.nlq.services.metric_embedding_index import get_metric_embedding_index
            self._metric_index = get_metric_embedding_index()
            if not self._metric_index.is_initialized:
                await self._metric_index.initialize()
        return self._metric_index

    async def resolve(self, query: str) -> IntentResolutionResult:
        """
        Resolve query intent using tiered approach.

        Args:
            query: User's natural language query

        Returns:
            IntentResolutionResult with resolved intent and metadata
        """
        # Detect complexity first
        complexity = detect_complexity(query)

        # Complex queries go straight to LLM (Tier 3)
        if complexity in (QueryComplexity.COMPARISON, QueryComplexity.TREND,
                          QueryComplexity.BREAKDOWN, QueryComplexity.SUPERLATIVE,
                          QueryComplexity.COMPLEX):
            return await self._tier_3_llm_parse(query, complexity)

        # Tier 1: Try cache first (FREE)
        tier_1_result = await self._tier_1_cache_lookup(query)
        if tier_1_result and tier_1_result.success:
            tier_1_result.complexity = complexity
            return tier_1_result

        # Tier 1b: Try exact metric match (FREE)
        tier_1b_result = self._tier_1_exact_match(query)
        if tier_1b_result and tier_1b_result.success:
            tier_1b_result.complexity = complexity
            return tier_1b_result

        # Tier 2: Try embedding-based lookup (CHEAP)
        tier_2_result = await self._tier_2_embedding_lookup(query)
        if tier_2_result and tier_2_result.success:
            tier_2_result.complexity = complexity
            return tier_2_result

        # Tier 3: Fall back to LLM (EXPENSIVE)
        return await self._tier_3_llm_parse(query, complexity)

    async def _tier_1_cache_lookup(self, query: str) -> Optional[IntentResolutionResult]:
        """Tier 1: Check RAG cache for similar queries."""
        if not self.cache_service or not self.cache_service.is_available:
            return None

        try:
            cache_result = self.cache_service.lookup(query)

            if cache_result.high_confidence and cache_result.parsed:
                return IntentResolutionResult(
                    tier=ResolutionTier.TIER_1_FREE,
                    success=True,
                    intent=cache_result.parsed.get("intent"),
                    metric=cache_result.parsed.get("metric"),
                    period=cache_result.parsed.get("period_reference"),
                    parsed_query=cache_result.parsed,
                    confidence=cache_result.confidence,
                    cost_estimate=0.0,
                    source="cache",
                    embedding_similarity=cache_result.similarity,
                )
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.warning(f"Cache lookup failed: {e}")

        return None

    def _tier_1_exact_match(self, query: str) -> Optional[IntentResolutionResult]:
        """Tier 1b: Check for exact metric name match."""
        from src.nlq.knowledge.synonyms import normalize_metric

        query_normalized = query.lower().strip()

        # Try direct metric resolution
        resolved = normalize_metric(query_normalized)
        if resolved:
            return IntentResolutionResult(
                tier=ResolutionTier.TIER_1_FREE,
                success=True,
                intent="POINT_QUERY",
                metric=resolved,
                period="2025",  # Default to current year
                parsed_query={
                    "intent": "POINT_QUERY",
                    "metric": resolved,
                    "period_type": "FULL_YEAR",
                    "period_reference": "CURRENT",
                    "period_year": 2025,
                },
                confidence=0.95,
                cost_estimate=0.0,
                source="exact_match",
                matched_term=query_normalized,
            )

        return None

    async def _tier_2_embedding_lookup(self, query: str) -> Optional[IntentResolutionResult]:
        """Tier 2: Use embedding similarity to match metrics."""
        try:
            metric_index = await self._get_metric_index()
            if not metric_index or not metric_index.is_initialized:
                return None

            result = await metric_index.lookup(query)

            if result and result.is_high_confidence:
                return IntentResolutionResult(
                    tier=ResolutionTier.TIER_2_EMBEDDING,
                    success=True,
                    intent="POINT_QUERY",
                    metric=result.canonical_metric,
                    period="2025",  # Default to current year
                    parsed_query={
                        "intent": "POINT_QUERY",
                        "metric": result.canonical_metric,
                        "period_type": "FULL_YEAR",
                        "period_reference": "CURRENT",
                        "period_year": 2025,
                    },
                    confidence=result.confidence,
                    cost_estimate=0.0001,  # Approximate OpenAI embedding cost
                    source="embedding",
                    embedding_similarity=result.similarity,
                    matched_term=result.matched_term,
                )

        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.warning(f"Embedding lookup failed: {e}")

        return None

    async def _tier_3_llm_parse(
        self,
        query: str,
        complexity: QueryComplexity
    ) -> IntentResolutionResult:
        """Tier 3: Full LLM parse for complex queries."""
        if not self.query_parser:
            return IntentResolutionResult(
                tier=ResolutionTier.TIER_3_LLM,
                success=False,
                error="No LLM parser available",
                cost_estimate=0.0,
                source="llm",
                complexity=complexity,
            )

        try:
            # This calls Claude
            parsed = self.query_parser.parse(query)

            return IntentResolutionResult(
                tier=ResolutionTier.TIER_3_LLM,
                success=True,
                intent=parsed.intent.value if parsed.intent else None,
                metric=parsed.metric,
                period=parsed.resolved_period,
                parsed_query=parsed.model_dump() if hasattr(parsed, 'model_dump') else None,
                confidence=0.95,  # Claude parses are high confidence
                cost_estimate=0.003,  # Approximate Claude cost
                source="llm",
                complexity=complexity,
            )

        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"LLM parse failed: {e}")
            return IntentResolutionResult(
                tier=ResolutionTier.TIER_3_LLM,
                success=False,
                error=str(e),
                cost_estimate=0.003,  # Still charged for failed requests
                source="llm",
                complexity=complexity,
            )


# Convenience function for use in routes
async def resolve_intent(
    query: str,
    cache_service: Optional["QueryCacheService"] = None,
    query_parser: Optional["QueryParser"] = None,
) -> IntentResolutionResult:
    """
    Resolve query intent using tiered approach.

    This is the main entry point for the tiered intent system.
    """
    resolver = TieredIntentResolver(cache_service, query_parser)
    return await resolver.resolve(query)
