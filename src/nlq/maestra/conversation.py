"""
Maestra conversation service — orchestrates LLM calls, tool processing, state management.

This is the heart of Maestra. It:
1. Builds conversation history from stored messages
2. Composes the system prompt from 4 layers
3. Calls Claude with tool definitions
4. Processes tool calls in a loop (max 10 rounds)
5. Accumulates rich content for the frontend
6. Persists state changes (contour map, session state, messages)

Ported from dcl-onboarding-agent conversation.service.ts
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

import anthropic

from src.nlq.maestra.types import (
    ContourMap,
    ConversationState,
    DemoPhase,
    EngagementMode,
    EngagementPhase,
    IntelBrief,
    MaestraEngagement,
    MaestraMessage,
    MaestraSession,
    PreDealContext,
    SectionId,
    SectionStatus,
    SessionStatus,
)
from src.nlq.maestra.state import (
    ActionType,
    StateAction,
    calculate_completion_pct,
    reduce_state,
)
from src.nlq.maestra.completeness import calculate_contour_completeness
from src.nlq.maestra.prompts import compose_system_prompt
from src.nlq.maestra.tools import (
    TOOL_DEFINITIONS,
    process_advance_section,
    process_configure_scope,
    process_navigate_portal,
    process_park_item,
    process_query_engine,
    process_show_comparison,
    process_show_hierarchy,
    process_show_table,
    process_update_contour,
)
from src.nlq.maestra.persistence import get_maestra_persistence

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
MAESTRA_MODEL = os.environ.get("MAESTRA_MODEL", "claude-sonnet-4-20250514")
MAESTRA_MAX_TOKENS = 4096


class ConversationService:
    """
    Manages Maestra conversations with Claude.

    Stateless service — all state is loaded from/saved to persistence.
    """

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY required for Maestra. "
                "Set it in environment variables."
            )
        self._anthropic = anthropic.Anthropic(
            api_key=api_key,
            timeout=60.0,
        )
        self._persistence = get_maestra_persistence()

    # =========================================================================
    # PUBLIC: CREATE ENGAGEMENT
    # =========================================================================

    def create_engagement(
        self,
        deal_name: str = "Meridian-Cascadia Integration",
        entities: list[dict[str, str]] | None = None,
        demo_mode: bool = True,
        mode: str = "pre_deal",
    ) -> dict[str, Any]:
        """
        Create a new engagement with prework pipeline.

        In pre_deal mode: runs prework, creates a single unified session.
        In classic mode: creates per-entity sessions with demo phases.
        """
        if entities is None:
            entities = [
                {"id": "meridian", "name": "Meridian Partners"},
                {"id": "cascadia", "name": "Cascadia Advisory"},
            ]

        engagement_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        eng_mode = EngagementMode(mode)

        if eng_mode == EngagementMode.PRE_DEAL:
            return self._create_pre_deal_engagement(
                engagement_id, deal_name, entities, demo_mode, now,
            )
        else:
            return self._create_classic_engagement(
                engagement_id, deal_name, entities, demo_mode, now,
            )

    def _create_pre_deal_engagement(
        self,
        engagement_id: str,
        deal_name: str,
        entities: list[dict[str, str]],
        demo_mode: bool,
        now: str,
    ) -> dict[str, Any]:
        """Create a pre-deal engagement with prework pipeline."""
        # Run prework — load seed data for both entities
        pre_deal_context = self._run_prework(entities, demo_mode)

        phase = EngagementPhase.PREWORK_COMPLETE

        engagement = MaestraEngagement(
            engagement_id=engagement_id,
            deal_name=deal_name,
            mode=EngagementMode.PRE_DEAL,
            phase=phase,
            entities=entities,
            pre_deal_context=pre_deal_context,
            created_at=now,
            updated_at=now,
        )

        # Save engagement
        self._persistence.save_engagement({
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.PRE_DEAL.value,
            "phase": phase.value,
            "entities": entities,
            "objects_in_scope": engagement.objects_in_scope,
            "session_ids": [],
            "stakeholder_map": engagement.stakeholder_map,
            "timeline": engagement.timeline,
            "pre_deal_context": pre_deal_context.model_dump(),
            "created_at": now,
            "updated_at": now,
        })

        # Create single unified session for pre-deal interview
        pd_section_statuses = {
            "PDC": SectionStatus.NOT_STARTED.value,
            "PDA": SectionStatus.NOT_STARTED.value,
            "PDT": SectionStatus.NOT_STARTED.value,
            "PDS": SectionStatus.NOT_STARTED.value,
            "PDR": SectionStatus.NOT_STARTED.value,
            "PDF": SectionStatus.NOT_STARTED.value,
        }

        session_id = str(uuid.uuid4())
        self._persistence.save_session({
            "session_id": session_id,
            "engagement_id": engagement_id,
            "entity_id": "combined",
            "status": SessionStatus.READY.value,
            "current_section": SectionId.PDC.value,
            "section_statuses": pd_section_statuses,
            "contour_map": ContourMap().model_dump(),
            "intel_brief": None,
            "demo_phase": None,
            "customer_name": deal_name,
            "stakeholder_name": "Deal Team" if not demo_mode else "Jordan Chen",
            "stakeholder_role": "Deal Lead" if not demo_mode else "VP of Data",
            "created_at": now,
            "updated_at": now,
        })

        # Update engagement with session ID
        self._persistence.save_engagement({
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.PRE_DEAL.value,
            "phase": phase.value,
            "entities": entities,
            "objects_in_scope": engagement.objects_in_scope,
            "session_ids": [session_id],
            "stakeholder_map": engagement.stakeholder_map,
            "timeline": engagement.timeline,
            "pre_deal_context": pre_deal_context.model_dump(),
            "created_at": now,
            "updated_at": now,
        })

        return {
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.PRE_DEAL.value,
            "phase": phase.value,
            "workstreams": len(engagement.objects_in_scope),
            "risks": 0,
            "session_ids": [session_id],
            "entities": entities,
            "prework_complete": True,
        }

    def _create_classic_engagement(
        self,
        engagement_id: str,
        deal_name: str,
        entities: list[dict[str, str]],
        demo_mode: bool,
        now: str,
    ) -> dict[str, Any]:
        """Create a classic per-entity engagement."""
        engagement = MaestraEngagement(
            engagement_id=engagement_id,
            deal_name=deal_name,
            mode=EngagementMode.CLASSIC,
            entities=entities,
            created_at=now,
            updated_at=now,
        )

        self._persistence.save_engagement({
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.CLASSIC.value,
            "phase": engagement.phase.value,
            "entities": entities,
            "objects_in_scope": engagement.objects_in_scope,
            "session_ids": [],
            "stakeholder_map": engagement.stakeholder_map,
            "timeline": engagement.timeline,
            "created_at": now,
            "updated_at": now,
        })

        session_ids = []
        for entity in entities:
            session = MaestraSession(
                session_id=str(uuid.uuid4()),
                engagement_id=engagement_id,
                entity_id=entity["id"],
                customer_name=entity["name"],
                stakeholder_name="Jordan Chen" if demo_mode else "",
                stakeholder_role="VP of Data" if demo_mode else "",
                demo_phase=DemoPhase.PHASE_1_CONTEXT if demo_mode else None,
            )
            session_ids.append(session.session_id)

            self._persistence.save_session({
                "session_id": session.session_id,
                "engagement_id": engagement_id,
                "entity_id": entity["id"],
                "status": session.status.value,
                "current_section": session.current_section.value,
                "section_statuses": session.section_statuses,
                "contour_map": session.contour_map.model_dump(),
                "intel_brief": session.intel_brief.model_dump() if session.intel_brief else None,
                "demo_phase": session.demo_phase.value if session.demo_phase else None,
                "customer_name": session.customer_name,
                "stakeholder_name": session.stakeholder_name,
                "stakeholder_role": session.stakeholder_role,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })

        engagement.session_ids = session_ids
        self._persistence.save_engagement({
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.CLASSIC.value,
            "phase": engagement.phase.value,
            "entities": entities,
            "objects_in_scope": engagement.objects_in_scope,
            "session_ids": session_ids,
            "stakeholder_map": engagement.stakeholder_map,
            "timeline": engagement.timeline,
            "created_at": now,
            "updated_at": now,
        })

        return {
            "engagement_id": engagement_id,
            "deal_name": deal_name,
            "mode": EngagementMode.CLASSIC.value,
            "phase": engagement.phase.value,
            "workstreams": len(engagement.objects_in_scope),
            "risks": 0,
            "session_ids": session_ids,
            "entities": entities,
        }

    def _run_prework(
        self,
        entities: list[dict[str, str]],
        demo_mode: bool,
    ) -> PreDealContext:
        """
        Run prework pipeline — load all available data into engagement context.

        In demo mode: loads seed data for Meridian and Cascadia.
        In production: would ingest public filings, parse term sheet, run AOD/AAM.
        """
        from src.nlq.maestra.seed_data import get_cascadia_intel, get_meridian_intel

        ctx = PreDealContext()

        # Load entity intel briefs
        ctx.acquirer_intel = get_meridian_intel()
        ctx.target_intel = get_cascadia_intel()

        # Load system data
        systems_data = self._lookup_system_data("systems")
        all_systems = systems_data.get("systems", [])
        ctx.acquirer_systems = [s for s in all_systems if s.get("entity") == "Meridian"]
        ctx.target_systems = [s for s in all_systems if s.get("entity") == "Cascadia"]

        # Load connections
        connections_data = self._lookup_system_data("connections")
        ctx.system_connections = connections_data.get("connections", [])

        ctx.prework_complete = True

        logger.info("Prework complete: loaded intel briefs, %d systems, %d connections",
                     len(all_systems), len(ctx.system_connections))

        return ctx

    # =========================================================================
    # PUBLIC: SEND MESSAGE
    # =========================================================================

    def send_message(
        self,
        engagement_id: str,
        message: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a stakeholder message and get Maestra's response.

        If session_id not provided, uses the first session for this engagement.
        """
        # Load session
        session = self._load_session(engagement_id, session_id)
        if not session:
            return {
                "response": f"No active session found for engagement {engagement_id}.",
                "actions_taken": [],
                "suggestions": [],
                "phase": "unknown",
                "error": True,
            }

        # Build contour map from session data
        contour = ContourMap(**session.get("contour_map", {}))
        current_section = SectionId(session.get("current_section", "1"))
        section_statuses = session.get("section_statuses", {})
        demo_phase_str = session.get("demo_phase")
        demo_phase = DemoPhase(demo_phase_str) if demo_phase_str else None

        intel_brief_data = session.get("intel_brief")
        intel_brief = IntelBrief(**intel_brief_data) if intel_brief_data else None

        # Load pre-deal context if in pre-deal mode
        pre_deal_context = None
        is_pre_deal = current_section.value.startswith("PD")
        if is_pre_deal:
            eng = self._persistence.get_engagement(engagement_id)
            if eng:
                pdc_data = eng.get("pre_deal_context")
                if pdc_data:
                    pre_deal_context = PreDealContext(**pdc_data)

        # Save stakeholder message
        sid = session["session_id"]
        self._persistence.save_message({
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "role": "stakeholder",
            "content": message,
            "rich_content": [],
            "section": current_section.value,
            "created_at": datetime.utcnow().isoformat(),
        })

        # Load conversation history
        history = self._build_history(sid)

        # Compose system prompt
        system_prompt = compose_system_prompt(
            section=current_section,
            customer_name=session.get("customer_name", ""),
            stakeholder_name=session.get("stakeholder_name", ""),
            stakeholder_role=session.get("stakeholder_role", ""),
            contour_map=contour,
            intel_brief=intel_brief,
            demo_phase=demo_phase,
            interview_section=current_section if demo_phase == DemoPhase.PHASE_4_ONBOARDING else None,
            pre_deal_context=pre_deal_context,
        )

        # Call Claude with tools
        agent_text, display_content, actions_taken, navigation, state_action = (
            self._run_tool_loop(system_prompt, history, contour, current_section.value)
        )

        # Apply state action if advance_section was called
        if state_action:
            conv_state = ConversationState(
                status=SessionStatus(session.get("status", "IN_PROGRESS")),
                current_section=current_section,
                section_statuses=section_statuses,
            )
            new_state = reduce_state(conv_state, state_action)
            current_section = new_state.current_section
            section_statuses = new_state.section_statuses
            session_status = new_state.status.value

            # Advance demo phase if in classic demo mode
            if demo_phase and state_action.type == ActionType.ADVANCE:
                demo_phase = _next_demo_phase(demo_phase)

            # Update engagement phase for pre-deal mode
            if is_pre_deal and state_action.type == ActionType.ADVANCE:
                self._update_engagement_phase(engagement_id, current_section, pre_deal_context)
        else:
            session_status = "IN_PROGRESS"

        # Calculate completeness
        completeness = calculate_contour_completeness(contour)

        # Save agent message
        self._persistence.save_message({
            "id": str(uuid.uuid4()),
            "session_id": sid,
            "role": "agent",
            "content": agent_text,
            "rich_content": display_content,
            "section": current_section.value,
            "created_at": datetime.utcnow().isoformat(),
        })

        # Update session state
        self._persistence.save_session({
            "session_id": sid,
            "engagement_id": engagement_id,
            "entity_id": session.get("entity_id", ""),
            "status": session_status,
            "current_section": current_section.value,
            "section_statuses": section_statuses,
            "contour_map": contour.model_dump(),
            "intel_brief": intel_brief.model_dump() if intel_brief else None,
            "demo_phase": demo_phase.value if demo_phase else None,
            "customer_name": session.get("customer_name", ""),
            "stakeholder_name": session.get("stakeholder_name", ""),
            "stakeholder_role": session.get("stakeholder_role", ""),
            "created_at": session.get("created_at", ""),
            "updated_at": datetime.utcnow().isoformat(),
        })

        # Save contour map separately for cross-session access
        self._persistence.save_contour_map(
            engagement_id=engagement_id,
            entity_id=session.get("entity_id", ""),
            contour_data=contour.model_dump(),
            completeness_score=completeness,
        )

        # Build suggestions based on state
        suggestions = self._build_suggestions(
            current_section, section_statuses, demo_phase,
        )

        return {
            "response": agent_text,
            "rich_content": display_content,
            "actions_taken": actions_taken,
            "suggestions": suggestions,
            "phase": self._get_phase_label(engagement_id, demo_phase, session_status, is_pre_deal),
            "section": current_section.value,
            "completeness": completeness,
            "navigation": navigation,
        }

    # =========================================================================
    # PUBLIC: GET STATUS
    # =========================================================================

    def get_status(self, engagement_id: str) -> dict[str, Any]:
        """Get engagement status with workstream summary."""
        eng = self._persistence.get_engagement(engagement_id)
        if not eng:
            return {"error": f"Engagement {engagement_id} not found"}

        sessions = self._persistence.get_sessions_for_engagement(engagement_id)
        contour_maps = self._persistence.get_contour_maps_for_engagement(engagement_id)

        # Workstream summary from sessions
        workstream_summary = []
        for session in sessions:
            entity_id = session.get("entity_id", "unknown")
            section_statuses = session.get("section_statuses", {})
            pct = calculate_completion_pct(section_statuses)
            workstream_summary.append({
                "name": f"{entity_id} scoping",
                "status": session.get("status", "unknown"),
                "progress_pct": pct,
            })

        # Overall progress
        if workstream_summary:
            overall_pct = sum(w["progress_pct"] for w in workstream_summary) / len(workstream_summary)
        else:
            overall_pct = 0

        # Entity completeness from contour maps
        entity_completeness = {
            cm.get("entity_id", ""): cm.get("completeness_score", 0)
            for cm in contour_maps
        }

        # Days since start
        created = eng.get("created_at", "")
        days = 0
        if created:
            try:
                start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days = (datetime.utcnow() - start.replace(tzinfo=None)).days
            except (ValueError, TypeError):
                pass

        return {
            "phase": eng.get("phase", "scoping"),
            "deal_name": eng.get("deal_name", ""),
            "overall_progress_pct": round(overall_pct),
            "workstream_summary": workstream_summary,
            "open_risks": 0,
            "synergy_realization_pct": 0,
            "days_since_start": days,
            "next_milestones": [],
            "entity_completeness": entity_completeness,
        }

    # =========================================================================
    # INTERNAL: TOOL LOOP
    # =========================================================================

    def _run_tool_loop(
        self,
        system_prompt: str,
        history: list[dict[str, Any]],
        contour: ContourMap,
        current_section: str,
    ) -> tuple[str, list[dict], list[str], dict | None, StateAction | None]:
        """
        Call Claude with tools and process tool calls in a loop.

        Returns:
            (agent_text, display_content, actions_taken, navigation, state_action)
        """
        display_content: list[dict] = []
        actions_taken: list[str] = []
        navigation: dict | None = None
        state_action: StateAction | None = None
        agent_text = ""

        messages = list(history)  # copy

        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = self._anthropic.messages.create(
                    model=MAESTRA_MODEL,
                    max_tokens=MAESTRA_MAX_TOKENS,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                )
            except anthropic.APIError as e:
                logger.error(f"Claude API error in Maestra tool loop round {round_num}: {e}")
                if not agent_text:
                    agent_text = f"I encountered an issue connecting to my reasoning engine. Please try again. (Error: {type(e).__name__})"
                break

            # Extract text and tool_use blocks
            text_parts = []
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(block)

            if text_parts:
                agent_text = "\n".join(text_parts)

            if not tool_calls:
                break  # No more tools to process

            # Process each tool call
            tool_results = []
            for tc in tool_calls:
                result, rich, action_desc, nav, sa = self._process_tool_call(
                    tc.name, tc.input, contour, current_section,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(result),
                })
                if rich:
                    display_content.append(rich)
                if action_desc:
                    actions_taken.append(action_desc)
                if nav:
                    navigation = nav
                if sa:
                    state_action = sa

            # Add assistant response + tool results to conversation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # If stop_reason is end_turn, we're done
            if response.stop_reason == "end_turn":
                break

        # Nudge if no text produced
        if not agent_text.strip() and (display_content or actions_taken):
            try:
                nudge_messages = list(messages)
                nudge_messages.append({
                    "role": "user",
                    "content": "[System: You processed tool calls but did not respond to the user. Please acknowledge what you did and continue the conversation with your next question.]",
                })
                nudge_response = self._anthropic.messages.create(
                    model=MAESTRA_MODEL,
                    max_tokens=MAESTRA_MAX_TOKENS,
                    system=system_prompt,
                    messages=nudge_messages,
                )
                for block in nudge_response.content:
                    if block.type == "text":
                        agent_text = block.text
                        break
            except anthropic.APIError as e:
                logger.warning(f"Nudge failed: {e}")
                agent_text = "I've recorded the information. Let me continue."

        return agent_text, display_content, actions_taken, navigation, state_action

    def _process_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        contour: ContourMap,
        current_section: str,
    ) -> tuple[dict, dict | None, str | None, dict | None, StateAction | None]:
        """
        Process a single tool call.

        Returns: (result, rich_content, action_description, navigation, state_action)
        """
        rich = None
        action = None
        nav = None
        state_action = None

        try:
            if tool_name == "update_contour":
                contour, result = process_update_contour(
                    contour,
                    tool_input.get("dimension_type", ""),
                    tool_input.get("operation", "add"),
                    tool_input.get("node_data", {}),
                    tool_input.get("confidence", 0.8),
                    tool_input.get("provenance", "STAKEHOLDER_CONFIRMED"),
                )
                action = f"Updated {tool_input.get('dimension_type')} ({tool_input.get('operation')})"

            elif tool_name == "show_comparison":
                rich, result = process_show_comparison(
                    tool_input.get("dimension", ""),
                    tool_input.get("systems", []),
                )
                action = f"Displayed comparison: {tool_input.get('dimension')}"

            elif tool_name == "show_hierarchy":
                rich, result = process_show_hierarchy(
                    tool_input.get("title", ""),
                    tool_input.get("root", {}),
                )
                action = f"Displayed hierarchy: {tool_input.get('title')}"

            elif tool_name == "show_table":
                rich, result = process_show_table(
                    tool_input.get("headers", []),
                    tool_input.get("rows", []),
                    tool_input.get("title"),
                )
                action = f"Displayed table: {tool_input.get('title', 'data')}"

            elif tool_name == "park_item":
                contour, result = process_park_item(
                    contour,
                    tool_input.get("dimension", ""),
                    tool_input.get("question", ""),
                    tool_input.get("suggested_person"),
                    current_section,
                )
                action = f"Parked: {tool_input.get('dimension')}"

            elif tool_name == "advance_section":
                state_action, result = process_advance_section(
                    tool_input.get("summary", ""),
                )
                action = f"Advanced section: {tool_input.get('summary', '')[:50]}"

            elif tool_name == "process_file":
                result = {
                    "success": True,
                    "file_id": tool_input.get("file_id"),
                    "note": "File processing not yet implemented in consolidated Maestra.",
                }
                action = "Processed file"

            elif tool_name == "lookup_system_data":
                result = self._lookup_system_data(
                    tool_input.get("query_type", "systems"),
                    tool_input.get("system_name"),
                    tool_input.get("dimension"),
                )
                action = f"Looked up {tool_input.get('query_type')}"

            elif tool_name == "compare_entities":
                result = {
                    "success": True,
                    "dimension": tool_input.get("dimension"),
                    "note": "Cross-entity comparison from contour maps.",
                }
                action = f"Compared entities on {tool_input.get('dimension')}"

            elif tool_name == "navigate_portal":
                nav_content, result = process_navigate_portal(
                    tool_input.get("tab", ""),
                    tool_input.get("entity"),
                    tool_input.get("filters"),
                )
                nav = {"tab": tool_input.get("tab"), "sub_view": tool_input.get("entity")}
                action = f"Navigated to {tool_input.get('tab')}"

            elif tool_name == "query_engine":
                result = process_query_engine(
                    tool_input.get("engine", ""),
                    tool_input.get("query"),
                )
                action = f"Queried {tool_input.get('engine')} engine"

            elif tool_name == "configure_scope":
                result = process_configure_scope(
                    tool_input.get("deliverable_selections"),
                    tool_input.get("confirmed", False),
                )
                action = f"Configured DD scope (confirmed={tool_input.get('confirmed', False)})"

            else:
                result = {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool processing error ({tool_name}): {e}", exc_info=True)
            result = {"error": f"Tool {tool_name} failed: {str(e)}"}

        return result, rich, action, nav, state_action

    # =========================================================================
    # INTERNAL: HELPERS
    # =========================================================================

    def _load_session(
        self,
        engagement_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Load session from persistence. Falls back to first session for engagement."""
        if session_id:
            return self._persistence.get_session(session_id)

        sessions = self._persistence.get_sessions_for_engagement(engagement_id)
        return sessions[0] if sessions else None

    def _build_history(self, session_id: str) -> list[dict[str, Any]]:
        """Build Claude-compatible conversation history from stored messages."""
        messages = self._persistence.get_messages(session_id, limit=50)
        history = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "stakeholder":
                # Annotate rich content that was displayed
                rich = msg.get("rich_content", [])
                if rich:
                    for rc in rich:
                        rc_type = rc.get("type", "")
                        rc_title = rc.get("title", rc.get("dimension", ""))
                        content += f"\n[Displayed {rc_type}: {rc_title}]"

                history.append({"role": "user", "content": content})

            elif role == "agent":
                history.append({"role": "assistant", "content": content})

            # Skip system messages in history

        return history

    def _lookup_system_data(
        self,
        query_type: str,
        system_name: str | None = None,
        dimension: str | None = None,
    ) -> dict[str, Any]:
        """
        Look up discovered system data.
        In demo mode, returns seed data. In live mode, calls AOD/AAM.
        """
        # Demo seed data for Meridian + Cascadia
        if query_type == "systems":
            return {
                "success": True,
                "systems": [
                    {"name": "SAP S/4HANA", "type": "ERP", "entity": "Meridian", "governance": "Governed"},
                    {"name": "NetSuite", "type": "ERP", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Workday", "type": "HCM", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Salesforce", "type": "CRM", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Oracle", "type": "ERP", "entity": "Meridian", "governance": "Shadow"},
                    {"name": "ADP", "type": "Payroll", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Concur", "type": "Expense", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Adaptive", "type": "FP&A", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Tableau", "type": "BI", "entity": "Meridian", "governance": "Governed"},
                    {"name": "ServiceNow", "type": "ITSM", "entity": "Meridian", "governance": "Governed"},
                    {"name": "Jira", "type": "Project", "entity": "Meridian", "governance": "Shadow"},
                    {"name": "SharePoint", "type": "Document", "entity": "Meridian", "governance": "Governed"},
                    {"name": "QuickBooks", "type": "ERP", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "BambooHR", "type": "HCM", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "HubSpot", "type": "CRM", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "Gusto", "type": "Payroll", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "Google Workspace", "type": "Productivity", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "Asana", "type": "Project", "entity": "Cascadia", "governance": "Shadow"},
                    {"name": "Stripe", "type": "Payments", "entity": "Cascadia", "governance": "Governed"},
                    {"name": "Looker", "type": "BI", "entity": "Cascadia", "governance": "Shadow"},
                ],
            }

        elif query_type == "connections":
            return {
                "success": True,
                "connections": [
                    {"source": "SAP", "target": "NetSuite", "type": "API", "frequency": "Daily"},
                    {"source": "Workday", "target": "ADP", "type": "File Transfer", "frequency": "Bi-weekly"},
                    {"source": "Salesforce", "target": "SAP", "type": "API", "frequency": "Real-time"},
                    {"source": "QuickBooks", "target": "Gusto", "type": "Manual", "frequency": "Monthly"},
                    {"source": "HubSpot", "target": "QuickBooks", "type": "API", "frequency": "Daily"},
                ],
            }

        elif query_type == "dimension_data":
            return {
                "success": True,
                "dimension": dimension,
                "data": f"Dimension data for '{dimension}' available via contour map.",
            }

        return {"success": True, "query_type": query_type, "data": "No data available."}

    def _update_engagement_phase(
        self,
        engagement_id: str,
        current_section: SectionId,
        pre_deal_context: PreDealContext | None,
    ) -> None:
        """Update engagement phase based on pre-deal section transitions."""
        phase_map = {
            SectionId.PDC: EngagementPhase.SCOPING,
            SectionId.PDA: EngagementPhase.SCOPING,
            SectionId.PDT: EngagementPhase.SCOPING,
            SectionId.PDS: EngagementPhase.SCOPING,
            SectionId.PDR: EngagementPhase.ANALYSIS_RUNNING,
            SectionId.PDF: EngagementPhase.FINDINGS,
        }
        new_phase = phase_map.get(current_section)
        if not new_phase:
            return

        eng = self._persistence.get_engagement(engagement_id)
        if eng:
            eng["phase"] = new_phase.value
            eng["updated_at"] = datetime.utcnow().isoformat()
            self._persistence.save_engagement(eng)

    def _get_phase_label(
        self,
        engagement_id: str,
        demo_phase: DemoPhase | None,
        session_status: str,
        is_pre_deal: bool,
    ) -> str:
        """Get the phase label for the response."""
        if demo_phase:
            return demo_phase.value
        if is_pre_deal:
            eng = self._persistence.get_engagement(engagement_id)
            if eng:
                return eng.get("phase", session_status)
        return session_status

    def _build_suggestions(
        self,
        current_section: SectionId,
        section_statuses: dict[str, str],
        demo_phase: DemoPhase | None,
    ) -> list[str]:
        """Build contextual suggestions for the frontend."""
        suggestions = []

        if demo_phase:
            phase_suggestions = {
                DemoPhase.PHASE_1_CONTEXT: ["Tell me about the deal", "What systems are involved?"],
                DemoPhase.PHASE_2_DISCOVERY: ["Show me the discovered systems", "Any shadow IT?"],
                DemoPhase.PHASE_3_CONNECTION: ["How do the systems connect?", "Show the topology"],
                DemoPhase.PHASE_4_ONBOARDING: ["Walk me through the org structure", "Let's move on"],
                DemoPhase.PHASE_5_COFA: ["Show me the conflicts", "How do we resolve these?"],
                DemoPhase.PHASE_6_CROSS_SELL: ["Show cross-sell candidates", "What's the EBITDA impact?"],
                DemoPhase.PHASE_7_QOE: ["What's the sustainability score?", "Show revenue quality"],
                DemoPhase.PHASE_8_WHAT_IF: ["Run the aggressive scenario", "What if we cut integration costs?"],
                DemoPhase.PHASE_9_NEXT_STEPS: ["What's the timeline?", "How does ongoing monitoring work?"],
            }
            return phase_suggestions.get(demo_phase, [])

        # Pre-deal suggestions
        pd_suggestions = {
            SectionId.PDC: ["That's correct", "Close date is Q2", "Main concern is system integration"],
            SectionId.PDA: ["That looks right", "We also have a subsidiary in London", "Move on"],
            SectionId.PDT: ["We have limited access to their data", "That matches what we know"],
            SectionId.PDS: ["Run it all", "Skip portfolio rationalization", "Looks good, confirm"],
            SectionId.PDR: [],  # automatic
            SectionId.PDF: ["Show me the cross-sell details", "Walk me through the bridge", "What about vendor overlap?"],
        }

        if current_section in pd_suggestions:
            return pd_suggestions[current_section]

        section_suggestions = {
            SectionId.S1: ["Here's how we're organized", "We have three main divisions"],
            SectionId.S2: ["SAP is our main ERP", "Let me explain our system landscape"],
            SectionId.S3: ["That's correct", "We actually have more cost centers", "Let's move on"],
            SectionId.S4: ["The board sees it the same way", "Management reporting is different"],
            SectionId.S5: ["Our biggest pain is quarterly close", "Revenue by region takes forever"],
        }
        return section_suggestions.get(current_section, ["Continue", "Let's move on"])


def _next_demo_phase(current: DemoPhase) -> DemoPhase:
    """Advance to the next demo phase."""
    order = list(DemoPhase)
    try:
        idx = order.index(current)
        if idx + 1 < len(order):
            return order[idx + 1]
    except ValueError:
        pass
    return DemoPhase.DEMO_COMPLETE


# =============================================================================
# SINGLETON
# =============================================================================

_conversation_service: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service
