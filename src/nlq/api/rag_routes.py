"""
RAG Cache API Routes for AOS-NLQ

Provides endpoints for:
- Query cache statistics
- RAG learning log access
- LLM call counter
- Cache seeding and management
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from ..services.llm_call_counter import get_call_counter
from ..services.rag_learning_log import get_learning_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG Cache"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CacheStatsResponse(BaseModel):
    """Response model for cache statistics."""
    available: bool
    total_vectors: int = 0
    namespace: str = ""
    namespace_vectors: int = 0
    dimension: int = 0
    error: Optional[str] = None


class SessionStatsResponse(BaseModel):
    """Response model for session statistics."""
    session_id: str
    llm_calls: int
    cached_queries: int
    learned_queries: int
    first_call_at: Optional[str] = None
    last_call_at: Optional[str] = None


class GlobalStatsResponse(BaseModel):
    """Response model for global statistics."""
    total_llm_calls: int
    total_cached_queries: int
    total_learned_queries: int
    active_sessions: int
    server_start_time: str
    uptime_seconds: float


class LearningLogEntry(BaseModel):
    """Model for a learning log entry."""
    id: str
    description: str
    success: bool
    source: str
    learned: bool
    timestamp: str
    persona: str


class LearningLogResponse(BaseModel):
    """Response model for learning log."""
    entries: List[LearningLogEntry]
    total: int
    stats: dict


class LearningStatsResponse(BaseModel):
    """Response model for learning statistics."""
    total_queries: int
    successful_queries: int
    queries_learned: int
    from_cache: int
    from_llm: int
    cache_hit_rate: float
    learning_rate: float
    supabase_connected: bool


# =============================================================================
# LLM CALL COUNTER ENDPOINTS
# =============================================================================

@router.get("/session/stats", response_model=SessionStatsResponse)
async def get_session_stats(
    session_id: str = Query(default="default", description="Browser session ID")
):
    """
    Get LLM call statistics for a browser session.

    The session_id should be generated on the frontend and passed with each request.
    It resets when the browser is closed.
    """
    counter = get_call_counter()
    stats = counter.get_session_stats(session_id)
    return SessionStatsResponse(**stats)


@router.get("/global/stats", response_model=GlobalStatsResponse)
async def get_global_stats():
    """
    Get global LLM call statistics across all sessions.

    Useful for monitoring overall system usage.
    """
    counter = get_call_counter()
    stats = counter.get_global_stats()
    return GlobalStatsResponse(**stats)


@router.post("/session/reset")
async def reset_session(
    session_id: str = Query(default="default", description="Browser session ID")
):
    """
    Reset the LLM call counter for a session.

    Called when user wants to manually reset or when session expires.
    """
    counter = get_call_counter()
    success = counter.reset_session(session_id)
    return {"success": success, "session_id": session_id}


# =============================================================================
# LEARNING LOG ENDPOINTS
# =============================================================================

@router.get("/learning/log", response_model=LearningLogResponse)
async def get_learning_log_entries(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum entries to return"),
    persona: Optional[str] = Query(default=None, description="Filter by persona")
):
    """
    Get recent RAG learning log entries.

    Returns entries with plain English descriptions, sorted newest first.
    This is the data shown in the UI's right sidebar.
    """
    log = get_learning_log()

    # Get entries with plain English descriptions
    entries = log.get_recent_entries_plain(limit)

    # Filter by persona if specified
    if persona:
        entries = [e for e in entries if e.get("persona") == persona]

    stats = log.get_stats()

    return LearningLogResponse(
        entries=[LearningLogEntry(**e) for e in entries],
        total=len(entries),
        stats=stats
    )


@router.get("/learning/stats", response_model=LearningStatsResponse)
async def get_learning_stats():
    """
    Get RAG learning statistics.

    Shows cache hit rate, learning rate, and other metrics.
    """
    log = get_learning_log()
    stats = log.get_stats()
    return LearningStatsResponse(**stats)


@router.get("/learning/log/db")
async def get_learning_log_from_db(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum entries to return"),
    offset: int = Query(default=0, ge=0, description="Number of entries to skip"),
    persona: Optional[str] = Query(default=None, description="Filter by persona")
):
    """
    Get RAG learning log entries from Supabase database.

    For historical analysis and reporting.
    """
    log = get_learning_log()
    entries = await log.get_entries_from_db(limit=limit, offset=offset, persona=persona)
    return {"entries": entries, "limit": limit, "offset": offset}


# =============================================================================
# CACHE MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/cache/stats")
async def get_cache_stats():
    """
    Get RAG cache statistics from Pinecone.

    Returns the number of cached queries and other metadata.
    """
    # Import here to avoid circular dependency
    from ..main import get_cache_service

    cache = get_cache_service()
    if cache:
        return cache.get_stats()
    return {"available": False, "error": "Cache service not initialized"}


@router.post("/cache/seed")
async def seed_cache(
    confirm: bool = Query(default=False, description="Must be true to proceed")
):
    """
    Seed the cache with common queries.

    Requires confirm=true query parameter.
    This is an admin operation.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=true to seed cache"
        )

    from ..main import get_cache_service

    cache = get_cache_service()
    if not cache or not cache.is_available:
        raise HTTPException(
            status_code=503,
            detail="Cache service not available"
        )

    # Import seed data
    try:
        from ...scripts.seed_data import SEED_QUERIES
        count = cache.bulk_store(SEED_QUERIES)
        return {"seeded": count, "status": "complete"}
    except ImportError:
        raise HTTPException(
            status_code=404,
            detail="Seed data not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to seed cache: {str(e)}"
        )


@router.delete("/cache/clear")
async def clear_cache(
    confirm: bool = Query(default=False, description="Must be true to proceed")
):
    """
    Clear all cached queries.

    DANGER: This deletes all learned queries from the cache.
    Requires confirm=true query parameter.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=true to clear cache"
        )

    from ..main import get_cache_service

    cache = get_cache_service()
    if not cache or not cache.is_available:
        raise HTTPException(
            status_code=503,
            detail="Cache service not available"
        )

    success = cache.delete_all(confirm=True)
    if success:
        return {"status": "cleared", "message": "All cached queries have been deleted"}
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to clear cache"
        )


# =============================================================================
# COMBINED STATUS ENDPOINT
# =============================================================================

@router.get("/status")
async def get_rag_status(
    session_id: str = Query(default="default", description="Browser session ID")
):
    """
    Get combined RAG system status.

    Returns session stats, learning stats, and cache stats in one call.
    Optimized for dashboard display.
    """
    counter = get_call_counter()
    log = get_learning_log()

    session_stats = counter.get_session_stats(session_id)
    learning_stats = log.get_stats()

    # Get recent log entries (last 10 for quick display)
    recent_entries = log.get_recent_entries_plain(10)

    # Get cache stats
    cache_stats = {"available": False}
    try:
        from ..main import get_cache_service
        cache = get_cache_service()
        if cache:
            cache_stats = cache.get_stats()
    except:
        pass

    return {
        "session": session_stats,
        "learning": learning_stats,
        "cache": cache_stats,
        "recent_log": recent_entries,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
