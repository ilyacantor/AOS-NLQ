"""
Pydantic models for the autonomOS Data Connectivity Layer (DCL).

Covers all DCL capabilities across both tiers:

DCL Core (metadata only):
    - Persona-Contextual Definitions
    - Temporal Versioning (definition drift)
    - Provenance Trace
    - Source of Record tagging

DCL Deep (opt-in, reads data values in-flight, never persists):
    - Entity Resolution
    - Golden Records (field-level provenance)
    - Conflict Detection and Truth Scoring
    - Data Quality Feedback Loop

Integration:
    - MCP Server tool descriptors
    - Enriched Query Response metadata
    - Admin interfaces (manual conflict resolution, audit trail)

All confidence, trust, and quality scores are bounded [0.0, 1.0].
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Shared Enums
# =============================================================================


class Severity(str, Enum):
    """Severity level for conflicts and alerts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConflictStatus(str, Enum):
    """Lifecycle status of a detected conflict."""

    OPEN = "open"
    REVIEWING = "reviewing"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class RootCauseType(str, Enum):
    """Classification of why two source systems disagree.

    Each category captures a distinct class of discrepancy so that
    downstream consumers can apply the correct remediation strategy.
    """

    TIMING = "timing"
    """Systems recorded the same event at different cut-off dates."""

    CURRENCY = "currency"
    """Values differ because of exchange-rate or denomination mismatch."""

    RECOGNITION_METHOD = "recognition_method"
    """Revenue / expense recognition rules differ between systems."""

    SCOPE = "scope"
    """Systems include different entity populations (e.g., subsidiaries)."""

    STALE_DATA = "stale_data"
    """One system has not yet received an update that the other has."""


class MergeAction(str, Enum):
    """Action that was taken during an entity merge operation."""

    MERGE = "merge"
    AUTO_MERGE = "auto_merge"
    SPLIT = "split"
    UNDO = "undo"


# =============================================================================
# 1. Entity Resolution
# =============================================================================


class SourceRecord(BaseModel):
    """A single record as it exists in one source system.

    This is the raw representation before any resolution or deduplication
    has been applied.  The DCL Deep tier reads these values in-flight
    and never persists them.
    """

    source_system_id: str = Field(
        ...,
        description="Identifier of the originating source system (e.g., 'salesforce', 'netsuite').",
    )
    source_record_id: str = Field(
        ...,
        description="Primary-key identifier of this record within the source system.",
    )
    entity_type: str = Field(
        ...,
        description="Logical entity type (e.g., 'company', 'customer', 'contact').",
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value pairs of all record attributes as supplied by the source.",
    )
    extracted_at: datetime = Field(
        ...,
        description="Timestamp when this record snapshot was read from the source.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_system_id": "salesforce",
                "source_record_id": "001ABC123",
                "entity_type": "company",
                "attributes": {"name": "Acme Corp", "industry": "Technology"},
                "extracted_at": "2026-02-07T10:30:00Z",
            }
        }
    )


class MatchCandidate(BaseModel):
    """A potential match discovered during entity resolution.

    The confidence score quantifies how likely two source records refer
    to the same real-world entity.  Scores at or above the auto-merge
    threshold may be merged without human review.
    """

    candidate_id: str = Field(
        ...,
        description="Unique identifier for this match candidate.",
    )
    source_record_a: SourceRecord = Field(
        ...,
        description="First source record in the candidate pair.",
    )
    source_record_b: SourceRecord = Field(
        ...,
        description="Second source record in the candidate pair.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability that the two records represent the same entity (0.0-1.0).",
    )
    match_signals: List[str] = Field(
        default_factory=list,
        description="Human-readable descriptions of the signals that contributed to the score.",
    )
    matched_at: datetime = Field(
        ...,
        description="Timestamp when this match candidate was generated.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "candidate_id": "mc-001",
                "confidence": 0.92,
                "match_signals": [
                    "Exact domain match: acme.com",
                    "Fuzzy name: Acme Corp vs ACME Corporation (0.95)",
                ],
                "matched_at": "2026-02-07T11:00:00Z",
            }
        }
    )


class CanonicalEntity(BaseModel):
    """The resolved, deduplicated representation of an entity.

    Maps one or more (source_system_id, source_record_id) pairs to a
    single dcl_global_id.  This is the backbone of cross-system identity.
    """

    dcl_global_id: str = Field(
        ...,
        description="DCL-assigned globally unique identifier for this canonical entity.",
    )
    entity_type: str = Field(
        ...,
        description="Logical entity type (e.g., 'company', 'customer', 'contact').",
    )
    display_name: str = Field(
        ...,
        description="Human-readable name chosen as the canonical representation.",
    )
    source_records: List[SourceRecord] = Field(
        default_factory=list,
        description="All source records that have been resolved to this entity.",
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when this canonical entity was first created.",
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp of the most recent update to this entity.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dcl_global_id": "dcl-ent-acme-001",
                "entity_type": "company",
                "display_name": "Acme Corporation",
                "created_at": "2026-01-15T08:00:00Z",
                "updated_at": "2026-02-07T10:30:00Z",
            }
        }
    )


class MergeHistory(BaseModel):
    """Audit record for an entity merge, split, or undo operation.

    Every merge is reversible.  The undo capability replays the inverse
    of the original action, restoring the previous entity graph state.
    """

    merge_id: str = Field(
        ...,
        description="Unique identifier for this merge operation.",
    )
    action: MergeAction = Field(
        ...,
        description="The action that was performed (merge, auto_merge, split, undo).",
    )
    surviving_entity_id: str = Field(
        ...,
        description="dcl_global_id of the entity that survived the merge (or was recreated on undo).",
    )
    merged_entity_ids: List[str] = Field(
        default_factory=list,
        description="dcl_global_ids of entities that were consumed by the merge.",
    )
    performed_by: str = Field(
        ...,
        description="User or system principal that initiated the action.",
    )
    performed_at: datetime = Field(
        ...,
        description="Timestamp when the action was executed.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable explanation for why this action was taken.",
    )
    undone_by_merge_id: Optional[str] = Field(
        default=None,
        description="If this operation was later reversed, the merge_id of the undo entry.",
    )
    undoes_merge_id: Optional[str] = Field(
        default=None,
        description="If this is an undo action, the merge_id of the original operation being reversed.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "merge_id": "mrg-20260207-001",
                "action": "merge",
                "surviving_entity_id": "dcl-ent-acme-001",
                "merged_entity_ids": ["dcl-ent-acme-002"],
                "performed_by": "jdoe@company.com",
                "performed_at": "2026-02-07T14:00:00Z",
                "reason": "Confirmed duplicate via domain match and D&B verification.",
            }
        }
    )


# =============================================================================
# 2. Golden Records
# =============================================================================


class FieldProvenance(BaseModel):
    """Tracks which source system contributed a specific field value to a golden record.

    Every field in a golden record carries provenance so that consumers
    can understand exactly where each piece of data originated and how
    trustworthy it is.
    """

    field_name: str = Field(
        ...,
        description="Name of the golden-record field (e.g., 'revenue', 'employee_count').",
    )
    value: Any = Field(
        ...,
        description="The value selected for the golden record.",
    )
    source_system_id: str = Field(
        ...,
        description="Source system that contributed this value.",
    )
    source_record_id: str = Field(
        ...,
        description="Record ID within the source system.",
    )
    trust_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Trust score of this source for this field (0.0-1.0).",
    )
    selected_reason: str = Field(
        ...,
        description=(
            "Why this source was chosen for this field "
            "(e.g., 'highest_trust', 'most_recent', 'manual_override')."
        ),
    )
    collected_at: datetime = Field(
        ...,
        description="Timestamp when this value was collected from the source.",
    )


class GoldenRecord(BaseModel):
    """The single best representation of an entity assembled from multiple sources.

    Each field carries its own provenance, making it transparent which
    source system contributed which value and why it was selected over
    alternatives.
    """

    dcl_global_id: str = Field(
        ...,
        description="Canonical entity ID this golden record belongs to.",
    )
    entity_type: str = Field(
        ...,
        description="Logical entity type (e.g., 'company', 'customer').",
    )
    fields: Dict[str, FieldProvenance] = Field(
        default_factory=dict,
        description=(
            "Map of field name to FieldProvenance. Each entry captures "
            "the chosen value and the source it came from."
        ),
    )
    assembled_at: datetime = Field(
        ...,
        description="Timestamp when this golden record was last assembled.",
    )
    contributing_sources: List[str] = Field(
        default_factory=list,
        description="Distinct source_system_ids that contributed at least one field.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dcl_global_id": "dcl-ent-acme-001",
                "entity_type": "company",
                "fields": {
                    "name": {
                        "field_name": "name",
                        "value": "Acme Corporation",
                        "source_system_id": "salesforce",
                        "source_record_id": "001ABC123",
                        "trust_score": 0.95,
                        "selected_reason": "highest_trust",
                        "collected_at": "2026-02-07T10:30:00Z",
                    },
                    "annual_revenue": {
                        "field_name": "annual_revenue",
                        "value": 150000000,
                        "source_system_id": "netsuite",
                        "source_record_id": "NS-5678",
                        "trust_score": 0.98,
                        "selected_reason": "system_of_record_for_financials",
                        "collected_at": "2026-02-07T09:00:00Z",
                    },
                },
                "assembled_at": "2026-02-07T11:00:00Z",
                "contributing_sources": ["salesforce", "netsuite"],
            }
        }
    )


# =============================================================================
# 3. Conflict Detection
# =============================================================================


class Conflict(BaseModel):
    """A detected discrepancy between two or more source systems for the same metric or entity.

    Conflicts are scored by severity and tracked through a lifecycle
    from detection to resolution.  Each conflict includes a root-cause
    classification to assist automated and manual remediation.
    """

    conflict_id: str = Field(
        ...,
        description="Unique identifier for this conflict.",
    )
    entity_id: Optional[str] = Field(
        default=None,
        description="dcl_global_id of the entity involved, if applicable.",
    )
    metric: str = Field(
        ...,
        description="Canonical metric name where the discrepancy was detected.",
    )
    systems_involved: List[str] = Field(
        ...,
        min_length=2,
        description="Source system IDs that disagree (minimum two).",
    )
    values_by_system: Dict[str, Any] = Field(
        default_factory=dict,
        description="Map of source_system_id to the value reported by that system.",
    )
    delta: float = Field(
        ...,
        description="Absolute magnitude of the discrepancy between the most divergent values.",
    )
    delta_pct: Optional[float] = Field(
        default=None,
        description="Discrepancy expressed as a percentage of the reference value.",
    )
    root_cause: RootCauseType = Field(
        ...,
        description="Classification of the likely reason for the discrepancy.",
    )
    severity: Severity = Field(
        ...,
        description="Impact severity (critical, high, medium, low).",
    )
    status: ConflictStatus = Field(
        default=ConflictStatus.OPEN,
        description="Current lifecycle status of this conflict.",
    )
    detected_at: datetime = Field(
        ...,
        description="Timestamp when the conflict was first detected.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the most recent status or data change.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable summary of the conflict.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "cnf-20260207-001",
                "entity_id": "dcl-ent-acme-001",
                "metric": "revenue",
                "systems_involved": ["netsuite", "salesforce"],
                "values_by_system": {
                    "netsuite": 150000000,
                    "salesforce": 148500000,
                },
                "delta": 1500000,
                "delta_pct": 1.0,
                "root_cause": "timing",
                "severity": "medium",
                "status": "open",
                "detected_at": "2026-02-07T12:00:00Z",
                "description": (
                    "Revenue differs by $1.5M (1.0%) between NetSuite and "
                    "Salesforce.  Likely cut-off timing difference at quarter-end."
                ),
            }
        }
    )


# =============================================================================
# 4. Truth Scoring
# =============================================================================


class TrustRecommendation(BaseModel):
    """A recommendation for which source system to trust for a given conflict.

    Generated by the truth-scoring engine after evaluating freshness,
    historical accuracy, and source-of-record designations.
    """

    conflict_id: str = Field(
        ...,
        description="Identifier of the conflict this recommendation addresses.",
    )
    winner_system: str = Field(
        ...,
        description="Source system ID recommended as the authoritative value.",
    )
    winner_value: Any = Field(
        ...,
        description="The value from the winning system.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this recommendation (0.0-1.0).",
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation for why this system was chosen.",
    )
    contributing_factors: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of factors that influenced the decision "
            "(e.g., 'source_of_record', 'most_recent_update', 'historical_accuracy')."
        ),
    )
    recommended_at: datetime = Field(
        ...,
        description="Timestamp when this recommendation was generated.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "cnf-20260207-001",
                "winner_system": "netsuite",
                "winner_value": 150000000,
                "confidence": 0.91,
                "reason": (
                    "NetSuite is the designated system of record for financial "
                    "metrics and was updated 4 hours more recently than Salesforce."
                ),
                "contributing_factors": [
                    "source_of_record",
                    "most_recent_update",
                    "historical_accuracy",
                ],
                "recommended_at": "2026-02-07T12:05:00Z",
            }
        }
    )


# =============================================================================
# 5. Data Quality Feedback
# =============================================================================


class QualityScore(BaseModel):
    """Quality assessment for a metric or data source.

    Supports both automated scoring (computed from freshness,
    completeness, consistency checks) and manual overrides by
    administrators who have domain knowledge.
    """

    target_id: str = Field(
        ...,
        description=(
            "Identifier of the scored target. May be a metric name, "
            "source_system_id, or dcl_global_id depending on context."
        ),
    )
    target_type: str = Field(
        ...,
        description="Type of the scored target ('metric', 'source_system', 'entity').",
    )
    automatic_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="System-computed quality score based on automated checks (0.0-1.0).",
    )
    manual_override: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Administrator-supplied override score (0.0-1.0). "
            "When present, this takes precedence over the automatic score."
        ),
    )
    effective_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "The score actually used downstream: manual_override if set, "
            "otherwise automatic_score."
        ),
    )
    factors: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Breakdown of factor scores that contribute to the automatic score "
            "(e.g., {'freshness': 0.95, 'completeness': 0.88, 'consistency': 0.92})."
        ),
    )
    override_reason: Optional[str] = Field(
        default=None,
        description="Explanation provided by the administrator when setting a manual override.",
    )
    overridden_by: Optional[str] = Field(
        default=None,
        description="User principal who set the manual override.",
    )
    assessed_at: datetime = Field(
        ...,
        description="Timestamp when this quality assessment was computed or overridden.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "target_id": "revenue",
                "target_type": "metric",
                "automatic_score": 0.91,
                "manual_override": None,
                "effective_score": 0.91,
                "factors": {
                    "freshness": 0.95,
                    "completeness": 0.88,
                    "consistency": 0.92,
                },
                "assessed_at": "2026-02-07T06:00:00Z",
            }
        }
    )


# =============================================================================
# 6. Temporal Versioning (Definition Drift)
# =============================================================================


class DefinitionChange(BaseModel):
    """A versioned record of a metric or concept definition changing over time.

    Captures definition drift so that historical queries can be
    interpreted under the definition that was in effect at the time
    the data was recorded.
    """

    change_id: str = Field(
        ...,
        description="Unique identifier for this definition change.",
    )
    concept: str = Field(
        ...,
        description="The metric or concept whose definition changed (e.g., 'revenue', 'churn_rate').",
    )
    change_date: datetime = Field(
        ...,
        description="Effective date of the new definition.",
    )
    old_definition: str = Field(
        ...,
        description="Full text of the previous definition.",
    )
    new_definition: str = Field(
        ...,
        description="Full text of the new definition.",
    )
    changed_by: str = Field(
        ...,
        description="User or system principal that authored the change.",
    )
    reason: str = Field(
        ...,
        description="Business rationale for why the definition was changed.",
    )
    affects_historical: bool = Field(
        default=False,
        description=(
            "Whether this change should be applied retroactively to "
            "historical data or only to data going forward."
        ),
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Monotonically increasing version number for this concept.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "change_id": "def-chg-20260101-001",
                "concept": "revenue",
                "change_date": "2026-01-01T00:00:00Z",
                "old_definition": "Total invoiced amount including services and licenses.",
                "new_definition": (
                    "Total invoiced amount including services, licenses, "
                    "and usage-based billing components."
                ),
                "changed_by": "cfo@company.com",
                "reason": "Added usage-based billing after product launch in Q4 2025.",
                "affects_historical": False,
                "version": 3,
            }
        }
    )


# =============================================================================
# 7. Provenance Trace
# =============================================================================


class ProvenanceLineage(BaseModel):
    """End-to-end lineage record for a data value.

    Traces the path from the originating source system and table/field
    through any transformations to the final value surfaced in NLQ
    responses.  Includes trust and freshness assessments.
    """

    lineage_id: str = Field(
        ...,
        description="Unique identifier for this lineage trace.",
    )
    metric: str = Field(
        ...,
        description="Canonical metric name this lineage describes.",
    )
    source_system: str = Field(
        ...,
        description="Originating source system identifier (e.g., 'netsuite', 'snowflake').",
    )
    source_table: str = Field(
        ...,
        description="Table or object name within the source system.",
    )
    source_field: str = Field(
        ...,
        description="Column or field name within the source table.",
    )
    transformation: Optional[str] = Field(
        default=None,
        description=(
            "Description of any transformation applied between source "
            "and final value (e.g., 'SUM(amount) WHERE type=revenue', 'currency_convert(USD)')."
        ),
    )
    intermediate_steps: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of intermediate processing steps "
            "(e.g., ['extract_from_netsuite', 'currency_normalize', 'aggregate_quarterly'])."
        ),
    )
    trust_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Trust score for this data path (0.0-1.0).",
    )
    freshness: str = Field(
        ...,
        description="Human-readable freshness indicator (e.g., '2h', '24h', '7d').",
    )
    last_updated: datetime = Field(
        ...,
        description="Timestamp of the most recent data refresh along this lineage path.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lineage_id": "lin-rev-ns-001",
                "metric": "revenue",
                "source_system": "netsuite",
                "source_table": "transactions",
                "source_field": "amount",
                "transformation": "SUM(amount) WHERE type = 'revenue' GROUP BY period",
                "intermediate_steps": [
                    "extract_from_netsuite",
                    "currency_normalize_to_usd",
                    "aggregate_quarterly",
                ],
                "trust_score": 0.96,
                "freshness": "4h",
                "last_updated": "2026-02-07T06:00:00Z",
            }
        }
    )


# =============================================================================
# 8. Persona-Contextual Definitions
# =============================================================================


class PersonaDefinition(BaseModel):
    """A metric or value definition tailored to a specific executive persona.

    Different personas (CFO, CRO, COO, etc.) may interpret the same
    term differently.  This model captures those per-persona semantics
    so the NLQ engine can respond appropriately based on who is asking.
    """

    persona: str = Field(
        ...,
        description="Executive persona this definition applies to (e.g., 'CFO', 'CRO', 'COO').",
    )
    metric: str = Field(
        ...,
        description="Canonical metric name (e.g., 'revenue', 'pipeline').",
    )
    value: Optional[Any] = Field(
        default=None,
        description="Persona-specific value or computation reference, if applicable.",
    )
    definition: str = Field(
        ...,
        description="Full text definition of this metric as understood by this persona.",
    )
    rationale: str = Field(
        ...,
        description="Explanation of why this persona's definition differs from others.",
    )
    includes: List[str] = Field(
        default_factory=list,
        description="Components explicitly included in this persona's view (e.g., ['services', 'licenses']).",
    )
    excludes: List[str] = Field(
        default_factory=list,
        description="Components explicitly excluded from this persona's view (e.g., ['intercompany']).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "persona": "CFO",
                "metric": "revenue",
                "value": None,
                "definition": (
                    "Total recognized revenue per ASC 606, including services, "
                    "licenses, and usage-based billing. Excludes deferred revenue."
                ),
                "rationale": (
                    "CFO view aligns with GAAP reporting and excludes deferred "
                    "amounts that have not yet met recognition criteria."
                ),
                "includes": ["services", "licenses", "usage_billing"],
                "excludes": ["deferred_revenue", "intercompany"],
            }
        }
    )


# =============================================================================
# 9. MCP Server
# =============================================================================


class MCPToolParameter(BaseModel):
    """Schema for a single parameter accepted by an MCP tool."""

    name: str = Field(
        ...,
        description="Parameter name.",
    )
    type: str = Field(
        ...,
        description="JSON Schema type (e.g., 'string', 'number', 'boolean', 'array', 'object').",
    )
    description: str = Field(
        ...,
        description="Human-readable description of the parameter.",
    )
    required: bool = Field(
        default=False,
        description="Whether this parameter is required.",
    )
    default: Optional[Any] = Field(
        default=None,
        description="Default value when the parameter is not supplied.",
    )


class MCPTool(BaseModel):
    """Descriptor for a tool exposed through the Model Context Protocol (MCP) server.

    Each tool represents a discrete DCL capability that can be invoked
    by an AI agent or external system via the MCP interface.
    """

    tool_id: str = Field(
        ...,
        description="Unique identifier for this tool (e.g., 'dcl.resolve_entity', 'dcl.get_conflicts').",
    )
    name: str = Field(
        ...,
        description="Human-readable tool name.",
    )
    description: str = Field(
        ...,
        description="Detailed description of what this tool does and when to use it.",
    )
    parameters: List[MCPToolParameter] = Field(
        default_factory=list,
        description="Parameters accepted by this tool.",
    )
    returns: str = Field(
        ...,
        description="Description of the return value type and structure.",
    )
    category: str = Field(
        default="general",
        description="Capability category (e.g., 'entity_resolution', 'conflict_detection', 'provenance').",
    )


class MCPToolResult(BaseModel):
    """Result envelope returned by an MCP tool invocation."""

    tool_id: str = Field(
        ...,
        description="Identifier of the tool that was invoked.",
    )
    success: bool = Field(
        ...,
        description="Whether the tool invocation succeeded.",
    )
    data: Optional[Any] = Field(
        default=None,
        description="Payload returned by the tool on success.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the invocation failed.",
    )
    duration_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Wall-clock execution time in milliseconds.",
    )
    invoked_at: datetime = Field(
        ...,
        description="Timestamp when the tool was invoked.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tool_id": "dcl.resolve_entity",
                "success": True,
                "data": {
                    "dcl_global_id": "dcl-ent-acme-001",
                    "display_name": "Acme Corporation",
                },
                "error": None,
                "duration_ms": 42.5,
                "invoked_at": "2026-02-07T14:30:00Z",
            }
        }
    )


# =============================================================================
# 10. Enriched Query Response
# =============================================================================


class QueryMetadata(BaseModel):
    """Metadata that enriches an NLQ response with DCL context.

    Attached to query responses to provide transparency about entity
    resolution, data provenance, and any active conflicts that may
    affect the reported values.
    """

    query_id: str = Field(
        ...,
        description="Unique identifier for the query this metadata belongs to.",
    )
    entity: Optional[CanonicalEntity] = Field(
        default=None,
        description="Resolved canonical entity, if the query involved entity resolution.",
    )
    provenance: Optional[List[ProvenanceLineage]] = Field(
        default=None,
        description="Lineage traces for the data values included in the response.",
    )
    conflicts: Optional[List[Conflict]] = Field(
        default=None,
        description="Active conflicts affecting the metrics in this response.",
    )
    trust_recommendation: Optional[TrustRecommendation] = Field(
        default=None,
        description="Truth-scoring recommendation, if a conflict was detected.",
    )
    quality_score: Optional[QualityScore] = Field(
        default=None,
        description="Quality assessment for the primary metric in the response.",
    )
    persona_definition: Optional[PersonaDefinition] = Field(
        default=None,
        description="Persona-specific definition applied to this query, if any.",
    )
    definition_version: Optional[DefinitionChange] = Field(
        default=None,
        description="The definition version in effect at the time of the queried data.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query_id": "qry-20260207-001",
                "entity": None,
                "provenance": [
                    {
                        "lineage_id": "lin-rev-ns-001",
                        "metric": "revenue",
                        "source_system": "netsuite",
                        "source_table": "transactions",
                        "source_field": "amount",
                        "trust_score": 0.96,
                        "freshness": "4h",
                        "last_updated": "2026-02-07T06:00:00Z",
                    }
                ],
                "conflicts": [],
            }
        }
    )


# =============================================================================
# 11. Admin - Conflict Resolution
# =============================================================================


class AuditEntry(BaseModel):
    """A single entry in the audit trail for administrative actions."""

    action: str = Field(
        ...,
        description="Description of the action taken (e.g., 'status_changed', 'resolution_submitted').",
    )
    performed_by: str = Field(
        ...,
        description="User principal who performed the action.",
    )
    performed_at: datetime = Field(
        ...,
        description="Timestamp of the action.",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional structured details about the action.",
    )


class ConflictResolution(BaseModel):
    """Administrative resolution of a detected conflict.

    Captures the decision, rationale, and full audit trail so that
    every conflict resolution is traceable and defensible.
    """

    resolution_id: str = Field(
        ...,
        description="Unique identifier for this resolution.",
    )
    conflict_id: str = Field(
        ...,
        description="Identifier of the conflict being resolved.",
    )
    decision: str = Field(
        ...,
        description=(
            "The resolution decision. Typically the source_system_id to trust "
            "or a directive like 'use_average', 'manual_value', 'dismiss'."
        ),
    )
    resolved_value: Optional[Any] = Field(
        default=None,
        description="The final value to use after resolution, if applicable.",
    )
    rationale: str = Field(
        ...,
        description="Detailed explanation of why this decision was made.",
    )
    resolved_by: str = Field(
        ...,
        description="User principal who authored the resolution.",
    )
    resolved_at: datetime = Field(
        ...,
        description="Timestamp when the resolution was finalized.",
    )
    audit_trail: List[AuditEntry] = Field(
        default_factory=list,
        description="Chronological audit trail of all actions taken on this conflict.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolution_id": "res-20260207-001",
                "conflict_id": "cnf-20260207-001",
                "decision": "netsuite",
                "resolved_value": 150000000,
                "rationale": (
                    "NetSuite is the system of record for financial data. "
                    "The Salesforce figure reflects a pipeline snapshot, not "
                    "recognized revenue."
                ),
                "resolved_by": "cfo@company.com",
                "resolved_at": "2026-02-07T15:00:00Z",
                "audit_trail": [
                    {
                        "action": "conflict_detected",
                        "performed_by": "system",
                        "performed_at": "2026-02-07T12:00:00Z",
                    },
                    {
                        "action": "status_changed",
                        "performed_by": "analyst@company.com",
                        "performed_at": "2026-02-07T13:00:00Z",
                        "details": {
                            "from": "open",
                            "to": "reviewing",
                        },
                    },
                    {
                        "action": "resolution_submitted",
                        "performed_by": "cfo@company.com",
                        "performed_at": "2026-02-07T15:00:00Z",
                        "details": {
                            "decision": "netsuite",
                        },
                    },
                ],
            }
        }
    )


# =============================================================================
# 12. Source of Record
# =============================================================================


class SORTag(BaseModel):
    """Source of Record designation for a data system.

    Tags a source system as the authoritative source for one or more
    business domains.  Trust and quality scores inform the truth-scoring
    engine when adjudicating conflicts.
    """

    source_system_id: str = Field(
        ...,
        description="Identifier of the tagged source system (e.g., 'netsuite', 'salesforce').",
    )
    sor_for: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "Business domains for which this system is the source of record "
            "(e.g., ['financials', 'accounts_receivable', 'general_ledger'])."
        ),
    )
    trust_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall trust score for this source system (0.0-1.0).",
    )
    quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall data quality score for this source system (0.0-1.0).",
    )
    is_primary: bool = Field(
        default=False,
        description=(
            "Whether this is the primary source of record. When multiple "
            "systems cover overlapping domains, the primary system wins ties."
        ),
    )
    designated_by: Optional[str] = Field(
        default=None,
        description="User principal who designated this system as the source of record.",
    )
    designated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the designation was made.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-text notes about this source-of-record designation.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_system_id": "netsuite",
                "sor_for": [
                    "financials",
                    "accounts_receivable",
                    "accounts_payable",
                    "general_ledger",
                ],
                "trust_score": 0.97,
                "quality_score": 0.94,
                "is_primary": True,
                "designated_by": "cfo@company.com",
                "designated_at": "2026-01-01T00:00:00Z",
                "notes": "NetSuite is the GL system of record per FP&A policy.",
            }
        }
    )


# =============================================================================
# 13. Route-specific Request/Response Models
# =============================================================================


class EntityCandidate(BaseModel):
    """A candidate entity match returned by entity search."""

    dcl_global_id: str
    name: str
    source_system: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    match_signals: List[str] = Field(default_factory=list)


class EntityRecord(BaseModel):
    """Full entity record returned by entity lookup."""

    dcl_global_id: str
    entity_type: str = "company"
    display_name: str
    source_records: List[Dict[str, Any]] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EntitySearchResponse(BaseModel):
    """Response for entity search endpoint."""

    term: str
    candidates: List[EntityCandidate]
    total: int


class MergeRequest(BaseModel):
    """Request to merge two entities."""

    entity_a_id: str
    entity_b_id: str
    confirmed_by: str


class MergeResponse(BaseModel):
    """Response from entity merge."""

    merge_id: str
    surviving_entity_id: str
    merged_entity_ids: List[str]
    status: str = "merged"


class MergeUndoResponse(BaseModel):
    """Response from merge undo."""

    merge_id: str
    restored_entity_ids: List[str]
    status: str = "undone"


class ConflictResolutionRequest(BaseModel):
    """Request to resolve a conflict."""

    decision: str  # accept_a, accept_b, manual
    rationale: Optional[str] = None
    resolved_by: str = "system"


class ConflictResolutionResponse(BaseModel):
    """Response from conflict resolution."""

    conflict_id: str
    resolution_id: str
    decision: str
    status: str = "resolved"


class ProvenanceRecord(BaseModel):
    """Provenance data for a metric."""

    metric: str
    lineage: List[Dict[str, Any]]
    system_of_record: Optional[str] = None
    trust_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    freshness: Optional[str] = None


class TemporalChangelogEntry(BaseModel):
    """A single entry in a concept's definition changelog."""

    change_id: Optional[str] = None
    concept: str
    change_date: str
    old_definition: str
    new_definition: str
    changed_by: str
    reason: str
    version: Optional[int] = None


class TemporalBoundaryCheck(BaseModel):
    """Result of checking if comparison crosses a definition boundary."""

    concept: str
    start_period: str
    end_period: str
    crosses_boundary: bool
    change_date: Optional[str] = None
    old_definition: Optional[str] = None
    new_definition: Optional[str] = None
    warning: Optional[str] = None


class QueryRequest(BaseModel):
    """Request for DCL enriched query."""

    metric: str
    entity: Optional[str] = None
    persona: Optional[str] = None
    time_range: Optional[str] = None
    dimensions: Optional[List[str]] = None
    order_by: Optional[str] = None
    limit: Optional[int] = None


class QueryResponse(BaseModel):
    """Response for DCL enriched query."""

    metric: str
    value: Optional[Any] = None
    formatted_value: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    period: Optional[str] = None
    metadata: Optional[QueryMetadata] = None
    entity: Optional[str] = None
    persona: Optional[str] = None


class MCPExecuteRequest(BaseModel):
    """Request to execute an MCP tool."""

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPExecuteResponse(BaseModel):
    """Response from MCP tool execution."""

    tool_name: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


# =============================================================================
# Convenience exports
# =============================================================================

__all__ = [
    # Enums
    "Severity",
    "ConflictStatus",
    "RootCauseType",
    "MergeAction",
    # Entity Resolution
    "SourceRecord",
    "MatchCandidate",
    "CanonicalEntity",
    "MergeHistory",
    # Golden Records
    "FieldProvenance",
    "GoldenRecord",
    # Conflict Detection
    "Conflict",
    # Truth Scoring
    "TrustRecommendation",
    # Data Quality Feedback
    "QualityScore",
    # Temporal Versioning
    "DefinitionChange",
    # Provenance Trace
    "ProvenanceLineage",
    # Persona-Contextual Definitions
    "PersonaDefinition",
    # MCP Server
    "MCPToolParameter",
    "MCPTool",
    "MCPToolResult",
    # Enriched Query Response
    "QueryMetadata",
    # Admin
    "AuditEntry",
    "ConflictResolution",
    # Source of Record
    "SORTag",
    # Route-specific Request/Response Models
    "EntityCandidate",
    "EntityRecord",
    "EntitySearchResponse",
    "MergeRequest",
    "MergeResponse",
    "MergeUndoResponse",
    "ConflictResolutionRequest",
    "ConflictResolutionResponse",
    "ProvenanceRecord",
    "TemporalChangelogEntry",
    "TemporalBoundaryCheck",
    "QueryRequest",
    "QueryResponse",
    "MCPExecuteRequest",
    "MCPExecuteResponse",
]
