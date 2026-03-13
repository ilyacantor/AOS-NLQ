"""
DCL Enrichment Service for NLQ responses.

Enriches NLQ query results with:
- Entity resolution (company/customer matching)
- Provenance trace (where the data comes from)
- Conflict surfacing (cross-system disagreements)
- Temporal warnings (definition changes across comparison periods)
- Persona-contextual values

This service acts as the bridge between NLQ's query flow and DCL's
new capabilities (entity resolution, golden records, conflict detection, etc.).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_dcl_engine = None


def _get_dcl_engine():
    """Get the DCL engine singleton (lazy init)."""
    global _dcl_engine
    if _dcl_engine is None:
        try:
            from src.nlq.dcl.engine import get_dcl_engine
            _dcl_engine = get_dcl_engine()
        except (ImportError, RuntimeError, OSError) as e:
            logger.warning(f"DCL engine not available: {e}")
            return None
    return _dcl_engine


def resolve_entity_for_query(entity_term: str) -> Optional[Dict[str, Any]]:
    """
    Resolve an entity name from a user query via DCL.

    Args:
        entity_term: Entity name extracted from query (e.g., "Acme", "Globex Corp")

    Returns:
        Dict with:
        - entity_name: Canonical name
        - entity_id: DCL global ID
        - matched_systems: List of systems where entity was found
        - confidence: Match confidence
        - candidates: Other possible matches (for ambiguity)
        Or None if no match found.
    """
    engine = _get_dcl_engine()
    if not engine:
        return None

    try:
        matches = engine.resolve_entity(entity_term)
        if not matches:
            return None

        top_match = matches[0]

        # Check for ambiguity (multiple close matches)
        candidates = []
        if len(matches) > 1:
            for m in matches[1:]:
                candidates.append({
                    "name": m.get("canonical_name", m.get("name", "")),
                    "entity_id": m.get("dcl_global_id", ""),
                    "confidence": m.get("confidence", 0),
                })

        # Gather matched systems info
        source_records = top_match.get("source_records", [])
        matched_systems = list(set(r.get("source_system", "") for r in source_records))

        return {
            "entity_name": top_match.get("canonical_name", entity_term),
            "entity_id": top_match.get("dcl_global_id", ""),
            "matched_systems": matched_systems,
            "system_count": len(matched_systems),
            "confidence": top_match.get("confidence", 0.0),
            "candidates": candidates if candidates else None,
            "is_ambiguous": len(matches) > 1 and matches[1].get("confidence", 0) > 0.7,
        }
    except (RuntimeError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Entity resolution failed for '{entity_term}': {e}")
        return None


def get_provenance_for_metric(metric: str) -> Optional[Dict[str, Any]]:
    """
    Get provenance trace for a metric via DCL.

    Args:
        metric: Canonical metric name (e.g., "revenue", "pipeline")

    Returns:
        Dict with lineage info, or None if not available.
    """
    engine = _get_dcl_engine()
    if not engine:
        return None

    try:
        provenance = engine.get_provenance(metric)
        if not provenance:
            return None

        # Convert Pydantic model to dict for downstream consumers
        if hasattr(provenance, "model_dump"):
            return provenance.model_dump()
        return provenance
    except (RuntimeError, KeyError, TypeError, AttributeError) as e:
        logger.debug(f"Provenance lookup failed for '{metric}': {e}")
        return None


def get_conflicts_for_query(
    metric: str,
    entity_id: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Get conflicts for a metric/entity combination.

    Args:
        metric: Canonical metric name
        entity_id: Optional DCL global entity ID to filter

    Returns:
        List of conflict dicts sorted by severity, or None if no conflicts.
    """
    engine = _get_dcl_engine()
    if not engine:
        return None

    try:
        conflicts = engine.get_all_conflicts()
        if not conflicts:
            return None

        # Filter by metric and optionally entity
        filtered = []
        for c in conflicts:
            if c.get("metric") == metric:
                if entity_id is None or c.get("entity_id") == entity_id:
                    filtered.append(c)

        if not filtered:
            return None

        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        filtered.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 4))

        return filtered
    except (RuntimeError, KeyError, TypeError, AttributeError) as e:
        logger.debug(f"Conflict lookup failed for '{metric}': {e}")
        return None


def check_temporal_warning(
    metric: str,
    start_period: Optional[str] = None,
    end_period: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check if a comparison query crosses a definition change boundary.

    Args:
        metric: Canonical metric name (maps to concept in temporal versioning)
        start_period: Earlier period in comparison
        end_period: Later period in comparison

    Returns:
        Warning dict if boundary crossed, None otherwise.
    """
    if not start_period or not end_period:
        return None

    engine = _get_dcl_engine()
    if not engine:
        return None

    try:
        warning = engine.check_temporal_boundary(metric, start_period, end_period)
        if not warning:
            return None
        # Convert Pydantic model to dict and filter out non-crossing results
        if hasattr(warning, "model_dump"):
            warning_dict = warning.model_dump()
        else:
            warning_dict = warning
        # Only return if boundary was actually crossed
        if not warning_dict.get("crosses_boundary", False):
            return None
        return warning_dict
    except (RuntimeError, KeyError, TypeError, AttributeError) as e:
        logger.debug(f"Temporal check failed for '{metric}': {e}")
        return None


def get_persona_value(metric: str, persona: str) -> Optional[Dict[str, Any]]:
    """
    Get persona-contextual value for a metric.

    Args:
        metric: Canonical metric name
        persona: Persona identifier (CFO, CRO, COO, etc.)

    Returns:
        Dict with persona-specific value, definition, and rationale.
    """
    engine = _get_dcl_engine()
    if not engine:
        return None

    try:
        return engine.get_persona_value(metric, persona)
    except (RuntimeError, KeyError, TypeError, AttributeError) as e:
        logger.debug(f"Persona value lookup failed for '{metric}/{persona}': {e}")
        return None


def enrich_response(
    metric: str,
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    persona: Optional[str] = None,
    start_period: Optional[str] = None,
    end_period: Optional[str] = None,
    is_comparison: bool = False,
) -> Dict[str, Any]:
    """
    Full enrichment pipeline: entity + provenance + conflicts + temporal warnings.

    This is the main entry point for enriching NLQ responses with DCL data.

    Args:
        metric: Canonical metric name
        entity: Entity name from query (for resolution)
        entity_id: Already-resolved entity ID (skips resolution)
        persona: Detected persona
        start_period: Start period (for temporal warnings)
        end_period: End period (for temporal warnings)
        is_comparison: Whether this is a comparison query

    Returns:
        Dict with optional keys: entity_resolution, provenance, conflicts, temporal_warning, persona_value
    """
    enrichment = {}

    # 1. Entity resolution
    resolved_entity_id = entity_id
    if entity and not entity_id:
        entity_data = resolve_entity_for_query(entity)
        if entity_data:
            enrichment["entity_resolution"] = entity_data
            resolved_entity_id = entity_data.get("entity_id")
            enrichment["entity_name"] = entity_data.get("entity_name")
            enrichment["entity_id"] = resolved_entity_id

    # 2. Provenance
    provenance = get_provenance_for_metric(metric)
    if provenance:
        enrichment["provenance"] = provenance

    # 3. Conflicts
    conflicts = get_conflicts_for_query(metric, resolved_entity_id)
    if conflicts:
        enrichment["conflicts"] = conflicts

    # 4. Temporal warnings (only for comparison queries)
    if is_comparison and start_period and end_period:
        warning = check_temporal_warning(metric, start_period, end_period)
        if warning:
            enrichment["temporal_warning"] = warning

    # 5. Persona-contextual values
    if persona:
        persona_val = get_persona_value(metric, persona)
        if persona_val:
            enrichment["persona_value"] = persona_val

    return enrichment


def format_provenance_for_personality(provenance: Dict[str, Any]) -> str:
    """
    Format provenance data as natural language for the personality layer.

    Returns something like "from SAP ERP" or "sourced from Salesforce CRM".
    """
    if not provenance:
        return ""

    lineage = provenance.get("lineage", [])
    if not lineage:
        return ""

    # Find the SOR source
    sor_source = None
    for source in lineage:
        if source.get("is_system_of_record"):
            sor_source = source
            break

    if not sor_source:
        sor_source = lineage[0]

    system_name = _format_system_name(sor_source.get("source_system", ""))
    return f"from {system_name}" if system_name else ""


def format_entity_for_personality(entity_resolution: Dict[str, Any]) -> str:
    """
    Format entity resolution as natural language for the personality layer.

    Returns something like "Acme Corp, matched across 3 systems".
    """
    if not entity_resolution:
        return ""

    name = entity_resolution.get("entity_name", "")
    count = entity_resolution.get("system_count", 0)

    if count > 1:
        return f"{name}, matched across {count} systems"
    return name


def format_conflict_for_personality(conflicts: List[Dict[str, Any]], persona: str = "CFO") -> str:
    """
    Format conflicts as natural language for the personality layer.

    Returns something like "CRM says $4.2M, ERP says $3.8M. Timing difference. Trust the ERP."
    """
    if not conflicts:
        return ""

    parts = []
    for conflict in conflicts:
        systems = conflict.get("systems", {})
        system_names = list(systems.keys())
        if len(system_names) < 2:
            continue

        sys_a = system_names[0]
        sys_b = system_names[1]
        val_a = systems[sys_a].get("formatted", "")
        val_b = systems[sys_b].get("formatted", "")

        root_cause = conflict.get("root_cause", {})
        cause_type = root_cause.get("type", "unknown")

        trust_rec = conflict.get("trust_recommendation", {})
        winner = trust_rec.get("winner", "")
        winner_name = _format_system_name(winner)

        severity = conflict.get("severity", "")

        line = f"{_format_system_name(sys_a)} says {val_a}, {_format_system_name(sys_b)} says {val_b}."
        line += f" {_format_cause_type(cause_type)}."
        if winner_name:
            line += f" Trust {winner_name}."

        parts.append(line)

    return " ".join(parts)


def format_temporal_warning_for_personality(warning: Dict[str, Any]) -> str:
    """
    Format temporal warning as natural language for the personality layer.

    Returns something like "Revenue was redefined in March 2025. Your Q1-to-Q1 comparison spans that change."
    """
    if not warning:
        return ""

    concept = warning.get("concept", "This metric")
    change_date = warning.get("change_date", "")
    old_def = warning.get("old_definition", "")
    new_def = warning.get("new_definition", "")

    parts = [f"{concept.title()} was redefined"]
    if change_date:
        parts[0] += f" on {change_date}"
    parts[0] += "."

    if old_def and new_def:
        parts.append(f"Old: {old_def}. New: {new_def}.")

    parts.append("Your comparison spans that change — numbers may not be directly comparable.")

    return " ".join(parts)


def _format_system_name(system_id: str) -> str:
    """Format a system ID into a human-readable name."""
    name_map = {
        "salesforce_crm": "Salesforce CRM",
        "sap_erp": "SAP ERP",
        "netsuite_erp": "NetSuite",
        "hubspot_crm": "HubSpot CRM",
        "mongodb": "MongoDB",
        "snowflake": "Snowflake",
    }
    return name_map.get(system_id, system_id.replace("_", " ").title())


def _format_cause_type(cause_type: str) -> str:
    """Format a root cause type into natural language."""
    cause_map = {
        "timing": "Timing difference",
        "currency": "Currency conversion mismatch",
        "recognition_method": "Different recognition methods",
        "scope": "Scope difference",
        "stale_data": "Stale data in one system",
    }
    return cause_map.get(cause_type, f"Root cause: {cause_type}")
