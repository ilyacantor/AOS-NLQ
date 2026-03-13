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
from ..services.query_cache_service import get_cache_service
from ..services.insufficient_data_tracker import get_insufficient_data_tracker

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


class InsufficientDataEntry(BaseModel):
    """Model for an insufficient data log entry."""
    id: str
    description: str
    query: str
    confidence: float
    reason: str
    persona: str
    timestamp: str


class InsufficientDataResponse(BaseModel):
    """Response model for insufficient data log."""
    entries: List[InsufficientDataEntry]
    total: int
    stats: dict
    message: str = "Possible insufficient data conditions detected"


class InsufficientDataStatsResponse(BaseModel):
    """Response model for insufficient data statistics."""
    total_entries: int
    avg_confidence: float
    by_reason: dict
    by_persona: dict
    threshold: float
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
    Get RAG cache statistics from Pinecone + hit rate health.

    Returns vector counts, hit rate, and a healthy flag (true if hit rate >= 60%).
    """
    cache = get_cache_service()
    pinecone_stats = cache.get_stats() if cache else {"available": False, "error": "Cache service not initialized"}

    log = get_learning_log()
    learning_stats = log.get_stats()
    hit_rate = learning_stats.get("cache_hit_rate", 0)
    total_queries = learning_stats.get("total_queries", 0)
    healthy = hit_rate >= 0.60 or total_queries < 10  # need sample size before judging

    if not healthy:
        logger.warning(
            f"Cache hit rate below 60%%: {hit_rate:.1%} over {total_queries} queries. "
            f"Tier 1 resolution may be degraded."
        )

    return {
        **pinecone_stats,
        "hit_rate": round(hit_rate, 4),
        "total_queries": total_queries,
        "from_cache": learning_stats.get("from_cache", 0),
        "from_llm": learning_stats.get("from_llm", 0),
        "healthy": healthy,
    }


@router.delete("/cache/entry")
async def delete_cache_entry(
    query: str = Query(..., description="The query to delete from cache")
):
    """
    Delete a specific cache entry by query text.
    
    Use this to remove corrupted or incorrect cache entries.
    """
    cache = get_cache_service()
    if not cache or not cache.is_available:
        raise HTTPException(
            status_code=503,
            detail="Cache service not available"
        )
    
    deleted = cache.delete_by_query(query)
    if deleted:
        return {"success": True, "message": f"Deleted cache entry for: {query}"}
    else:
        return {"success": False, "message": f"No exact match found for: {query}"}


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
    except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
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
        cache = get_cache_service()
        if cache:
            cache_stats = cache.get_stats()
    except (RuntimeError, KeyError, TypeError, ValueError, OSError):
        # Cache stats are non-critical, continue with default
        cache_stats = {"available": False, "error": "Failed to retrieve cache stats"}

    return {
        "session": session_stats,
        "learning": learning_stats,
        "cache": cache_stats,
        "recent_log": recent_entries,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# =============================================================================
# INSUFFICIENT DATA TRACKING ENDPOINTS
# =============================================================================

@router.get("/insufficient-data/log", response_model=InsufficientDataResponse)
async def get_insufficient_data_log(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum entries to return"),
    persona: Optional[str] = Query(default=None, description="Filter by persona")
):
    """
    Get recent queries that returned with low confidence (<80%).

    These represent possible insufficient data conditions where:
    - The metric was not recognized
    - The time period was unclear
    - The data was not available
    - The query was ambiguous

    This helps identify data gaps and query patterns that need better coverage.
    """
    tracker = get_insufficient_data_tracker()

    # Get entries with plain English descriptions
    entries = tracker.get_recent_entries_plain(limit)

    # Filter by persona if specified
    if persona:
        entries = [e for e in entries if e.get("persona") == persona]

    stats = tracker.get_stats()

    return InsufficientDataResponse(
        entries=[InsufficientDataEntry(**e) for e in entries],
        total=len(entries),
        stats=stats
    )


@router.get("/insufficient-data/stats", response_model=InsufficientDataStatsResponse)
async def get_insufficient_data_stats():
    """
    Get statistics about insufficient data conditions.

    Shows breakdown by reason and persona to help identify patterns.
    """
    tracker = get_insufficient_data_tracker()
    stats = tracker.get_stats()
    return InsufficientDataStatsResponse(**stats)


@router.get("/insufficient-data/log/db")
async def get_insufficient_data_from_db(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum entries to return"),
    offset: int = Query(default=0, ge=0, description="Number of entries to skip"),
    persona: Optional[str] = Query(default=None, description="Filter by persona")
):
    """
    Get insufficient data log entries from Supabase database.

    For historical analysis and reporting of data gaps.
    """
    tracker = get_insufficient_data_tracker()
    entries = await tracker.get_entries_from_db(limit=limit, offset=offset, persona=persona)
    return {"entries": entries, "limit": limit, "offset": offset}


@router.delete("/insufficient-data/clear")
async def clear_insufficient_data_log(
    confirm: bool = Query(default=False, description="Must be true to proceed")
):
    """
    Clear the in-memory insufficient data log.

    Requires confirm=true query parameter.
    Note: This only clears memory buffer, not database records.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=true to clear log"
        )

    tracker = get_insufficient_data_tracker()
    tracker.clear_memory()
    return {"status": "cleared", "message": "Insufficient data log memory cleared"}


# =============================================================================
# HISTORY ENDPOINT — server-side dedup replaces fragile localStorage
# =============================================================================

class HistoryItem(BaseModel):
    """A single deduplicated history entry."""
    query: str
    normalized_query: str
    count: int
    last_used: str
    tag: str
    execution_time_ms: Optional[int] = None
    persona: str = "CFO"


class HistoryResponse(BaseModel):
    """Response model for /rag/history."""
    entries: List[HistoryItem]
    total: int


@router.get("/history", response_model=HistoryResponse)
async def get_query_history(
    limit: int = Query(default=50, ge=1, le=200, description="Max unique queries to return"),
):
    """
    Get deduplicated query history from Supabase.

    Groups by normalized_query, returns unique queries with count and
    last_used timestamp, sorted most-recent first. The frontend History
    tab should use this instead of localStorage.

    Returns HTTP 503 if Supabase is unavailable (no silent fallback).
    """
    log = get_learning_log()
    try:
        entries = await log.get_aggregated_history(limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return HistoryResponse(
        entries=[HistoryItem(**e) for e in entries],
        total=len(entries),
    )


# =============================================================================
# CUMULATIVE STATS FROM DB — replaces localStorage stat accumulation
# =============================================================================

class CumulativeDbStatsResponse(BaseModel):
    """Response model for /rag/learning/stats/db."""
    total_queries: int
    from_cache: int
    from_llm: int
    from_bypass: int
    queries_learned: int
    cache_hit_rate: float
    learning_rate: float
    supabase_connected: bool


@router.get("/learning/stats/db", response_model=CumulativeDbStatsResponse)
async def get_cumulative_stats_from_db():
    """
    Get cumulative learning stats computed directly from Supabase.

    This replaces the fragile localStorage-based cumulative stat tracking
    on the frontend. Stats survive browser clears because they're computed
    from the DB on every request.

    Returns HTTP 503 if Supabase is unavailable (no silent fallback).
    """
    log = get_learning_log()
    try:
        stats = await log.get_cumulative_stats_from_db()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return CumulativeDbStatsResponse(**stats)


# =============================================================================
# RETENTION CLEANUP — admin endpoint + startup hook
# =============================================================================

@router.delete("/learning/cleanup")
async def cleanup_old_learning_entries(
    retention_days: int = Query(default=90, ge=1, le=365, description="Days to retain"),
    confirm: bool = Query(default=False, description="Must be true to proceed"),
):
    """
    Delete learning log entries older than retention_days.

    Requires confirm=true query parameter. Admin-only.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=true to run cleanup"
        )

    log = get_learning_log()
    deleted = await log.cleanup_old_entries(retention_days=retention_days)
    return {
        "status": "completed",
        "retention_days": retention_days,
        "deleted_approximately": deleted,
    }
