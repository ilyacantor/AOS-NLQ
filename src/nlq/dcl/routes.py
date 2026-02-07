"""
FastAPI routes for DCL (Data Connectivity Layer) capabilities.

Endpoints cover:
- Health check
- Entity resolution (search, lookup, merge, undo)
- Golden records
- Conflict detection and resolution
- Provenance / lineage
- Temporal versioning
- Persona-contextual definitions
- Enriched query
- MCP server tool listing and execution

All routes are mounted under the /api/dcl prefix.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Lazy-initialised engine singleton
# ---------------------------------------------------------------------------
# The engine module may perform expensive setup (DB connections, model loading)
# so we defer import and instantiation until the first request.

_engine_instance = None


def _get_engine():
    """Return the singleton DCLEngine, creating it on first call."""
    global _engine_instance
    if _engine_instance is None:
        from src.nlq.dcl.engine import DCLEngine
        _engine_instance = DCLEngine()
    return _engine_instance


# ---------------------------------------------------------------------------
# Import shared Pydantic models from dcl.models
# ---------------------------------------------------------------------------
from src.nlq.dcl.models import (
    # Entity resolution
    EntityCandidate,
    EntityRecord,
    EntitySearchResponse,
    MergeRequest,
    MergeResponse,
    MergeUndoResponse,
    # Golden records
    GoldenRecord,
    # Conflicts
    Conflict,
    ConflictResolutionRequest,
    ConflictResolutionResponse,
    # Provenance
    ProvenanceRecord,
    # Temporal
    TemporalChangelogEntry,
    TemporalBoundaryCheck,
    # Persona definitions
    PersonaDefinition,
    # Enriched query
    QueryRequest,
    QueryMetadata,
    QueryResponse,
    # MCP
    MCPTool,
    MCPExecuteRequest,
    MCPExecuteResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/dcl", tags=["DCL"])


# =============================================================================
# HEALTH CHECK
# =============================================================================

class HealthResponse(BaseModel):
    """Response model for DCL health check."""
    status: str = "ok"
    timestamp: str
    engine_ready: bool
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return DCL health status."""
    try:
        engine = _get_engine()
        engine_ready = engine is not None
    except Exception:
        engine_ready = False

    return HealthResponse(
        status="ok" if engine_ready else "degraded",
        timestamp=datetime.utcnow().isoformat() + "Z",
        engine_ready=engine_ready,
    )


# =============================================================================
# ENTITY RESOLUTION
# =============================================================================

@router.get("/entities/{term}", response_model=EntitySearchResponse)
async def search_entities(term: str):
    """
    Search / browse entities by term.

    Returns all candidate matches with source, values and confidence.
    """
    engine = _get_engine()
    try:
        candidates = engine.search_entities(term)
        return EntitySearchResponse(
            term=term,
            candidates=candidates,
            total=len(candidates),
        )
    except Exception as exc:
        logger.exception("Entity search failed for term=%s", term)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/entities/id/{dcl_global_id}", response_model=EntityRecord)
async def get_entity_by_id(dcl_global_id: str):
    """Get the canonical entity record by its DCL global ID."""
    engine = _get_engine()
    try:
        entity = engine.get_entity(dcl_global_id)
    except Exception as exc:
        logger.exception("Entity lookup failed for id=%s", dcl_global_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity {dcl_global_id} not found")
    return entity


@router.post("/entities/merge", response_model=MergeResponse, status_code=201)
async def merge_entities(body: MergeRequest):
    """
    Merge two entities into one.

    The caller must supply the IDs of both entities and who confirmed the merge.
    """
    engine = _get_engine()
    try:
        result = engine.merge_entities(
            entity_a_id=body.entity_a_id,
            entity_b_id=body.entity_b_id,
            confirmed_by=body.confirmed_by,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Entity merge failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/entities/merge/{merge_id}/undo", response_model=MergeUndoResponse)
async def undo_merge(merge_id: str):
    """Undo a previous entity merge."""
    engine = _get_engine()
    try:
        result = engine.undo_merge(merge_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Merge undo failed for merge_id=%s", merge_id)
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# GOLDEN RECORDS
# =============================================================================

@router.get("/golden-record/{dcl_global_id}", response_model=GoldenRecord)
async def get_golden_record(dcl_global_id: str):
    """
    Assemble and return the golden record for a given entity.

    The golden record merges data from all contributing sources,
    applying survivorship rules to produce a single canonical view.
    """
    engine = _get_engine()
    try:
        record = engine.get_golden_record(dcl_global_id)
    except Exception as exc:
        logger.exception("Golden record assembly failed for id=%s", dcl_global_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No golden record found for entity {dcl_global_id}",
        )
    return record


# =============================================================================
# CONFLICT DETECTION
# =============================================================================

class ConflictListResponse(BaseModel):
    """Wrapper for paginated conflict list."""
    conflicts: List[Conflict]
    total: int


@router.get("/conflicts", response_model=ConflictListResponse)
async def list_conflicts(
    status: Optional[str] = Query(
        default=None,
        description="Filter by conflict status (e.g. 'active', 'resolved')",
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity (e.g. 'high', 'medium', 'low')",
    ),
    entity: Optional[str] = Query(
        default=None,
        description="Filter by entity DCL global ID",
    ),
):
    """
    List all active conflicts, with optional filters.
    """
    engine = _get_engine()
    try:
        conflicts = engine.list_conflicts(
            status=status,
            severity=severity,
            entity=entity,
        )
        return ConflictListResponse(conflicts=conflicts, total=len(conflicts))
    except Exception as exc:
        logger.exception("Conflict listing failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/conflicts/{conflict_id}", response_model=Conflict)
async def get_conflict(conflict_id: str):
    """Get a single conflict by ID."""
    engine = _get_engine()
    try:
        conflict = engine.get_conflict(conflict_id)
    except Exception as exc:
        logger.exception("Conflict lookup failed for id=%s", conflict_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if conflict is None:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")
    return conflict


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=ConflictResolutionResponse,
)
async def resolve_conflict(conflict_id: str, body: ConflictResolutionRequest):
    """
    Resolve a conflict.

    Accepted decisions: ``accept_a``, ``accept_b``, ``manual``.
    """
    if body.decision not in ("accept_a", "accept_b", "manual"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision '{body.decision}'. Must be one of: accept_a, accept_b, manual",
        )

    engine = _get_engine()
    try:
        result = engine.resolve_conflict(
            conflict_id=conflict_id,
            decision=body.decision,
            rationale=body.rationale,
            resolved_by=body.resolved_by,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Conflict resolution failed for id=%s", conflict_id)
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# PROVENANCE
# =============================================================================

@router.get("/provenance/{metric}", response_model=ProvenanceRecord)
async def get_provenance(metric: str):
    """
    Return complete lineage for a metric, including freshness and quality scores.
    """
    engine = _get_engine()
    try:
        record = engine.get_provenance(metric)
    except Exception as exc:
        logger.exception("Provenance lookup failed for metric=%s", metric)
        raise HTTPException(status_code=500, detail=str(exc))

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No provenance information found for metric '{metric}'",
        )
    return record


# =============================================================================
# TEMPORAL VERSIONING
# =============================================================================

class TemporalChangelogResponse(BaseModel):
    """Wrapper for definition changelog."""
    concept: str
    changelog: List[TemporalChangelogEntry]
    total: int


@router.get("/temporal/{concept}", response_model=TemporalChangelogResponse)
async def get_temporal_changelog(concept: str):
    """
    Get the definition changelog for a concept (metric, dimension, etc.).

    Shows how a definition has evolved over time so analysts understand
    when comparisons may cross a definitional boundary.
    """
    engine = _get_engine()
    try:
        entries = engine.get_temporal_changelog(concept)
        return TemporalChangelogResponse(
            concept=concept,
            changelog=entries,
            total=len(entries),
        )
    except Exception as exc:
        logger.exception("Temporal changelog failed for concept=%s", concept)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/temporal/check", response_model=TemporalBoundaryCheck)
async def check_temporal_boundary(
    concept: str = Query(..., description="Concept / metric name"),
    start_period: str = Query(..., description="Start period (e.g. '2024-Q1')"),
    end_period: str = Query(..., description="End period (e.g. '2025-Q4')"),
):
    """
    Check whether a comparison between two periods crosses a
    definitional boundary for the given concept.
    """
    engine = _get_engine()
    try:
        result = engine.check_temporal_boundary(
            concept=concept,
            start_period=start_period,
            end_period=end_period,
        )
        return result
    except Exception as exc:
        logger.exception("Temporal boundary check failed")
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# PERSONA DEFINITIONS
# =============================================================================

class PersonaDefinitionsResponse(BaseModel):
    """All persona definitions for a metric."""
    metric: str
    definitions: List[PersonaDefinition]
    total: int


@router.get(
    "/persona-definitions/{metric}",
    response_model=PersonaDefinitionsResponse,
)
async def get_persona_definitions(metric: str):
    """
    Get every persona-specific definition for a metric.

    Different C-suite personas (CFO, CRO, COO, ...) may define the same
    metric differently. This endpoint returns all known definitions.
    """
    engine = _get_engine()
    try:
        definitions = engine.get_persona_definitions(metric)
        return PersonaDefinitionsResponse(
            metric=metric,
            definitions=definitions,
            total=len(definitions),
        )
    except Exception as exc:
        logger.exception("Persona definitions lookup failed for metric=%s", metric)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/persona-definitions/{metric}/{persona}",
    response_model=PersonaDefinition,
)
async def get_persona_definition(metric: str, persona: str):
    """Get the definition of a metric for a specific persona."""
    engine = _get_engine()
    try:
        definition = engine.get_persona_definition(metric, persona)
    except Exception as exc:
        logger.exception(
            "Persona definition lookup failed for metric=%s persona=%s",
            metric,
            persona,
        )
        raise HTTPException(status_code=500, detail=str(exc))

    if definition is None:
        raise HTTPException(
            status_code=404,
            detail=f"No definition found for metric '{metric}' / persona '{persona}'",
        )
    return definition


# =============================================================================
# ENRICHED QUERY
# =============================================================================

@router.post("/query", response_model=QueryResponse)
async def enriched_query(body: QueryRequest):
    """
    Enhanced query endpoint that returns data enriched with DCL metadata.

    Accepts a metric (required) plus optional entity, persona, and time_range.
    The response includes a ``metadata`` block with entity resolution results,
    provenance lineage, and any active conflicts -- all optional and
    non-breaking so callers can adopt incrementally.
    """
    engine = _get_engine()
    try:
        result = engine.enriched_query(
            metric=body.metric,
            entity=body.entity,
            persona=body.persona,
            time_range=body.time_range,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Enriched query failed")
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# MCP SERVER
# =============================================================================

class MCPToolListResponse(BaseModel):
    """List of available MCP tools."""
    tools: List[MCPTool]
    total: int


@router.get("/mcp/tools", response_model=MCPToolListResponse)
async def list_mcp_tools():
    """List all MCP tools exposed by the DCL."""
    engine = _get_engine()
    try:
        tools = engine.list_mcp_tools()
        return MCPToolListResponse(tools=tools, total=len(tools))
    except Exception as exc:
        logger.exception("MCP tool listing failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/mcp/execute", response_model=MCPExecuteResponse)
async def execute_mcp_tool(body: MCPExecuteRequest):
    """
    Execute an MCP tool by name.

    The request body must include the tool name and a dictionary of arguments.
    """
    engine = _get_engine()
    try:
        result = engine.execute_mcp_tool(
            tool_name=body.tool_name,
            arguments=body.arguments,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("MCP tool execution failed for tool=%s", body.tool_name)
        raise HTTPException(status_code=500, detail=str(exc))
