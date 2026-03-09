"""
Maestra API routes — native NLQ endpoints.

Replaces the DCL proxy for Maestra endpoints. All Maestra functionality
now lives in NLQ. These endpoints are mounted at /api/reports/maestra/*.

Endpoints:
    POST /api/reports/maestra/engage          — Create engagement
    POST /api/reports/maestra/{id}/message     — Send message
    GET  /api/reports/maestra/{id}/status      — Get status
    GET  /api/reports/maestra/{id}/contour/{e} — Get contour map for entity
    GET  /api/reports/maestra/{id}/messages    — Get message history
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.nlq.maestra.conversation import get_conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports/maestra", tags=["Maestra"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class EngageRequest(BaseModel):
    deal_name: str = "Meridian-Cascadia Integration"
    entities: list[dict[str, str]] | None = None
    demo_mode: bool = True


class MessageRequest(BaseModel):
    message: str
    session_id: str | None = None


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/engage")
async def create_engagement(req: EngageRequest = EngageRequest()):
    """Create a new Maestra engagement with per-entity scoping sessions."""
    try:
        svc = get_conversation_service()
        result = svc.create_engagement(
            deal_name=req.deal_name,
            entities=req.entities,
            demo_mode=req.demo_mode,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Maestra service unavailable: {e}. Ensure ANTHROPIC_API_KEY is set.",
        )
    except Exception as e:
        logger.error(f"Failed to create engagement: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create engagement: {type(e).__name__}: {e}",
        )


@router.post("/{engagement_id}/message")
async def send_message(engagement_id: str, req: MessageRequest):
    """Send a stakeholder message and get Maestra's response."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        svc = get_conversation_service()
        result = svc.send_message(
            engagement_id=engagement_id,
            message=req.message,
            session_id=req.session_id,
        )

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["response"])

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Maestra service unavailable: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to process message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Maestra message processing failed: {type(e).__name__}: {e}",
        )


@router.get("/{engagement_id}/status")
async def get_status(engagement_id: str):
    """Get engagement status with workstream progress."""
    try:
        svc = get_conversation_service()
        result = svc.get_status(engagement_id)

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Maestra service unavailable: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to get status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get engagement status: {type(e).__name__}: {e}",
        )


@router.get("/{engagement_id}/contour/{entity_id}")
async def get_contour_map(engagement_id: str, entity_id: str):
    """Get the contour map for a specific entity in an engagement."""
    try:
        from src.nlq.maestra.persistence import get_maestra_persistence
        persistence = get_maestra_persistence()
        result = persistence.get_contour_map(engagement_id, entity_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No contour map found for entity '{entity_id}' in engagement '{engagement_id}'.",
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contour map: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get contour map: {type(e).__name__}: {e}",
        )


@router.get("/{engagement_id}/messages")
async def get_messages(engagement_id: str, session_id: str | None = None, limit: int = 50):
    """Get message history for an engagement session."""
    try:
        from src.nlq.maestra.persistence import get_maestra_persistence
        persistence = get_maestra_persistence()

        if not session_id:
            sessions = persistence.get_sessions_for_engagement(engagement_id)
            if not sessions:
                raise HTTPException(
                    status_code=404,
                    detail=f"No sessions found for engagement '{engagement_id}'.",
                )
            session_id = sessions[0]["session_id"]

        messages = persistence.get_messages(session_id, limit=limit)
        return {"session_id": session_id, "messages": messages}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get messages: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get messages: {type(e).__name__}: {e}",
        )
