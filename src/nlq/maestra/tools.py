"""
Maestra LLM tools — Claude function calling definitions + processors.

8 original tools (ported from dcl-onboarding-agent):
    1. update_contour    — update contour map dimension
    2. show_comparison   — side-by-side conflict display
    3. show_hierarchy    — collapsible tree view
    4. show_table        — tabular data in chat
    5. park_item         — defer topic for follow-up
    6. advance_section   — move to next interview section
    7. process_file      — handle uploaded files
    8. lookup_system_data — query discovered system data

3 Convergence tools:
    9. compare_entities    — cross-entity comparison
   10. navigate_portal     — switch portal view
   11. query_engine        — pull data from engines
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from src.nlq.maestra.types import (
    Conflict,
    ConflictStatus,
    ContourMap,
    FollowUpTask,
    HierarchyNode,
    NodeType,
    PriorityQuery,
    Provenance,
    SOREntry,
    VocabularyEntry,
)
from src.nlq.maestra.completeness import calculate_contour_completeness
from src.nlq.maestra.state import ActionType, StateAction

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL DEFINITIONS (for Claude API tool_use)
# =============================================================================

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "update_contour",
        "description": "Add, update, or remove nodes in the Enterprise Contour Map. Call immediately when the stakeholder provides organizational data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension_type": {
                    "type": "string",
                    "enum": [
                        "organizational_hierarchy",
                        "sor_authority_map",
                        "conflict_register",
                        "management_overlay",
                        "vocabulary_map",
                        "priority_queries",
                    ],
                    "description": "Which dimension of the contour map to update.",
                },
                "operation": {
                    "type": "string",
                    "enum": ["add", "update", "remove"],
                    "description": "Operation to perform.",
                },
                "node_data": {
                    "type": "object",
                    "description": "Data for the node. Shape depends on dimension_type.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0-1. Default 0.8.",
                },
                "provenance": {
                    "type": "string",
                    "enum": [
                        "PUBLIC_FILING",
                        "SYSTEM_EXTRACTED",
                        "STAKEHOLDER_CONFIRMED",
                        "STAKEHOLDER_FILE",
                        "INFERRED",
                        "UNVERIFIED",
                    ],
                    "description": "Data provenance. Default STAKEHOLDER_CONFIRMED.",
                },
            },
            "required": ["dimension_type", "operation", "node_data"],
        },
    },
    {
        "name": "show_comparison",
        "description": "Display a side-by-side comparison of values from different systems for conflict resolution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "The dimension being compared (e.g., 'Cost Centers').",
                },
                "systems": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "system": {"type": "string"},
                            "value": {"type": "string"},
                            "is_match": {"type": "boolean"},
                        },
                        "required": ["system", "value"],
                    },
                    "description": "Systems and their values for comparison.",
                },
            },
            "required": ["dimension", "systems"],
        },
    },
    {
        "name": "show_hierarchy",
        "description": "Display an organizational tree view in the chat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title for the hierarchy display."},
                "root": {
                    "type": "object",
                    "description": "Root node with name and optional children array (recursive).",
                    "properties": {
                        "name": {"type": "string"},
                        "children": {"type": "array"},
                    },
                    "required": ["name"],
                },
            },
            "required": ["title", "root"],
        },
    },
    {
        "name": "show_table",
        "description": "Display tabular data inline in the chat message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Table title."},
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column headers.",
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "Table rows (2D array of strings).",
                },
            },
            "required": ["headers", "rows"],
        },
    },
    {
        "name": "park_item",
        "description": "Park an unresolved topic as a follow-up task. Never push >5 min on one topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Topic being parked."},
                "question": {"type": "string", "description": "The unresolved question."},
                "suggested_person": {
                    "type": "string",
                    "description": "Who might know the answer.",
                },
            },
            "required": ["dimension", "question"],
        },
    },
    {
        "name": "advance_section",
        "description": "Mark current section COMPLETE and advance to the next. Call when exit criteria for current section are met.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was captured in this section.",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "process_file",
        "description": "Process an uploaded file to extract organizational data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "ID of the uploaded file."},
                "analysis_focus": {
                    "type": "string",
                    "description": "Optional focus area (e.g., 'organizational hierarchy').",
                },
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "lookup_system_data",
        "description": "Query AOD/AAM/DCL for discovered system data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["systems", "connections", "dimension_data", "graph_summary"],
                    "description": "Type of data to look up.",
                },
                "system_name": {
                    "type": "string",
                    "description": "Filter by specific system name.",
                },
                "dimension": {
                    "type": "string",
                    "description": "For dimension_data queries.",
                },
            },
            "required": ["query_type"],
        },
    },
    # === CONVERGENCE TOOLS ===
    {
        "name": "compare_entities",
        "description": "Compare a specific dimension across both entities' contour maps. Shows alignment, conflicts, and materiality.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "The dimension to compare across entities.",
                },
            },
            "required": ["dimension"],
        },
    },
    {
        "name": "navigate_portal",
        "description": "Navigate the report portal to a specific tab/view. The portal switches to show the referenced data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tab": {
                    "type": "string",
                    "enum": [
                        "pl", "bs", "socf", "drill", "recon",
                        "combining", "overlap", "cross_sell",
                        "ebitda", "what_if", "qoe", "dashboard",
                    ],
                    "description": "Which portal tab to navigate to.",
                },
                "entity": {
                    "type": "string",
                    "enum": ["meridian", "cascadia", "combined"],
                    "description": "Optional entity filter.",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters to apply.",
                },
            },
            "required": ["tab"],
        },
    },
    {
        "name": "query_engine",
        "description": "Query cross-sell pipeline, EBITDA bridge, QofE, entity resolution, or COFA mapping. Returns exact numbers from engine outputs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "enum": [
                        "cross_sell", "ebitda_bridge", "qoe",
                        "entity_resolution", "cofa_mapping",
                    ],
                    "description": "Which engine to query.",
                },
                "query": {
                    "type": "object",
                    "description": "Engine-specific query parameters.",
                },
            },
            "required": ["engine"],
        },
    },
    {
        "name": "configure_scope",
        "description": "Set the DD scope — toggle deliverables on/off and confirm the configuration. Present as a checklist for the deal person to confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deliverable_selections": {
                    "type": "object",
                    "description": "Map of deliverable_id → boolean (selected or not). IDs: crm_integration, cross_sell, customer_migration, portfolio_rationalization, tech_integration, ebitda_bridge.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Whether the deal person has confirmed the scope.",
                },
            },
            "required": ["confirmed"],
        },
    },
]


# =============================================================================
# TOOL PROCESSORS
# =============================================================================

def process_update_contour(
    contour: ContourMap,
    dimension_type: str,
    operation: str,
    node_data: dict[str, Any],
    confidence: float = 0.8,
    provenance: str = "STAKEHOLDER_CONFIRMED",
) -> tuple[ContourMap, dict[str, Any]]:
    """
    Process update_contour tool call. Mutates the contour map in place.
    Returns (updated_contour, tool_result).
    """
    prov = Provenance(provenance) if provenance in Provenance.__members__ else Provenance.STAKEHOLDER_CONFIRMED

    if dimension_type == "organizational_hierarchy":
        node = HierarchyNode(
            id=node_data.get("id", str(uuid.uuid4())[:8]),
            name=node_data.get("name", ""),
            type=NodeType(node_data.get("type", "DIVISION")),
            level=node_data.get("level", 0),
            parent_id=node_data.get("parent_id"),
            source_system=node_data.get("source_system", ""),
            source_field=node_data.get("source_field", ""),
            confidence=confidence,
            provenance=prov,
            notes=node_data.get("notes", ""),
        )
        if node_data.get("children"):
            node.children = [
                HierarchyNode(**{**c, "confidence": confidence, "provenance": prov})
                for c in node_data["children"]
                if isinstance(c, dict)
            ]
        if operation == "add":
            contour.organizational_hierarchy.append(node)
        elif operation == "update":
            _update_in_list(contour.organizational_hierarchy, node)
        elif operation == "remove":
            contour.organizational_hierarchy = [
                n for n in contour.organizational_hierarchy if n.id != node.id
            ]

    elif dimension_type == "sor_authority_map":
        entry = SOREntry(
            dimension=node_data.get("dimension", ""),
            system=node_data.get("system", ""),
            confidence=confidence,
            confirmed_by=node_data.get("confirmed_by"),
            conflicts=node_data.get("conflicts", []),
            notes=node_data.get("notes", ""),
        )
        if operation == "add":
            contour.sor_authority_map.append(entry)
        elif operation == "update":
            for i, e in enumerate(contour.sor_authority_map):
                if e.dimension == entry.dimension:
                    contour.sor_authority_map[i] = entry
                    break
            else:
                contour.sor_authority_map.append(entry)

    elif dimension_type == "conflict_register":
        conflict = Conflict(
            id=node_data.get("id", str(uuid.uuid4())[:8]),
            dimension=node_data.get("dimension", ""),
            systems=node_data.get("systems", []),
            resolution=node_data.get("resolution"),
            resolved_by=node_data.get("resolved_by"),
            status=ConflictStatus(node_data.get("status", "OPEN")),
        )
        if operation == "add":
            contour.conflict_register.append(conflict)
        elif operation == "update":
            for i, c in enumerate(contour.conflict_register):
                if c.id == conflict.id:
                    contour.conflict_register[i] = conflict
                    break

    elif dimension_type == "management_overlay":
        node = HierarchyNode(
            id=node_data.get("id", str(uuid.uuid4())[:8]),
            name=node_data.get("name", ""),
            level=node_data.get("level", 0),
            confidence=confidence,
            provenance=prov,
        )
        if operation == "add":
            contour.management_overlay.append(node)

    elif dimension_type == "vocabulary_map":
        entry = VocabularyEntry(
            term=node_data.get("term", ""),
            meaning=node_data.get("meaning", ""),
            context=node_data.get("context", ""),
            system_equivalent=node_data.get("system_equivalent"),
        )
        if operation == "add":
            contour.vocabulary_map.append(entry)

    elif dimension_type == "priority_queries":
        query = PriorityQuery(
            id=node_data.get("id", str(uuid.uuid4())[:8]),
            question=node_data.get("question", ""),
            business_context=node_data.get("business_context", ""),
            frequency=node_data.get("frequency", ""),
            current_pain=node_data.get("current_pain", ""),
            priority=node_data.get("priority", 5),
        )
        if operation == "add":
            contour.priority_queries.append(query)

    # Recalculate completeness
    contour.metadata.completeness_score = calculate_contour_completeness(contour)
    contour.metadata.last_updated = datetime.utcnow().isoformat()

    return contour, {
        "success": True,
        "dimension_type": dimension_type,
        "operation": operation,
        "completeness_score": contour.metadata.completeness_score,
    }


def process_show_comparison(
    dimension: str,
    systems: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process show_comparison. Returns (rich_content, tool_result)."""
    rich = {
        "type": "comparison",
        "dimension": dimension,
        "systems": systems,
    }
    return rich, {"success": True, "displayed": "comparison", "dimension": dimension}


def process_show_hierarchy(
    title: str,
    root: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process show_hierarchy. Returns (rich_content, tool_result)."""
    rich = {
        "type": "hierarchy",
        "title": title,
        "root": root,
    }
    return rich, {"success": True, "displayed": "hierarchy", "title": title}


def process_show_table(
    headers: list[str],
    rows: list[list[str]],
    title: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process show_table. Returns (rich_content, tool_result)."""
    rich = {
        "type": "table",
        "title": title,
        "headers": headers,
        "rows": rows,
    }
    return rich, {"success": True, "displayed": "table", "title": title, "rows": len(rows)}


def process_park_item(
    contour: ContourMap,
    dimension: str,
    question: str,
    suggested_person: str | None = None,
    current_section: str = "",
) -> tuple[ContourMap, dict[str, Any]]:
    """Process park_item. Adds follow-up task to contour map."""
    task = FollowUpTask(
        description=f"[{dimension}] {question}",
        assigned_to=suggested_person,
        section=current_section,
    )
    contour.follow_up_tasks.append(task)
    contour.metadata.last_updated = datetime.utcnow().isoformat()

    return contour, {
        "success": True,
        "parked": dimension,
        "question": question,
        "assigned_to": suggested_person,
        "task_id": task.id,
    }


def process_advance_section(summary: str) -> tuple[StateAction, dict[str, Any]]:
    """Process advance_section. Returns state action + tool result."""
    action = StateAction(
        action_type=ActionType.ADVANCE,
        summary=summary,
    )
    return action, {"success": True, "action": "ADVANCE", "summary": summary}


def process_navigate_portal(
    tab: str,
    entity: str | None = None,
    filters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process navigate_portal. Returns navigation command + tool result."""
    nav = {
        "type": "navigation",
        "tab": tab,
        "entity": entity,
        "filters": filters or {},
    }
    return nav, {"success": True, "navigated_to": tab, "entity": entity}


def process_query_engine(
    engine: str,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Process query_engine. Returns demo data from seed_data.
    In production, this would call actual engine endpoints.
    """
    from src.nlq.maestra.seed_data import (
        get_cofa_mapping_data,
        get_cross_sell_data,
        get_ebitda_bridge_data,
        get_entity_overlap_data,
        get_qoe_data,
    )

    engine_data = {
        "cross_sell": get_cross_sell_data,
        "ebitda_bridge": get_ebitda_bridge_data,
        "qoe": get_qoe_data,
        "entity_resolution": get_entity_overlap_data,
        "cofa_mapping": get_cofa_mapping_data,
    }

    loader = engine_data.get(engine)
    if loader:
        return loader()

    return {
        "success": True,
        "engine": engine,
        "note": f"Unknown engine: {engine}",
    }


def process_configure_scope(
    deliverable_selections: dict[str, bool] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """
    Process configure_scope. Records DD scope selections.
    Returns the confirmed scope configuration.
    """
    from src.nlq.maestra.types import DDScope

    scope = DDScope()

    if deliverable_selections:
        for d in scope.deliverables:
            if d.id in deliverable_selections:
                d.selected = deliverable_selections[d.id]

    scope.confirmed = confirmed

    selected_names = [d.name for d in scope.deliverables if d.selected]

    return {
        "success": True,
        "confirmed": confirmed,
        "selected_deliverables": selected_names,
        "reconciliation_objects": scope.reconciliation_objects,
        "synergy_targets": scope.synergy_targets,
        "scope": scope.model_dump(),
    }


def _update_in_list(nodes: list[HierarchyNode], updated: HierarchyNode) -> None:
    """Update a node in a list by matching id."""
    for i, n in enumerate(nodes):
        if n.id == updated.id:
            nodes[i] = updated
            return
    nodes.append(updated)
