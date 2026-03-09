"""
Contour Map completeness scoring.

Ported from dcl-onboarding-agent contour.service.ts calculateCompleteness().
Extended with Convergence (dual-entity) combined engagement scoring.
"""

from __future__ import annotations

from src.nlq.maestra.types import ContourMap, ConflictStatus, EngagementCompleteness


# Weights for single-entity completeness (0-100)
WEIGHTS = {
    "hierarchy": 30,
    "sor": 20,
    "conflicts_resolved": 15,
    "management": 15,
    "vocabulary": 5,
    "queries": 10,
    "follow_ups": 5,
}


def calculate_contour_completeness(contour: ContourMap) -> float:
    """
    Calculate completeness score for a single entity's contour map.

    Returns 0-100 rounded integer.

    Scoring:
        Hierarchy >= 5 nodes:     30%
        SOR >= 3 entries:         20%
        Conflicts resolved:       15%
        Management overlay > 0:   15%
        Vocabulary >= 3 terms:     5%
        Priority queries >= 3:    10%
        Follow-up tasks > 0:       5%
    """
    score = 0.0

    # Hierarchy: target 5+ nodes
    h_count = len(contour.organizational_hierarchy)
    if h_count >= 5:
        score += WEIGHTS["hierarchy"]
    elif h_count > 0:
        score += WEIGHTS["hierarchy"] * (h_count / 5)

    # SOR: target 3+ entries
    s_count = len(contour.sor_authority_map)
    if s_count >= 3:
        score += WEIGHTS["sor"]
    elif s_count > 0:
        score += WEIGHTS["sor"] * (s_count / 3)

    # Conflicts: % resolved (no conflicts = full credit)
    total_conflicts = len(contour.conflict_register)
    if total_conflicts == 0:
        score += WEIGHTS["conflicts_resolved"]
    else:
        resolved = sum(
            1 for c in contour.conflict_register
            if c.status == ConflictStatus.RESOLVED
        )
        score += WEIGHTS["conflicts_resolved"] * (resolved / total_conflicts)

    # Management overlay: binary
    if len(contour.management_overlay) > 0:
        score += WEIGHTS["management"]

    # Vocabulary: target 3+ terms
    v_count = len(contour.vocabulary_map)
    if v_count >= 3:
        score += WEIGHTS["vocabulary"]
    elif v_count > 0:
        score += WEIGHTS["vocabulary"] * (v_count / 3)

    # Priority queries: target 3+
    q_count = len(contour.priority_queries)
    if q_count >= 3:
        score += WEIGHTS["queries"]
    elif q_count > 0:
        score += WEIGHTS["queries"] * (q_count / 3)

    # Follow-up tasks: binary
    if len(contour.follow_up_tasks) > 0:
        score += WEIGHTS["follow_ups"]

    return round(score)


def calculate_engagement_completeness(
    entity_contours: dict[str, ContourMap],
    cofa_complete: bool = False,
    entity_resolution_complete: bool = False,
    cross_sell_scored: bool = False,
    ebitda_bridge_built: bool = False,
    conflict_register_reviewed: bool = False,
    qoe_baseline_established: bool = False,
) -> EngagementCompleteness:
    """
    Calculate combined engagement completeness for Convergence (dual-entity).

    Combined score:
        Both entities scoped:     20%
        COFA unification:         20%
        Entity resolution:        15%
        Cross-sell scored:        10%
        EBITDA bridge built:      15%
        Conflict register:        10%
        QofE baseline:            10%
    """
    entity_scores = {
        eid: calculate_contour_completeness(contour)
        for eid, contour in entity_contours.items()
    }

    combined = 0.0

    # Both entities scoped (20%)
    if len(entity_scores) >= 2 and all(s >= 50 for s in entity_scores.values()):
        combined += 20.0
    elif entity_scores:
        avg = sum(entity_scores.values()) / len(entity_scores)
        combined += 20.0 * (avg / 100.0) * (len(entity_scores) / 2.0)

    if cofa_complete:
        combined += 20.0
    if entity_resolution_complete:
        combined += 15.0
    if cross_sell_scored:
        combined += 10.0
    if ebitda_bridge_built:
        combined += 15.0
    if conflict_register_reviewed:
        combined += 10.0
    if qoe_baseline_established:
        combined += 10.0

    return EngagementCompleteness(
        entity_scores=entity_scores,
        cofa_unification_pct=100.0 if cofa_complete else 0.0,
        entity_resolution_pct=100.0 if entity_resolution_complete else 0.0,
        cross_sell_scored=cross_sell_scored,
        ebitda_bridge_built=ebitda_bridge_built,
        conflict_register_reviewed=conflict_register_reviewed,
        qoe_baseline_established=qoe_baseline_established,
        combined_score=round(combined),
    )
