"""
Maestra action dispatch — executes read actions, creates plans for write actions.

Read actions are executed immediately by making HTTP requests to module endpoints.
Write actions create a plan document that requires human approval before execution.

Session 4 of the Maestra build.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from src.nlq.maestra.engagement import get_engagement_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module base URLs from environment
# ---------------------------------------------------------------------------

def _module_urls() -> dict[str, str]:
    """Resolve module URLs from environment. Called at use-time, not import-time."""
    return {
        "aod": os.environ.get("AOD_URL", "http://localhost:8001"),
        "aam": os.environ.get("AAM_URL", "http://localhost:8002"),
        "farm": os.environ.get("FARM_URL", "http://localhost:8003"),
        "dcl": os.environ.get("DCL_API_URL", "http://localhost:8004"),
        "nlq": os.environ.get("NLQ_URL", "http://localhost:8005"),
    }


# ---------------------------------------------------------------------------
# Action catalog
# ---------------------------------------------------------------------------

def _build_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    """Build the action catalog with resolved URLs."""
    urls = _module_urls()
    return {
        "read": {
            "aod:status": {"method": "GET", "url": f"{urls['aod']}/maestra/status"},
            "aam:status": {"method": "GET", "url": f"{urls['aam']}/maestra/status"},
            "farm:status": {"method": "GET", "url": f"{urls['farm']}/maestra/status"},
            "dcl:status": {"method": "GET", "url": f"{urls['dcl']}/maestra/status"},
            "nlq:report:overlap": {
                "method": "POST",
                "url": f"{urls['nlq']}/maestra/report",
                "body": {"type": "overlap"},
            },
            "nlq:report:conflicts": {
                "method": "POST",
                "url": f"{urls['nlq']}/maestra/report",
                "body": {"type": "conflicts"},
            },
            "nlq:report:cofa": {
                "method": "POST",
                "url": f"{urls['nlq']}/maestra/report",
                "body": {"type": "cofa"},
            },
        },
        "write": {
            "aod:run-discovery": {
                "method": "POST",
                "url": f"{urls['aod']}/maestra/run-discovery",
            },
            "aam:retry-manifest": {
                "method": "POST",
                "url": f"{urls['aam']}/maestra/retry-manifest",
            },
        },
    }


def _resolve_catalog_key(action: dict[str, Any]) -> str:
    """Derive catalog key from an action block.

    The action block from the LLM looks like:
        {"type": "read", "module": "aod", "endpoint": "/maestra/status", ...}

    We map this to a catalog key like "aod:status" by taking the last segment
    of the endpoint path.
    """
    module = action.get("module", "")
    endpoint = action.get("endpoint", "")

    # Strip leading /module/maestra/ prefix to get the action name
    # e.g. "/aod/maestra/status" → "status"
    # e.g. "/nlq/maestra/report" → "report"
    parts = [p for p in endpoint.strip("/").split("/") if p]

    if not parts:
        return f"{module}:unknown"

    # Take the last meaningful part(s)
    # For reports: "/maestra/report?type=overlap" → look for body/params
    action_name = parts[-1].split("?")[0]

    # Special case: report endpoints with type param
    params = action.get("params", {})
    report_type = params.get("type")
    if action_name == "report" and report_type:
        return f"{module}:report:{report_type}"

    return f"{module}:{action_name}"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_action(
    action_block: dict[str, Any],
    customer_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Dispatch an action from Maestra's LLM response.

    For read actions: execute the HTTP request immediately and return the result.
    For write actions: create a plan and return the plan info.

    Args:
        action_block: The parsed action from the LLM response.
            {"action": {"type": "read"|"write", "module": str, "endpoint": str, ...}}
            or {"type": "read"|"write", "module": str, ...}
        customer_id: The customer this action is for.
        session_id: The current session ID.

    Returns:
        For read actions: {"dispatched": True, "result": <data>, "catalog_key": str}
        For write actions: {"planned": True, "plan_id": str, "message": str}
        For errors: {"error": True, "message": str}
    """
    # Normalize: action may be wrapped in {"action": {...}} or be flat
    action = action_block.get("action", action_block)

    action_type = action.get("type", "").lower()
    module = action.get("module", "")
    rationale = action.get("rationale", "")

    if action_type not in ("read", "write"):
        return {
            "error": True,
            "message": f"Unknown action type '{action_type}'. Expected 'read' or 'write'.",
        }

    catalog = _build_catalog()
    catalog_key = _resolve_catalog_key(action)
    type_catalog = catalog.get(action_type, {})
    entry = type_catalog.get(catalog_key)

    if entry is None:
        logger.warning(
            f"Unknown action: type={action_type}, catalog_key={catalog_key}, "
            f"module={module}, endpoint={action.get('endpoint')}"
        )
        return {
            "error": True,
            "message": (
                f"Unknown action '{catalog_key}' for type '{action_type}'. "
                f"Available {action_type} actions: {list(type_catalog.keys())}"
            ),
        }

    svc = get_engagement_service()

    # ------------------------------------------------------------------
    # READ actions — execute immediately
    # ------------------------------------------------------------------
    if action_type == "read":
        method = entry["method"]
        url = entry["url"]
        body = entry.get("body")
        params = action.get("params", {})

        # Merge any params from the action into the body
        if body and params:
            body = {**body, **params}
        elif params and not body:
            body = params

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if method == "GET":
                    r = await client.get(url, params=params if not body else None)
                else:
                    r = await client.post(url, json=body)

            if r.status_code >= 400:
                error_msg = (
                    f"{module.upper()} returned HTTP {r.status_code} "
                    f"at {url}: {r.text[:200]}"
                )
                logger.warning(f"Read action failed: {error_msg}")

                # Log failure to session memory
                try:
                    svc.add_session_memory(customer_id, session_id, {
                        "interaction_type": "action_request",
                        "user_message_summary": f"Read action {catalog_key} failed: HTTP {r.status_code}",
                        "maestra_action": f"dispatch_failed:{catalog_key}",
                        "module_context": [module],
                    })
                except Exception:
                    pass

                return {"error": True, "message": error_msg}

            result_data = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

            # Log success to session memory
            try:
                svc.add_session_memory(customer_id, session_id, {
                    "interaction_type": "action_request",
                    "user_message_summary": f"Executed read action: {catalog_key}",
                    "maestra_action": f"dispatch_read:{catalog_key}",
                    "module_context": [module],
                })
            except Exception as e:
                logger.warning(f"Failed to log dispatch to session memory: {e}")

            return {
                "dispatched": True,
                "result": result_data,
                "catalog_key": catalog_key,
            }

        except httpx.ConnectError:
            error_msg = (
                f"{module.upper()} is currently unreachable at {url}. "
                f"I'll note this for the team."
            )
            logger.warning(f"Module unreachable during dispatch: {error_msg}")

            try:
                svc.add_session_memory(customer_id, session_id, {
                    "interaction_type": "escalation",
                    "user_message_summary": f"{module.upper()} unreachable during {catalog_key}",
                    "maestra_action": f"dispatch_unreachable:{catalog_key}",
                    "module_context": [module],
                })
            except Exception:
                pass

            return {"error": True, "message": error_msg}

        except Exception as e:
            error_msg = (
                f"Failed to dispatch {catalog_key} to {module.upper()}: "
                f"{type(e).__name__}: {e}"
            )
            logger.error(error_msg)
            return {"error": True, "message": error_msg}

    # ------------------------------------------------------------------
    # WRITE actions — create plan, do NOT execute
    # ------------------------------------------------------------------
    plan_data = {
        "customer_id": customer_id,
        "plan_type": "action_dispatch",
        "title": rationale or f"Execute {catalog_key}",
        "rationale": rationale or f"Maestra determined that {catalog_key} should be executed",
        "affected_modules": [module],
        "plan_body": {
            "catalog_key": catalog_key,
            "params": action.get("params", {}),
            "endpoint_config": entry,
        },
    }

    try:
        plan = svc.create_plan(plan_data)
    except Exception as e:
        error_msg = f"Failed to create plan for {catalog_key}: {type(e).__name__}: {e}"
        logger.error(error_msg)
        return {"error": True, "message": error_msg}

    # Log plan creation to session memory
    try:
        svc.add_session_memory(customer_id, session_id, {
            "interaction_type": "action_request",
            "user_message_summary": f"Created plan for write action: {catalog_key}",
            "maestra_action": f"plan_created:{catalog_key}",
            "module_context": [module],
        })
    except Exception as e:
        logger.warning(f"Failed to log plan creation to session memory: {e}")

    return {
        "planned": True,
        "plan_id": plan["id"],
        "message": (
            "I've created a plan for this. It needs approval before I can execute."
        ),
    }


# ---------------------------------------------------------------------------
# Execute an approved plan
# ---------------------------------------------------------------------------

async def execute_plan(plan_id: str) -> dict[str, Any]:
    """Execute a previously approved plan.

    Only plans with status='approved' can be executed.

    Returns:
        {"executed": True, "result": <data>, "plan_id": str}
        or {"error": True, "message": str}
    """
    svc = get_engagement_service()

    # Load plan from database — get it from pending plans or by direct query
    # Since we don't have a get_plan_by_id, we'll use the update flow
    # First, check the plan exists and is approved by attempting the update
    # Actually, we need to read the plan first. Let me use the Supabase client directly.
    engagement_svc = get_engagement_service()
    try:
        result = (
            engagement_svc._table("plans")
            .select("*")
            .eq("id", plan_id)
            .execute()
        )
        if not result.data:
            return {"error": True, "message": f"Plan {plan_id} not found"}
        plan = result.data[0]
    except Exception as e:
        return {"error": True, "message": f"Failed to load plan {plan_id}: {e}"}

    # Validate status — only approved plans can be executed.
    # Executed/failed plans cannot be re-executed.
    if plan["status"] in ("executed", "failed"):
        return {
            "error": True,
            "message": (
                f"Cannot execute plan {plan_id}: status is '{plan['status']}'. "
                f"This plan has already been processed."
            ),
        }
    if plan["status"] != "approved":
        return {
            "error": True,
            "message": (
                f"Cannot execute plan {plan_id}: status is '{plan['status']}'. "
                f"Only approved plans can be executed."
            ),
        }

    # Extract endpoint config from plan_body
    plan_body = plan.get("plan_body", {})
    if isinstance(plan_body, str):
        plan_body = json.loads(plan_body)

    endpoint_config = plan_body.get("endpoint_config", {})
    params = plan_body.get("params", {})
    method = endpoint_config.get("method", "POST")
    url = endpoint_config.get("url", "")

    if not url:
        svc.update_plan_status(plan_id, "failed", result_summary="No URL in plan_body")
        return {"error": True, "message": f"Plan {plan_id} has no endpoint URL"}

    # Execute the request
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "GET":
                r = await client.get(url, params=params)
            else:
                body = endpoint_config.get("body", {})
                if params:
                    body = {**body, **params}
                r = await client.post(url, json=body if body else params)

        if r.status_code >= 400:
            summary = f"HTTP {r.status_code}: {r.text[:200]}"
            svc.update_plan_status(plan_id, "failed", result_summary=summary)
            return {"error": True, "message": summary, "plan_id": plan_id}

        result_data = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        summary = f"Executed successfully. Status: {r.status_code}"

        svc.update_plan_status(
            plan_id, "executed",
            result_summary=summary,
        )

        return {
            "executed": True,
            "result": result_data,
            "plan_id": plan_id,
        }

    except httpx.ConnectError:
        summary = f"Module unreachable at {url}"
        svc.update_plan_status(plan_id, "failed", result_summary=summary)
        return {"error": True, "message": summary, "plan_id": plan_id}

    except Exception as e:
        summary = f"{type(e).__name__}: {e}"
        svc.update_plan_status(plan_id, "failed", result_summary=summary)
        return {"error": True, "message": summary, "plan_id": plan_id}
