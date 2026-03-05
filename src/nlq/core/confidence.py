"""
Confidence scoring for AOS-NLQ.

CRITICAL REQUIREMENT: ALL confidence scores MUST be bounded [0.0, 1.0].
The bounded_confidence() function MUST be used anywhere confidence is calculated.

Confidence is calculated based on:
- Intent clarity (0-1): How clear is what they're asking?
- Entity match (0-1): Did we find the metric/period they referenced?
- Data availability (0-1): Do we have data for that period?

Final score = weighted average, ALWAYS clamped to [0, 1]
"""

import math
from typing import Optional


def bounded_confidence(score) -> float:
    """
    Ensure confidence is always in [0, 1] range.

    CRITICAL: Use this function EVERYWHERE confidence is calculated or returned.

    Args:
        score: Raw confidence score (may be outside [0, 1]).
               Accepts float, int, or dict with 'overall' key (DCL format).

    Returns:
        Confidence clamped to [0.0, 1.0]

    Examples:
        bounded_confidence(0.95) -> 0.95
        bounded_confidence(1.5) -> 1.0
        bounded_confidence(-0.2) -> 0.0
        bounded_confidence(float('nan')) -> 0.0
        bounded_confidence({"overall": 0.95}) -> 0.95
    """
    # Defense in depth: DCL returns confidence as dict {"overall": float, ...}
    if isinstance(score, dict):
        score = score.get("overall", 0.0)

    # Reject non-numeric types
    if not isinstance(score, (int, float)):
        return 0.0

    # Handle NaN and infinity
    if math.isnan(score) or math.isinf(score):
        return 0.0

    return max(0.0, min(1.0, score))


class ConfidenceCalculator:
    """
    Calculates confidence scores for query results.

    Weights are configurable but default to:
    - Intent: 40% - How well did we understand the query?
    - Entity: 40% - Did we find matching metrics/periods?
    - Data: 20% - Is the data complete and available?
    """

    DEFAULT_WEIGHTS = {
        "intent": 0.4,
        "entity": 0.4,
        "data": 0.2,
    }

    def __init__(self, weights: Optional[dict] = None):
        """
        Initialize the confidence calculator.

        Args:
            weights: Optional custom weights for scoring factors.
                    Must sum to 1.0 or will be normalized.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

        # Normalize weights to sum to 1.0
        total = sum(self.weights.values())
        if total != 1.0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def calculate(
        self,
        intent_score: float,
        entity_score: float,
        data_score: float
    ) -> float:
        """
        Calculate overall confidence from component scores.

        All input scores should be in [0, 1] range, but will be bounded
        regardless to ensure safety.

        Args:
            intent_score: How clear was the query intent? (0-1)
            entity_score: Did we find the metric/period? (0-1)
            data_score: Is data available? (0-1)

        Returns:
            Overall confidence, ALWAYS bounded [0.0, 1.0]
        """
        # Bound all inputs first
        intent = bounded_confidence(intent_score)
        entity = bounded_confidence(entity_score)
        data = bounded_confidence(data_score)

        # Calculate weighted average
        weighted_sum = (
            self.weights["intent"] * intent +
            self.weights["entity"] * entity +
            self.weights["data"] * data
        )

        # Always bound the final result
        return bounded_confidence(weighted_sum)

    def calculate_from_parse_result(
        self,
        metric_found: bool,
        period_found: bool,
        intent_detected: bool,
        data_exists: bool,
        is_ambiguous: bool = False
    ) -> float:
        """
        Calculate confidence from boolean flags.

        Convenience method for common scenarios.

        Args:
            metric_found: Was the metric recognized?
            period_found: Was the period recognized?
            intent_detected: Was the query intent clear?
            data_exists: Does data exist for the query?
            is_ambiguous: Is the query ambiguous?

        Returns:
            Confidence score, ALWAYS bounded [0.0, 1.0]
        """
        # Convert booleans to scores
        intent_score = 0.8 if intent_detected else 0.3
        if is_ambiguous:
            intent_score *= 0.5

        entity_score = 0.0
        if metric_found and period_found:
            entity_score = 1.0
        elif metric_found or period_found:
            entity_score = 0.5

        data_score = 1.0 if data_exists else 0.0

        return self.calculate(intent_score, entity_score, data_score)
