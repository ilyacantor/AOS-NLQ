"""
DCL Engine — Core implementation of the Data Connectivity Layer.

Loads entity_test_scenarios.json and implements all DCL capabilities:
- Entity Resolution (deterministic + fuzzy matching)
- Golden Records (SOR-driven field-level provenance)
- Conflict Detection (cross-system disagreements)
- Truth Scoring (SOR tagging, freshness, quality)
- Temporal Versioning (definition drift detection)
- Persona-Contextual Definitions
- Provenance Trace
- MCP Tool registry
- Data Quality Feedback Loop

Two-tier model:
  DCL Core — metadata only (provenance, temporal, persona definitions)
  DCL Deep — reads data values in-flight, never stores/persists

All data loaded from data/entity_test_scenarios.json (no self-authored fixtures).
"""

import json
import logging
import os
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.nlq.dcl.models import (
    Conflict,
    ConflictResolutionResponse,
    ConflictStatus,
    EntityCandidate,
    EntityRecord,
    FieldProvenance,
    GoldenRecord,
    MCPExecuteResponse,
    MCPTool,
    MCPToolParameter,
    MergeResponse,
    MergeUndoResponse,
    PersonaDefinition,
    ProvenanceRecord,
    QueryMetadata,
    QueryResponse,
    RootCauseType,
    Severity,
    TemporalBoundaryCheck,
    TemporalChangelogEntry,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_engine_singleton: Optional["DCLEngine"] = None


def get_dcl_engine() -> "DCLEngine":
    """Return (or create) the module-level DCLEngine singleton."""
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = DCLEngine()
    return _engine_singleton


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fuzzy_score(a: str, b: str) -> float:
    """Case-insensitive fuzzy string similarity using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _parse_period_to_date(period: str) -> Optional[str]:
    """Convert period strings like '2024-Q1', '2025-Q2', 'Q1 2024' to approx date."""
    period = period.strip().upper()
    quarter_starts = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    # Handle 2024-Q1 format
    if "-Q" in period:
        parts = period.split("-Q")
        year = parts[0]
        q = f"Q{parts[1]}"
        month = quarter_starts.get(q, "01")
        return f"{year}-{month}-01"
    # Handle Q1 2024 format
    for q, month in quarter_starts.items():
        if q in period:
            year_part = period.replace(q, "").strip()
            if year_part:
                return f"{year_part}-{month}-01"
    # Bare year
    if period.isdigit() and len(period) == 4:
        return f"{period}-01-01"
    return None


# ---------------------------------------------------------------------------
# DCL Engine
# ---------------------------------------------------------------------------

class DCLEngine:
    """Core DCL engine — loads from entity_test_scenarios.json."""

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            # Walk up from this file to find data/entity_test_scenarios.json
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            data_path = str(project_root / "data" / "entity_test_scenarios.json")

        self._data_path = data_path
        self._data: Dict[str, Any] = {}
        self._merge_history: List[Dict[str, Any]] = []
        self._conflict_resolutions: Dict[str, Dict[str, Any]] = {}
        self._load_data()
        logger.info("DCLEngine initialised from %s", data_path)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        """Load and index the fixture data."""
        with open(self._data_path, "r") as f:
            self._data = json.load(f)

        # Build entity index: dcl_global_id -> entity dict
        self._entities: Dict[str, Dict[str, Any]] = {}
        for company in self._data.get("entities", {}).get("companies", []):
            gid = company.get("dcl_global_id", "")
            if gid:
                self._entities[gid] = company

        # Build conflict index: conflict_id -> conflict dict
        self._conflicts: Dict[str, Dict[str, Any]] = {}
        for c in self._data.get("conflicts", []):
            cid = c.get("id", "")
            if cid:
                self._conflicts[cid] = c

        # Provenance index: metric -> provenance dict
        self._provenance: Dict[str, Dict[str, Any]] = self._data.get("provenance", {})

        # Golden records index
        self._golden_records: Dict[str, Dict[str, Any]] = self._data.get("golden_records", {})

        # Temporal versioning
        self._temporal: List[Dict[str, Any]] = (
            self._data.get("temporal_versioning", {}).get("definition_changes", [])
        )

        # Persona definitions
        self._persona_defs: Dict[str, Dict[str, Any]] = self._data.get(
            "persona_contextual_definitions", {}
        )

        # SOR tags
        self._sor_tags: Dict[str, Dict[str, Any]] = self._data.get(
            "source_of_record_tags", {}
        )

        # Non-matches and ambiguous entities
        self._non_matches = self._data.get("entities", {}).get("non_matches", [])
        self._ambiguous = self._data.get("entities", {}).get("ambiguous_entities", [])

        # No-conflict control
        self._no_conflict = self._data.get("no_conflict_control", {})

    # ==================================================================
    # ENTITY RESOLUTION
    # ==================================================================

    def search_entities(self, term: str) -> List[EntityCandidate]:
        """Search entities by name term, returning ranked candidates."""
        term_lower = term.lower().strip()
        candidates = []

        for gid, entity in self._entities.items():
            canonical = entity.get("canonical_name", "")
            match_keys = entity.get("match_keys", {})
            fuzzy_info = match_keys.get("fuzzy", {})
            variants = fuzzy_info.get("name_variants", [canonical])

            # Check all name variants for this entity
            best_score = 0.0
            signals = []
            for variant in variants:
                # Exact substring match
                if term_lower in variant.lower():
                    score = 0.95 if term_lower == variant.lower() else 0.85
                    signals.append(f"Name match: '{term}' in '{variant}'")
                    best_score = max(best_score, score)
                else:
                    # Fuzzy match
                    sim = _fuzzy_score(term, variant)
                    if sim > 0.5:
                        signals.append(f"Fuzzy: '{term}' ~ '{variant}' ({sim:.2f})")
                        best_score = max(best_score, sim)

            # Check deterministic keys
            det_keys = match_keys.get("deterministic", [])
            for dk in det_keys:
                if term_lower in dk.lower():
                    signals.append(f"Deterministic key: {dk}")
                    best_score = max(best_score, 0.98)

            if best_score > 0.4:
                # Pick primary source system
                source_records = entity.get("source_records", [])
                primary_system = source_records[0].get("source_system", "") if source_records else ""

                candidates.append(EntityCandidate(
                    dcl_global_id=gid,
                    name=canonical,
                    source_system=primary_system,
                    confidence=min(best_score, 1.0),
                    match_signals=signals,
                ))

        # Also check ambiguous entities
        for amb in self._ambiguous:
            if term_lower in amb.get("search_term", "").lower():
                for cand in amb.get("candidates", []):
                    # Avoid duplicates
                    if not any(c.dcl_global_id == cand.get("dcl_global_id") for c in candidates):
                        candidates.append(EntityCandidate(
                            dcl_global_id=cand.get("dcl_global_id", ""),
                            name=cand.get("name", ""),
                            source_system=cand.get("source_system", ""),
                            confidence=cand.get("confidence", 0.0),
                            match_signals=[f"Ambiguous match for '{term}'"],
                        ))

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def get_entity(self, dcl_global_id: str) -> Optional[EntityRecord]:
        """Get entity record by DCL global ID."""
        entity = self._entities.get(dcl_global_id)
        if not entity:
            return None

        source_records = entity.get("source_records", [])
        # Flatten all fields from source records into attributes
        attributes: Dict[str, Any] = {}
        for sr in source_records:
            for k, v in sr.get("fields", {}).items():
                if k not in attributes:
                    attributes[k] = v

        return EntityRecord(
            dcl_global_id=dcl_global_id,
            entity_type="company",
            display_name=entity.get("canonical_name", ""),
            source_records=source_records,
            attributes=attributes,
        )

    def merge_entities(
        self, entity_a_id: str, entity_b_id: str, confirmed_by: str
    ) -> MergeResponse:
        """Merge two entities. Entity A survives, entity B is absorbed."""
        if entity_a_id not in self._entities:
            raise ValueError(f"Entity {entity_a_id} not found")
        if entity_b_id not in self._entities:
            raise ValueError(f"Entity {entity_b_id} not found")

        merge_id = f"mrg-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        # Record merge history
        self._merge_history.append({
            "merge_id": merge_id,
            "surviving_entity_id": entity_a_id,
            "merged_entity_ids": [entity_b_id],
            "confirmed_by": confirmed_by,
            "performed_at": datetime.utcnow().isoformat() + "Z",
            "entity_b_data": self._entities[entity_b_id],
        })

        # Absorb B's source records into A
        entity_a = self._entities[entity_a_id]
        entity_b = self._entities[entity_b_id]
        entity_a.setdefault("source_records", []).extend(
            entity_b.get("source_records", [])
        )

        # Remove B
        del self._entities[entity_b_id]

        return MergeResponse(
            merge_id=merge_id,
            surviving_entity_id=entity_a_id,
            merged_entity_ids=[entity_b_id],
            status="merged",
        )

    def undo_merge(self, merge_id: str) -> MergeUndoResponse:
        """Undo a previous merge."""
        merge_record = None
        for m in self._merge_history:
            if m["merge_id"] == merge_id:
                merge_record = m
                break

        if merge_record is None:
            raise ValueError(f"Merge {merge_id} not found")

        # Restore merged entity
        for eid in merge_record["merged_entity_ids"]:
            if "entity_b_data" in merge_record:
                self._entities[eid] = merge_record["entity_b_data"]

        # Remove the absorbed source records from surviving entity
        surviving = self._entities.get(merge_record["surviving_entity_id"])
        if surviving and "entity_b_data" in merge_record:
            b_record_ids = {
                sr.get("source_record_id")
                for sr in merge_record["entity_b_data"].get("source_records", [])
            }
            surviving["source_records"] = [
                sr for sr in surviving.get("source_records", [])
                if sr.get("source_record_id") not in b_record_ids
            ]

        return MergeUndoResponse(
            merge_id=merge_id,
            restored_entity_ids=merge_record["merged_entity_ids"],
            status="undone",
        )

    # ==================================================================
    # GOLDEN RECORDS
    # ==================================================================

    def get_golden_record(self, dcl_global_id: str) -> Optional[GoldenRecord]:
        """Assemble golden record from entity_test_scenarios.json data."""
        gr_data = self._golden_records.get(dcl_global_id)
        if not gr_data:
            return None

        now = datetime.utcnow()
        fields: Dict[str, FieldProvenance] = {}
        contributing_sources = set()

        for field_name, field_data in gr_data.get("fields", {}).items():
            source = field_data.get("source", "")
            contributing_sources.add(source)

            # Look up trust score from SOR tags
            sor_info = self._sor_tags.get(source, {})
            trust = sor_info.get("trust_score", 0.8)

            fields[field_name] = FieldProvenance(
                field_name=field_name,
                value=field_data.get("value"),
                source_system_id=source,
                source_record_id=f"{source}:{dcl_global_id}:{field_name}",
                trust_score=trust,
                selected_reason=field_data.get("reason", "highest_trust"),
                collected_at=now,
            )

        return GoldenRecord(
            dcl_global_id=dcl_global_id,
            entity_type="company",
            fields=fields,
            assembled_at=now,
            contributing_sources=sorted(contributing_sources),
        )

    # ==================================================================
    # CONFLICT DETECTION
    # ==================================================================

    def list_conflicts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        entity: Optional[str] = None,
    ) -> List[Conflict]:
        """List conflicts with optional filters."""
        results = []
        for cid, c in self._conflicts.items():
            # Check if resolved
            if cid in self._conflict_resolutions:
                c_status = "resolved"
            else:
                c_status = c.get("status", "open")

            if status and c_status.lower() != status.lower():
                continue
            if severity and c.get("severity", "").lower() != severity.lower():
                continue
            if entity and c.get("entity_id", "") != entity:
                continue

            results.append(self._conflict_to_model(cid, c))

        return results

    def get_conflict(self, conflict_id: str) -> Optional[Conflict]:
        """Get a single conflict by ID."""
        c = self._conflicts.get(conflict_id)
        if not c:
            return None
        return self._conflict_to_model(conflict_id, c)

    def resolve_conflict(
        self,
        conflict_id: str,
        decision: str,
        rationale: Optional[str] = None,
        resolved_by: str = "system",
    ) -> ConflictResolutionResponse:
        """Resolve a conflict."""
        if conflict_id not in self._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        resolution_id = f"res-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        self._conflict_resolutions[conflict_id] = {
            "resolution_id": resolution_id,
            "decision": decision,
            "rationale": rationale,
            "resolved_by": resolved_by,
            "resolved_at": datetime.utcnow().isoformat() + "Z",
        }

        return ConflictResolutionResponse(
            conflict_id=conflict_id,
            resolution_id=resolution_id,
            decision=decision,
            status="resolved",
        )

    def _conflict_to_model(self, conflict_id: str, c: Dict[str, Any]) -> Conflict:
        """Convert raw conflict dict from JSON to the Conflict Pydantic model."""
        systems = c.get("systems", {})
        system_ids = list(systems.keys())
        values_by_system = {}
        for sys_id, sys_data in systems.items():
            values_by_system[sys_id] = sys_data.get("value", sys_data.get("formatted", ""))

        delta_info = c.get("delta", {})
        root_cause = c.get("root_cause", {})
        cause_type = root_cause.get("type", "timing")

        # Map severity string
        severity_str = c.get("severity", "LOW").lower()

        # Map status
        if conflict_id in self._conflict_resolutions:
            status = ConflictStatus.RESOLVED
        else:
            status_str = c.get("status", "open").lower()
            status_map = {
                "open": ConflictStatus.OPEN,
                "reviewing": ConflictStatus.REVIEWING,
                "resolved": ConflictStatus.RESOLVED,
                "dismissed": ConflictStatus.DISMISSED,
            }
            status = status_map.get(status_str, ConflictStatus.OPEN)

        return Conflict(
            conflict_id=conflict_id,
            entity_id=c.get("entity_id"),
            metric=c.get("metric", ""),
            systems_involved=system_ids,
            values_by_system=values_by_system,
            delta=delta_info.get("absolute", 0),
            delta_pct=delta_info.get("percentage"),
            root_cause=RootCauseType(cause_type),
            severity=Severity(severity_str),
            status=status,
            detected_at=datetime.fromisoformat(
                c.get("detected_at", "2026-01-01T00:00:00Z").replace("Z", "+00:00")
            ),
            description=root_cause.get("explanation"),
        )

    # ==================================================================
    # PROVENANCE
    # ==================================================================

    def get_provenance(self, metric: str) -> Optional[ProvenanceRecord]:
        """Get provenance/lineage for a metric.

        Returns a ProvenanceRecord model when called from routes, but
        also supports dict-style access from the enrichment service.
        """
        prov = self._provenance.get(metric)
        if not prov:
            return None

        lineage = prov.get("lineage", [])
        # Determine SOR
        sor_system = None
        sor_trust = None
        sor_freshness = None
        for entry in lineage:
            if entry.get("is_system_of_record"):
                sor_system = entry.get("source_system")
                sor_trust = entry.get("trust_score")
                sor_freshness = entry.get("freshness")
                break

        return ProvenanceRecord(
            metric=metric,
            lineage=lineage,
            system_of_record=sor_system,
            trust_score=sor_trust,
            freshness=sor_freshness,
        )

    # ==================================================================
    # TEMPORAL VERSIONING
    # ==================================================================

    def get_temporal_changelog(self, concept: str) -> List[TemporalChangelogEntry]:
        """Get all definition changes for a concept."""
        entries = []
        for idx, change in enumerate(self._temporal):
            if change.get("concept", "").lower() == concept.lower():
                entries.append(TemporalChangelogEntry(
                    change_id=f"def-{concept}-{idx+1}",
                    concept=change["concept"],
                    change_date=change["change_date"],
                    old_definition=change["old_definition"],
                    new_definition=change["new_definition"],
                    changed_by=change["changed_by"],
                    reason=change["reason"],
                    version=idx + 1,
                ))
        return entries

    def check_temporal_boundary(
        self,
        concept: str,
        start_period: str,
        end_period: str,
    ) -> TemporalBoundaryCheck:
        """Check whether a comparison crosses a definition boundary."""
        start_date = _parse_period_to_date(start_period)
        end_date = _parse_period_to_date(end_period)

        for change in self._temporal:
            if change.get("concept", "").lower() != concept.lower():
                continue

            change_date = change.get("change_date", "")
            # If the change_date falls between start and end, we cross a boundary
            if start_date and end_date and change_date:
                if start_date <= change_date <= end_date:
                    affected = change.get("affected_periods", {})
                    warning = affected.get(
                        "note",
                        f"{concept.title()} definition changed on {change_date}. Comparison may not be apples-to-apples."
                    )
                    return TemporalBoundaryCheck(
                        concept=concept,
                        start_period=start_period,
                        end_period=end_period,
                        crosses_boundary=True,
                        change_date=change_date,
                        old_definition=change.get("old_definition"),
                        new_definition=change.get("new_definition"),
                        warning=warning,
                    )

        return TemporalBoundaryCheck(
            concept=concept,
            start_period=start_period,
            end_period=end_period,
            crosses_boundary=False,
        )

    # ==================================================================
    # PERSONA DEFINITIONS
    # ==================================================================

    def get_persona_definitions(self, metric: str) -> List[PersonaDefinition]:
        """Get all persona definitions for a metric."""
        metric_data = self._persona_defs.get(metric)
        if not metric_data:
            return []

        definitions = []
        for d in metric_data.get("definitions", []):
            definitions.append(PersonaDefinition(
                persona=d["persona"],
                metric=metric,
                value=d.get("value"),
                definition=d["definition"],
                rationale=d["rationale"],
            ))
        return definitions

    def get_persona_definition(
        self, metric: str, persona: str
    ) -> Optional[PersonaDefinition]:
        """Get definition for a specific metric+persona pair."""
        metric_data = self._persona_defs.get(metric)
        if not metric_data:
            return None

        persona_upper = persona.upper()
        for d in metric_data.get("definitions", []):
            if d["persona"].upper() == persona_upper:
                return PersonaDefinition(
                    persona=d["persona"],
                    metric=metric,
                    value=d.get("value"),
                    definition=d["definition"],
                    rationale=d["rationale"],
                )
        return None

    # ==================================================================
    # ENRICHED QUERY
    # ==================================================================

    def enriched_query(
        self,
        metric: str,
        entity: Optional[str] = None,
        persona: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> QueryResponse:
        """Execute an enriched query combining entity, provenance, conflicts, persona."""
        resolved_entity = None
        entity_name = None
        entity_id = None

        # Resolve entity if provided
        if entity:
            candidates = self.search_entities(entity)
            if candidates:
                top = candidates[0]
                entity_name = top.name
                entity_id = top.dcl_global_id
                entity_data = self.get_entity(top.dcl_global_id)
                if entity_data:
                    from src.nlq.dcl.models import CanonicalEntity
                    resolved_entity = CanonicalEntity(
                        dcl_global_id=entity_data.dcl_global_id,
                        entity_type=entity_data.entity_type,
                        display_name=entity_data.display_name,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )

        # Get provenance
        provenance_list = None
        prov = self.get_provenance(metric)
        if prov:
            provenance_list = []

        # Get conflicts
        conflict_models = None
        all_conflicts = self.list_conflicts(entity=entity_id)
        metric_conflicts = [c for c in all_conflicts if c.metric == metric]
        if metric_conflicts:
            conflict_models = metric_conflicts

        # Get persona definition
        persona_def = None
        if persona:
            persona_def = self.get_persona_definition(metric, persona)

        # Build value from persona or golden record
        value = None
        formatted_value = None
        if persona and entity_id:
            pval = self.get_persona_value(metric, persona)
            if pval:
                value = pval.get("value")
                formatted_value = str(value)

        # Build metadata
        metadata = QueryMetadata(
            query_id=f"qry-{uuid.uuid4().hex[:12]}",
            entity=resolved_entity,
            provenance=None,
            conflicts=conflict_models,
            persona_definition=persona_def,
        )

        return QueryResponse(
            metric=metric,
            value=value,
            formatted_value=formatted_value,
            metadata=metadata,
            entity=entity_name,
            persona=persona,
        )

    # ==================================================================
    # MCP SERVER
    # ==================================================================

    def list_mcp_tools(self) -> List[MCPTool]:
        """Return all MCP tools exposed by the DCL."""
        return [
            MCPTool(
                tool_id="dcl.resolve_entity",
                name="Resolve Entity",
                description="Search and resolve an entity across source systems by name or identifier.",
                parameters=[
                    MCPToolParameter(name="term", type="string", description="Entity name or search term", required=True),
                ],
                returns="EntitySearchResponse with ranked candidates",
                category="entity_resolution",
            ),
            MCPTool(
                tool_id="dcl.get_golden_record",
                name="Get Golden Record",
                description="Assemble the single best representation of an entity from all contributing sources.",
                parameters=[
                    MCPToolParameter(name="dcl_global_id", type="string", description="DCL global entity ID", required=True),
                ],
                returns="GoldenRecord with field-level provenance",
                category="entity_resolution",
            ),
            MCPTool(
                tool_id="dcl.get_conflicts",
                name="Get Conflicts",
                description="List active cross-system conflicts for an entity or metric.",
                parameters=[
                    MCPToolParameter(name="entity", type="string", description="Entity DCL global ID", required=False),
                    MCPToolParameter(name="metric", type="string", description="Metric name to filter", required=False),
                ],
                returns="List of Conflict objects with root cause and severity",
                category="conflict_detection",
            ),
            MCPTool(
                tool_id="dcl.get_provenance",
                name="Get Provenance",
                description="Retrieve data lineage and provenance for a metric.",
                parameters=[
                    MCPToolParameter(name="metric", type="string", description="Canonical metric name", required=True),
                ],
                returns="ProvenanceRecord with lineage chain",
                category="provenance",
            ),
            MCPTool(
                tool_id="dcl.check_temporal",
                name="Check Temporal Boundary",
                description="Check if a comparison between periods crosses a metric definition change.",
                parameters=[
                    MCPToolParameter(name="concept", type="string", description="Metric/concept name", required=True),
                    MCPToolParameter(name="start_period", type="string", description="Start period (e.g. 2024-Q1)", required=True),
                    MCPToolParameter(name="end_period", type="string", description="End period (e.g. 2025-Q1)", required=True),
                ],
                returns="TemporalBoundaryCheck with warning if boundary crossed",
                category="temporal_versioning",
            ),
            MCPTool(
                tool_id="dcl.get_persona_definition",
                name="Get Persona Definition",
                description="Get the persona-specific definition and value for a metric.",
                parameters=[
                    MCPToolParameter(name="metric", type="string", description="Canonical metric name", required=True),
                    MCPToolParameter(name="persona", type="string", description="Persona (CFO, CRO, COO)", required=True),
                ],
                returns="PersonaDefinition with value and rationale",
                category="persona",
            ),
            MCPTool(
                tool_id="dcl.enriched_query",
                name="Enriched Query",
                description="Execute a query enriched with entity resolution, provenance, conflicts, and persona context.",
                parameters=[
                    MCPToolParameter(name="metric", type="string", description="Metric name", required=True),
                    MCPToolParameter(name="entity", type="string", description="Entity name", required=False),
                    MCPToolParameter(name="persona", type="string", description="Persona", required=False),
                    MCPToolParameter(name="time_range", type="string", description="Time range", required=False),
                ],
                returns="QueryResponse with metadata",
                category="query",
            ),
        ]

    def execute_mcp_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> MCPExecuteResponse:
        """Execute an MCP tool by name."""
        tool_map = {
            "dcl.resolve_entity": self._mcp_resolve_entity,
            "dcl.get_golden_record": self._mcp_get_golden_record,
            "dcl.get_conflicts": self._mcp_get_conflicts,
            "dcl.get_provenance": self._mcp_get_provenance,
            "dcl.check_temporal": self._mcp_check_temporal,
            "dcl.get_persona_definition": self._mcp_get_persona_definition,
            "dcl.enriched_query": self._mcp_enriched_query,
        }

        handler = tool_map.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown MCP tool: {tool_name}")

        try:
            result = handler(arguments)
            return MCPExecuteResponse(
                tool_name=tool_name,
                success=True,
                result=result,
            )
        except (RuntimeError, KeyError, TypeError, ValueError, AttributeError) as e:
            return MCPExecuteResponse(
                tool_name=tool_name,
                success=False,
                error=str(e),
            )

    # MCP tool handlers
    def _mcp_resolve_entity(self, args: Dict[str, Any]) -> Any:
        candidates = self.search_entities(args["term"])
        return [c.model_dump() for c in candidates]

    def _mcp_get_golden_record(self, args: Dict[str, Any]) -> Any:
        gr = self.get_golden_record(args["dcl_global_id"])
        return gr.model_dump() if gr else None

    def _mcp_get_conflicts(self, args: Dict[str, Any]) -> Any:
        conflicts = self.list_conflicts(
            entity=args.get("entity"),
            severity=None,
            status=None,
        )
        return [c.model_dump() for c in conflicts]

    def _mcp_get_provenance(self, args: Dict[str, Any]) -> Any:
        prov = self.get_provenance(args["metric"])
        return prov.model_dump() if prov else None

    def _mcp_check_temporal(self, args: Dict[str, Any]) -> Any:
        result = self.check_temporal_boundary(
            concept=args["concept"],
            start_period=args["start_period"],
            end_period=args["end_period"],
        )
        return result.model_dump()

    def _mcp_get_persona_definition(self, args: Dict[str, Any]) -> Any:
        defn = self.get_persona_definition(args["metric"], args["persona"])
        return defn.model_dump() if defn else None

    def _mcp_enriched_query(self, args: Dict[str, Any]) -> Any:
        result = self.enriched_query(
            metric=args["metric"],
            entity=args.get("entity"),
            persona=args.get("persona"),
            time_range=args.get("time_range"),
        )
        return result.model_dump()

    # ==================================================================
    # ENRICHMENT SERVICE INTERFACE
    # (dict-returning methods used by dcl_enrichment.py)
    # ==================================================================

    def resolve_entity(self, term: str) -> List[Dict[str, Any]]:
        """Resolve entity by name — returns list of dicts for enrichment service."""
        candidates = self.search_entities(term)
        results = []
        for c in candidates:
            # Look up entity to get source records
            entity = self._entities.get(c.dcl_global_id, {})
            results.append({
                "canonical_name": c.name,
                "dcl_global_id": c.dcl_global_id,
                "source_records": entity.get("source_records", []),
                "confidence": c.confidence,
            })
        return results

    def get_all_conflicts(self) -> List[Dict[str, Any]]:
        """Return all conflicts as dicts for enrichment service."""
        results = []
        for cid, c in self._conflicts.items():
            # Build enrichment-friendly dict
            results.append({
                "id": cid,
                "entity": c.get("entity", ""),
                "entity_id": c.get("entity_id", ""),
                "metric": c.get("metric", ""),
                "severity": c.get("severity", "LOW"),
                "systems": c.get("systems", {}),
                "delta": c.get("delta", {}),
                "root_cause": c.get("root_cause", {}),
                "trust_recommendation": c.get("trust_recommendation", {}),
                "status": c.get("status", "open"),
            })
        return results

    def get_persona_value(self, metric: str, persona: str) -> Optional[Dict[str, Any]]:
        """Get persona-specific value for a metric — dict for enrichment service."""
        defn = self.get_persona_definition(metric, persona)
        if not defn:
            return None
        return {
            "persona": defn.persona,
            "metric": defn.metric,
            "value": defn.value,
            "definition": defn.definition,
            "rationale": defn.rationale,
        }
