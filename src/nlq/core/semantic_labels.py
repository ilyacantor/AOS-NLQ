"""
Semantic label generation for Galaxy visualization nodes.

Semantic labels provide human-readable classifications for each node
based on confidence level and match type.
"""

from src.nlq.models.response import MatchType


def get_semantic_label(confidence: float, match_type: MatchType) -> str:
    """
    Get semantic label for a node based on confidence and match type.

    Labels vary by orbital ring:
    - EXACT (inner): "Exact Match", "Direct Answer", "Best Match"
    - POTENTIAL (middle): "Likely", "Probable", "Possible"
    - HYPOTHESIS (outer): "Potential", "Related", "Context"

    Args:
        confidence: Confidence score (0.0 to 1.0)
        match_type: Orbital ring assignment

    Returns:
        Semantic label string
    """
    if match_type == MatchType.EXACT:
        if confidence >= 0.95:
            return "Exact Match"
        elif confidence >= 0.85:
            return "Direct Answer"
        else:
            return "Best Match"

    elif match_type == MatchType.POTENTIAL:
        if confidence >= 0.75:
            return "Likely"
        elif confidence >= 0.65:
            return "Probable"
        else:
            return "Possible"

    else:  # HYPOTHESIS
        if confidence >= 0.50:
            return "Potential"
        elif confidence >= 0.35:
            return "Related"
        else:
            return "Context"


def get_match_type_from_confidence(confidence: float, is_primary: bool = False) -> MatchType:
    """
    Determine match type based on confidence score.

    This is a fallback for when match type isn't explicitly set.

    Args:
        confidence: Confidence score (0.0 to 1.0)
        is_primary: Whether this is the primary answer node

    Returns:
        MatchType enum value
    """
    if is_primary or confidence >= 0.85:
        return MatchType.EXACT
    elif confidence >= 0.55:
        return MatchType.POTENTIAL
    else:
        return MatchType.HYPOTHESIS
