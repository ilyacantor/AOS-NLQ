"""
Maestra Engagement API routes — sessions 2-5.

Endpoints:
    POST /maestra/chat                                  — live Maestra chat (session 5)
    GET  /maestra/stats/{customer_id}                   — interaction stats (session 5)
    POST /maestra/context                               — context assembly (session 3)
    POST /maestra/dispatch                              — action dispatch (session 4)
    GET  /maestra/engagement/{customer_id}              — get engagement + playbook
    PUT  /maestra/engagement/{customer_id}              — update engagement fields
    GET  /maestra/memory/{customer_id}                  — recent session memory
    POST /maestra/memory/{customer_id}                  — add session memory entry
    GET  /maestra/plans/{customer_id}                   — pending plans
    POST /maestra/plans                                 — create plan
    PUT  /maestra/plans/{plan_id}/status                — approve/reject plan
    POST /maestra/plans/{plan_id}/approve               — approve + execute plan
    POST /maestra/plans/{plan_id}/reject                — reject plan
    POST /maestra/interactions                          — log interaction
    GET  /maestra/module-state/{module}/{customer_id}   — get module state cache
    PUT  /maestra/module-state/{module}/{customer_id}   — set module state cache
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.nlq.maestra.engagement import get_engagement_service
from src.nlq.maestra.context import assemble_context
from src.nlq.maestra.dispatch import dispatch_action, execute_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maestra", tags=["Maestra Engagement"])


# =========================================================================
# REQUEST / RESPONSE MODELS
# =========================================================================


class CreateEngagementRequest(BaseModel):
    customer_id: str
    customer_name: str
    scenario_type: str = Field(
        ..., description="One of: single, multi, convergence, portfolio"
    )
    deal_phase: str = Field(
        default="discovery",
        description="One of: discovery, connection, semantic_mapping, analysis, integration_monitoring",
    )
    acquirer_entity: Optional[str] = None
    target_entity: Optional[str] = None


class UpdateEngagementRequest(BaseModel):
    deal_phase: Optional[str] = None
    onboarding_complete: Optional[bool] = None
    last_interaction_at: Optional[str] = None
    acquirer_entity: Optional[str] = None
    target_entity: Optional[str] = None


class SessionMemoryEntry(BaseModel):
    interaction_type: str = Field(
        ...,
        description="One of: status_check, action_request, analysis, onboarding, escalation, general",
    )
    user_message_summary: str
    maestra_action: Optional[str] = None
    module_context: Optional[list[str]] = None


class CreatePlanRequest(BaseModel):
    customer_id: str
    plan_type: str = Field(
        ..., description="One of: action_dispatch, code_change, configuration"
    )
    title: str
    rationale: str
    affected_modules: list[str]
    plan_body: dict[str, Any]
    cc_prompt: Optional[str] = None


class UpdatePlanStatusRequest(BaseModel):
    status: str = Field(
        ..., description="One of: pending, approved, rejected, executed, failed"
    )
    approved_by: Optional[str] = None
    result_summary: Optional[str] = None


class LogInteractionRequest(BaseModel):
    customer_id: str
    session_id: Optional[str] = None
    input_hash: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    interaction_type: Optional[str] = None
    action_dispatched: Optional[str] = None


class ContextRequest(BaseModel):
    customer_id: str
    message: str
    session_id: Optional[str] = None


class ChatRequest(BaseModel):
    customer_id: str
    message: str
    session_id: Optional[str] = None


class ModuleStateRequest(BaseModel):
    state_json: dict[str, Any]


# =========================================================================
# ENDPOINTS
# =========================================================================


# ----- Session 5: Chat + Stats -----

@router.post("/chat")
async def chat(req: ChatRequest):
    """Live Maestra chat endpoint — the primary customer-facing API.

    Validates customer exists, assembles context, dispatches actions,
    returns formatted response. No separate demo mode — the seeded
    Meridian/Cascadia tenant IS the demo.
    """
    import time as _time

    t0 = _time.time()
    print(f"MAESTRA: received message customer_id={req.customer_id} message={req.message[:80]!r}", flush=True)

    svc = get_engagement_service()
    session_id = req.session_id or str(uuid.uuid4())

    # 1. Validate customer_id exists
    try:
        engagement = svc.get_engagement(req.customer_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {req.customer_id} not found in maestra.customer_engagements",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    print(f"MAESTRA: engagement loaded +{int((_time.time() - t0) * 1000)}ms customer={engagement.get('customer_name')} phase={engagement.get('deal_phase')}", flush=True)

    # 2. First interaction check — refresh module state if no history
    try:
        recent = svc.get_recent_memory(req.customer_id, limit=1)
        if not recent:
            from src.nlq.maestra.context import _fetch_module_status, _fetch_module_health
            succeeded, failed = [], []
            for module in ("aod", "aam", "farm", "dcl"):
                mt = _time.time()
                fresh = _fetch_module_status(module)
                if fresh is None:
                    fresh = _fetch_module_health(module)  # fallback: at least get health
                elapsed = int((_time.time() - mt) * 1000)
                if fresh is not None:
                    svc.set_module_state(module, req.customer_id, fresh)
                    succeeded.append(f"{module}({elapsed}ms)")
                else:
                    failed.append(f"{module}({elapsed}ms)")
            print(f"MAESTRA: module state refreshed +{int((_time.time() - t0) * 1000)}ms succeeded=[{', '.join(succeeded) or 'none'}] failed=[{', '.join(failed) or 'none'}]", flush=True)
        else:
            print(f"MAESTRA: module state refresh skipped (not first interaction) +{int((_time.time() - t0) * 1000)}ms", flush=True)
    except Exception as e:
        print(f"MAESTRA: first-interaction module refresh failed +{int((_time.time() - t0) * 1000)}ms: {e}", flush=True)

    # 3. Call assembleContext (includes LLM call + dispatch from sessions 3-4)
    try:
        result = await assemble_context(req.customer_id, req.message, session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 4. Format response per session 5 spec
    response: dict[str, Any] = {
        "text": result["text"],
        "session_id": session_id,
    }

    dispatch = result.get("dispatch")
    if dispatch:
        if dispatch.get("dispatched"):
            response["action_result"] = dispatch.get("result")
        elif dispatch.get("planned"):
            response["plan_created"] = {
                "plan_id": dispatch["plan_id"],
                "title": dispatch.get("message", ""),
                "status": "pending",
            }

    print(f"MAESTRA: response sent +{int((_time.time() - t0) * 1000)}ms text_len={len(response['text'])} has_dispatch={bool(dispatch)}", flush=True)
    return response


@router.get("/stats/{customer_id}")
async def get_stats(customer_id: str):
    """Interaction stats for Maestra health monitoring."""
    svc = get_engagement_service()

    # Verify customer exists
    try:
        engagement = svc.get_engagement(customer_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_id} not found",
        )

    # Query interaction_log for aggregate stats
    try:
        log_result = (
            svc._table("interaction_log")
            .select("input_tokens, output_tokens, latency_ms, created_at")
            .eq("customer_id", customer_id)
            .execute()
        )
        logs = log_result.data or []
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query interaction_log for customer {customer_id}: {e}",
        )

    # Compute aggregates
    total_interactions = len(logs)
    total_input_tokens = sum(l.get("input_tokens", 0) for l in logs)
    total_output_tokens = sum(l.get("output_tokens", 0) for l in logs)
    total_latency = sum(l.get("latency_ms", 0) for l in logs)
    avg_latency_ms = int(total_latency / total_interactions) if total_interactions > 0 else 0

    # Count today's interactions
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    interactions_today = sum(
        1 for l in logs
        if l.get("created_at", "").startswith(today)
    )

    # Estimated cost (Claude Sonnet pricing: $3/M input, $15/M output)
    estimated_cost_usd = round(
        (total_input_tokens * 3.0 / 1_000_000)
        + (total_output_tokens * 15.0 / 1_000_000),
        4,
    )

    # Query plans
    try:
        plans_result = (
            svc._table("plans")
            .select("status")
            .eq("customer_id", customer_id)
            .execute()
        )
        plans = plans_result.data or []
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query plans for customer {customer_id}: {e}",
        )

    plans_pending = sum(1 for p in plans if p["status"] == "pending")
    plans_executed = sum(1 for p in plans if p["status"] == "executed")

    return {
        "total_interactions": total_interactions,
        "interactions_today": interactions_today,
        "avg_latency_ms": avg_latency_ms,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "plans_pending": plans_pending,
        "plans_executed": plans_executed,
        "last_interaction_at": engagement.get("last_interaction_at"),
    }


# ----- Session 3: Context Assembly -----

@router.post("/context")
async def context_assembly(req: ContextRequest):
    """Assemble context, call Claude, return Maestra's response."""
    session_id = req.session_id or str(uuid.uuid4())
    try:
        result = await assemble_context(req.customer_id, req.message, session_id)
        return result
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/engagement/{customer_id}")
async def get_engagement(customer_id: str):
    """Get engagement state for a customer, joined with playbook."""
    svc = get_engagement_service()
    try:
        return svc.get_engagement(customer_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/engagement", status_code=201)
async def create_engagement(req: CreateEngagementRequest):
    """Create a new customer engagement."""
    svc = get_engagement_service()
    try:
        return svc.create_engagement(req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/engagement/{customer_id}")
async def update_engagement(customer_id: str, req: UpdateEngagementRequest):
    """Update engagement state fields."""
    svc = get_engagement_service()
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return svc.update_engagement(customer_id, updates)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/memory/{customer_id}")
async def get_recent_memory(customer_id: str, limit: int = 10):
    """Get recent session memory entries, newest first."""
    svc = get_engagement_service()
    try:
        return svc.get_recent_memory(customer_id, limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/memory/{customer_id}", status_code=201)
async def add_session_memory(
    customer_id: str, session_id: str, entry: SessionMemoryEntry
):
    """Add a session memory entry.

    session_id is passed as a query parameter.
    """
    svc = get_engagement_service()
    try:
        return svc.add_session_memory(
            customer_id, session_id, entry.model_dump(exclude_none=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/plans/{customer_id}")
async def get_pending_plans(customer_id: str):
    """Get all pending plans for a customer."""
    svc = get_engagement_service()
    try:
        return svc.get_pending_plans(customer_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/plans", status_code=201)
async def create_plan(req: CreatePlanRequest):
    """Create a new plan with status='pending'."""
    svc = get_engagement_service()
    try:
        return svc.create_plan(req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/plans/{plan_id}/status")
async def update_plan_status(plan_id: str, req: UpdatePlanStatusRequest):
    """Update plan status (approve/reject/execute/fail)."""
    svc = get_engagement_service()
    try:
        return svc.update_plan_status(
            plan_id,
            req.status,
            approved_by=req.approved_by,
            result_summary=req.result_summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


class DispatchActionRequest(BaseModel):
    action: dict[str, Any]
    customer_id: str
    session_id: Optional[str] = None


class ApprovePlanRequest(BaseModel):
    approved_by: str = "operator"


@router.post("/dispatch")
async def dispatch_action_endpoint(req: DispatchActionRequest):
    """Dispatch an action (read: execute, write: create plan)."""
    session_id = req.session_id or str(uuid.uuid4())
    result = await dispatch_action(req.action, req.customer_id, session_id)
    if result.get("error"):
        # Return 200 with error payload (not HTTP error — dispatch errors are expected)
        return result
    return result


@router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: str, req: ApprovePlanRequest):
    """Approve a plan and immediately execute it.

    Only pending plans can be approved. Already executed/failed/rejected
    plans are refused.
    """
    svc = get_engagement_service()

    # Check current plan status before approving
    try:
        plan_row = (
            svc._table("plans")
            .select("status")
            .eq("id", plan_id)
            .execute()
        )
        if not plan_row.data:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
        current_status = plan_row.data[0]["status"]
        if current_status != "pending":
            return {
                "error": True,
                "message": (
                    f"Cannot approve plan {plan_id}: status is '{current_status}'. "
                    f"Only pending plans can be approved."
                ),
            }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        svc.update_plan_status(plan_id, "approved", approved_by=req.approved_by)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = await execute_plan(plan_id)
    return result


@router.post("/plans/{plan_id}/reject")
async def reject_plan(plan_id: str):
    """Reject a plan."""
    svc = get_engagement_service()
    try:
        return svc.update_plan_status(plan_id, "rejected")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/interactions", status_code=201)
async def log_interaction(req: LogInteractionRequest):
    """Log an LLM interaction for cost/quality monitoring."""
    svc = get_engagement_service()
    try:
        return svc.log_interaction(req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/module-state/{module}/{customer_id}")
async def get_module_state(module: str, customer_id: str):
    """Get cached module state."""
    svc = get_engagement_service()
    try:
        state = svc.get_module_state(module, customer_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail=f"No module state cached for module={module}, customer_id={customer_id}",
            )
        return state
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/module-state/{module}/{customer_id}")
async def set_module_state(
    module: str, customer_id: str, req: ModuleStateRequest
):
    """Set/update cached module state."""
    svc = get_engagement_service()
    try:
        return svc.set_module_state(module, customer_id, req.state_json)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
