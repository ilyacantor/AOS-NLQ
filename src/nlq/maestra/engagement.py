"""
Maestra Engagement State CRUD — Supabase persistence for customer engagements.

Tables (in maestra schema):
    customer_engagements  — one row per customer
    session_memory        — structured interaction records
    plans                 — plan mode for write actions
    module_state_cache    — cached module status
    interaction_log       — LLM call cost/quality monitoring
    customer_playbooks    — customer-specific context

All queries use the maestra schema explicitly via the Supabase client's
.schema("maestra") method. This requires the maestra schema to be exposed
in Supabase API settings (Settings > API > Exposed schemas > add "maestra").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.nlq.db.supabase_persistence import get_persistence_service

logger = logging.getLogger(__name__)

SCHEMA = "maestra"


class EngagementService:
    """
    CRUD operations for Maestra engagement state.

    Uses the existing SupabasePersistenceService singleton for the underlying
    Supabase client, then scopes all queries to the maestra schema.
    """

    def __init__(self):
        self._svc = get_persistence_service()

    @property
    def is_available(self) -> bool:
        return self._svc is not None and self._svc.is_available

    def _table(self, name: str):
        """Return a schema-scoped table query builder.

        Raises RuntimeError if the Supabase client is not available,
        so callers never silently degrade to empty results.
        """
        if not self.is_available:
            raise RuntimeError(
                "EngagementService: Supabase client is not available. "
                "Check SUPABASE_API_URL and SUPABASE_KEY environment variables."
            )
        return self._svc._client.schema(SCHEMA).table(name)

    # =========================================================================
    # CUSTOMER ENGAGEMENTS
    # =========================================================================

    def get_engagement(self, customer_id: str) -> dict[str, Any]:
        """Get engagement state for a customer, joined with playbook.

        Returns the customer_engagements row merged with customer_playbooks
        fields (systems, vocabulary, priorities, notes).

        Raises:
            RuntimeError: If Supabase is unavailable.
            LookupError: If no engagement exists for the given customer_id.
        """
        result = (
            self._table("customer_engagements")
            .select("*")
            .eq("customer_id", customer_id)
            .execute()
        )
        if not result.data:
            raise LookupError(
                f"No engagement found for customer_id={customer_id}"
            )
        engagement = result.data[0]

        # Join playbook data
        playbook_result = (
            self._table("customer_playbooks")
            .select("systems, vocabulary, priorities, notes")
            .eq("customer_id", customer_id)
            .execute()
        )
        if playbook_result.data:
            engagement.update(playbook_result.data[0])

        return engagement

    def create_engagement(self, engagement: dict[str, Any]) -> dict[str, Any]:
        """Create a new customer engagement.

        Required fields: customer_id, customer_name, scenario_type.
        Optional: deal_phase (defaults to 'discovery'), acquirer_entity, target_entity.

        Raises:
            RuntimeError: If Supabase is unavailable.
            ValueError: If required fields are missing or invalid.
        """
        required = ["customer_id", "customer_name", "scenario_type"]
        missing = [f for f in required if f not in engagement]
        if missing:
            raise ValueError(
                f"Missing required fields for engagement: {missing}"
            )

        result = (
            self._table("customer_engagements")
            .insert(engagement)
            .execute()
        )
        if not result.data:
            raise RuntimeError(
                f"Failed to create engagement for customer_id={engagement['customer_id']} — "
                "insert returned no data"
            )
        return result.data[0]

    def update_engagement(
        self, customer_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update engagement state for a customer.

        Updatable fields: deal_phase, onboarding_complete, last_interaction_at,
        acquirer_entity, target_entity.

        Raises:
            RuntimeError: If Supabase is unavailable.
            LookupError: If no engagement exists for the given customer_id.
        """
        result = (
            self._table("customer_engagements")
            .update(updates)
            .eq("customer_id", customer_id)
            .execute()
        )
        if not result.data:
            raise LookupError(
                f"No engagement found to update for customer_id={customer_id}"
            )
        return result.data[0]

    # =========================================================================
    # SESSION MEMORY
    # =========================================================================

    def add_session_memory(
        self,
        customer_id: str,
        session_id: str,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a session memory entry.

        entry must contain: interaction_type, user_message_summary.
        Optional: maestra_action, module_context.

        Raises:
            RuntimeError: If Supabase is unavailable.
            ValueError: If required fields are missing.
        """
        required = ["interaction_type", "user_message_summary"]
        missing = [f for f in required if f not in entry]
        if missing:
            raise ValueError(
                f"Missing required fields for session memory: {missing}"
            )

        row = {
            "customer_id": customer_id,
            "session_id": session_id,
            **entry,
        }
        result = self._table("session_memory").insert(row).execute()
        if not result.data:
            raise RuntimeError(
                f"Failed to add session memory for customer_id={customer_id}, "
                f"session_id={session_id} — insert returned no data"
            )
        return result.data[0]

    def get_recent_memory(
        self, customer_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent session memory entries for a customer, newest first.

        Raises:
            RuntimeError: If Supabase is unavailable.
        """
        result = (
            self._table("session_memory")
            .select("*")
            .eq("customer_id", customer_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    # =========================================================================
    # MODULE STATE CACHE
    # =========================================================================

    def get_module_state(
        self, module: str, customer_id: str
    ) -> Optional[dict[str, Any]]:
        """Get cached module state.

        Returns the state_json dict, or None if no cache entry exists.

        Raises:
            RuntimeError: If Supabase is unavailable.
        """
        result = (
            self._table("module_state_cache")
            .select("*")
            .eq("module", module)
            .eq("customer_id", customer_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def set_module_state(
        self, module: str, customer_id: str, state_json: dict[str, Any]
    ) -> dict[str, Any]:
        """Set/update cached module state.

        Uses upsert on (module, customer_id) unique constraint.

        Raises:
            RuntimeError: If Supabase is unavailable.
        """
        result = (
            self._table("module_state_cache")
            .upsert(
                {
                    "module": module,
                    "customer_id": customer_id,
                    "state_json": state_json,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="module,customer_id",
            )
            .execute()
        )
        if not result.data:
            raise RuntimeError(
                f"Failed to set module state for module={module}, "
                f"customer_id={customer_id} — upsert returned no data"
            )
        return result.data[0]

    # =========================================================================
    # PLANS
    # =========================================================================

    def create_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Create a new plan with status='pending'.

        Required fields: customer_id, plan_type, title, rationale,
        affected_modules, plan_body.
        Optional: cc_prompt.

        Raises:
            RuntimeError: If Supabase is unavailable.
            ValueError: If required fields are missing.
        """
        required = [
            "customer_id", "plan_type", "title", "rationale",
            "affected_modules", "plan_body",
        ]
        missing = [f for f in required if f not in plan]
        if missing:
            raise ValueError(f"Missing required fields for plan: {missing}")

        plan.setdefault("status", "pending")
        result = self._table("plans").insert(plan).execute()
        if not result.data:
            raise RuntimeError(
                f"Failed to create plan for customer_id={plan['customer_id']} — "
                "insert returned no data"
            )
        return result.data[0]

    def get_pending_plans(self, customer_id: str) -> list[dict[str, Any]]:
        """Get all pending plans for a customer.

        Raises:
            RuntimeError: If Supabase is unavailable.
        """
        result = (
            self._table("plans")
            .select("*")
            .eq("customer_id", customer_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def update_plan_status(
        self,
        plan_id: str,
        status: str,
        approved_by: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update plan status (approve/reject/execute/fail).

        Raises:
            RuntimeError: If Supabase is unavailable.
            LookupError: If no plan exists with the given plan_id.
            ValueError: If status is not a valid value.
        """
        valid_statuses = {"pending", "approved", "rejected", "executed", "failed"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid plan status '{status}'. Must be one of: {valid_statuses}"
            )

        updates: dict[str, Any] = {"status": status}
        if approved_by is not None:
            updates["approved_by"] = approved_by
        if status == "approved":
            updates["approved_at"] = datetime.now(timezone.utc).isoformat()
        if status == "executed":
            updates["executed_at"] = datetime.now(timezone.utc).isoformat()
        if result_summary is not None:
            updates["result_summary"] = result_summary

        result = (
            self._table("plans")
            .update(updates)
            .eq("id", plan_id)
            .execute()
        )
        if not result.data:
            raise LookupError(
                f"No plan found to update for plan_id={plan_id}"
            )
        return result.data[0]

    # =========================================================================
    # INTERACTION LOG
    # =========================================================================

    def log_interaction(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Log an LLM interaction for cost/quality monitoring.

        Required fields: customer_id, input_hash, model_used,
        input_tokens, output_tokens, latency_ms.
        Optional: session_id, interaction_type, action_dispatched.

        Raises:
            RuntimeError: If Supabase is unavailable.
            ValueError: If required fields are missing.
        """
        required = [
            "customer_id", "input_hash", "model_used",
            "input_tokens", "output_tokens", "latency_ms",
        ]
        missing = [f for f in required if f not in entry]
        if missing:
            raise ValueError(
                f"Missing required fields for interaction log: {missing}"
            )

        result = self._table("interaction_log").insert(entry).execute()
        if not result.data:
            raise RuntimeError(
                f"Failed to log interaction for customer_id={entry['customer_id']} — "
                "insert returned no data"
            )
        return result.data[0]


# Singleton
_engagement_service: Optional[EngagementService] = None


def get_engagement_service() -> EngagementService:
    """Get the singleton EngagementService instance."""
    global _engagement_service
    if _engagement_service is None:
        _engagement_service = EngagementService()
    return _engagement_service
