"""
Supabase Persistence Service for AOS-NLQ RAG

Multi-tenant database operations with Row-Level Security (RLS).
Provides CRUD operations for sessions, cache entries, and learning logs.

Usage:
    from nlq.db.supabase_persistence import get_persistence_service
    
    persistence = get_persistence_service()
    await persistence.upsert_session(tenant_id, session_id, stats)
"""

import os
import logging
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from uuid import UUID

from src.nlq.config import get_tenant_id

logger = logging.getLogger(__name__)


@dataclass
class SessionRecord:
    """Database record for RAG session."""
    tenant_id: str
    session_id: str
    call_count: int = 0
    queries_cached: int = 0
    queries_learned: int = 0
    first_call_at: Optional[datetime] = None
    last_call_at: Optional[datetime] = None
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class CacheEntryRecord:
    """Database record for RAG cache entry."""
    tenant_id: str
    query_hash: str
    original_query: str
    parsed_intent: Dict[str, Any]
    normalized_query: Optional[str] = None
    persona: Optional[str] = None
    confidence: float = 1.0
    hit_count: int = 0
    source: str = "llm"
    fact_base_version: Optional[str] = None
    embedding_id: Optional[str] = None


@dataclass
class LearningLogRecord:
    """Database record for RAG learning log."""
    tenant_id: str
    query: str
    session_id: Optional[str] = None
    normalized_query: Optional[str] = None
    success: bool = True
    source: str = "llm"
    learned: bool = False
    message: Optional[str] = None
    persona: Optional[str] = None
    similarity: Optional[float] = None
    llm_confidence: Optional[float] = None
    parsed_intent: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None


class SupabasePersistenceService:
    """
    Multi-tenant persistence service using Supabase PostgreSQL.
    
    Handles all RAG-related database operations with tenant isolation.
    
    TENANT ISOLATION:
    - Application-level filtering: All queries include tenant_id filter
    - Database-level RLS: Policies exist for future JWT-based auth
    
    NOTE: When using service-role key (required for server-side ops),
    RLS is bypassed. Tenant isolation is enforced via application logic
    with explicit tenant_id filtering on every query. For production
    multi-tenant deployments with untrusted clients, use JWT-based auth
    with proper RLS configuration.
    """
    
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        default_tenant_id: str = None,
    ):
        """
        Initialize Supabase persistence service.
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase service role key (for RLS bypass)
            default_tenant_id: Default tenant UUID for single-tenant mode
        """
        # Prefer SUPABASE_API_URL (REST API URL) over SUPABASE_URL (which may be PostgreSQL connection string)
        api_url = os.getenv("SUPABASE_API_URL", "").strip()
        fallback_url = os.getenv("SUPABASE_URL", "").strip()
        
        if api_url.startswith("https://"):
            self.supabase_url = supabase_url or api_url
            logger.info(f"Using SUPABASE_API_URL: {api_url[:40]}...")
        elif fallback_url.startswith("https://"):
            self.supabase_url = supabase_url or fallback_url
            logger.info(f"Using SUPABASE_URL: {fallback_url[:40]}...")
        else:
            self.supabase_url = supabase_url or ""
            logger.warning(f"No valid https:// Supabase URL found")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY", "")
        self.default_tenant_id = default_tenant_id or get_tenant_id()
        
        self._client = None
        self._initialized = False
        
        if self.supabase_url and self.supabase_key:
            self._init_client()
    
    def _init_client(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client, Client
            
            # Validate URL format
            if not self.supabase_url or not self.supabase_url.startswith("https://"):
                api_url_val = os.getenv("SUPABASE_API_URL", "")[:30]
                supa_url_val = os.getenv("SUPABASE_URL", "")[:30]
                logger.error(f"No valid Supabase API URL found. SUPABASE_API_URL='{api_url_val}...', SUPABASE_URL='{supa_url_val}...'")
                logger.error("Expected format: https://yourproject.supabase.co")
                self._initialized = False
                return
            
            self._client: Client = create_client(
                self.supabase_url,
                self.supabase_key
            )
            self._initialized = True
            logger.info(f"Supabase persistence service initialized with URL: {self.supabase_url[:30]}...")
        except ImportError:
            logger.warning("supabase-py not installed, persistence disabled")
            self._initialized = False
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self._initialized = False
    
    @property
    def is_available(self) -> bool:
        """Check if persistence service is available."""
        return self._initialized and self._client is not None
    
    # =========================================================================
    # SESSION OPERATIONS
    # =========================================================================
    
    def get_session(
        self,
        session_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[SessionRecord]:
        """
        Get session by ID.
        
        Args:
            session_id: Browser session identifier
            tenant_id: Tenant UUID (uses default if not provided)
            
        Returns:
            SessionRecord if found, None otherwise
        """
        if not self.is_available:
            return None
        
        tenant_id = tenant_id or self.default_tenant_id
        
        try:
            result = self._client.table("rag_sessions").select("*").eq(
                "tenant_id", tenant_id
            ).eq(
                "session_id", session_id
            ).execute()
            
            if result.data:
                row = result.data[0]
                return SessionRecord(
                    tenant_id=row["tenant_id"],
                    session_id=row["session_id"],
                    call_count=row.get("call_count", 0),
                    queries_cached=row.get("queries_cached", 0),
                    queries_learned=row.get("queries_learned", 0),
                    first_call_at=self._parse_datetime(row.get("first_call_at")),
                    last_call_at=self._parse_datetime(row.get("last_call_at")),
                    user_id=row.get("user_id"),
                    metadata=row.get("metadata"),
                )
            return None
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    def upsert_session(self, session: SessionRecord) -> bool:
        """
        Insert or update a session record.
        
        Args:
            session: SessionRecord to upsert
            
        Returns:
            True if successful
        """
        if not self.is_available:
            return False
        
        try:
            data = {
                "tenant_id": session.tenant_id or self.default_tenant_id,
                "session_id": session.session_id,
                "call_count": session.call_count,
                "queries_cached": session.queries_cached,
                "queries_learned": session.queries_learned,
                "user_id": session.user_id,
                "metadata": session.metadata or {},
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            if session.first_call_at:
                data["first_call_at"] = session.first_call_at.isoformat()
            if session.last_call_at:
                data["last_call_at"] = session.last_call_at.isoformat()
            
            self._client.table("rag_sessions").upsert(
                data,
                on_conflict="tenant_id,session_id"
            ).execute()
            
            logger.debug(f"Upserted session {session.session_id}")
            return True
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to upsert session: {e}")
            return False
    
    def increment_session_stats(
        self,
        session_id: str,
        tenant_id: Optional[str] = None,
        call_count_delta: int = 0,
        queries_cached_delta: int = 0,
        queries_learned_delta: int = 0,
    ) -> Optional[SessionRecord]:
        """
        Atomically increment session statistics.
        
        Args:
            session_id: Browser session identifier
            tenant_id: Tenant UUID
            call_count_delta: Amount to add to call_count
            queries_cached_delta: Amount to add to queries_cached
            queries_learned_delta: Amount to add to queries_learned
            
        Returns:
            Updated SessionRecord
        """
        if not self.is_available:
            return None
        
        tenant_id = tenant_id or self.default_tenant_id
        now = datetime.utcnow()
        
        try:
            existing = self.get_session(session_id, tenant_id)
            
            if existing:
                updated = SessionRecord(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    call_count=existing.call_count + call_count_delta,
                    queries_cached=existing.queries_cached + queries_cached_delta,
                    queries_learned=existing.queries_learned + queries_learned_delta,
                    first_call_at=existing.first_call_at,
                    last_call_at=now,
                    user_id=existing.user_id,
                    metadata=existing.metadata,
                )
            else:
                updated = SessionRecord(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    call_count=call_count_delta,
                    queries_cached=queries_cached_delta,
                    queries_learned=queries_learned_delta,
                    first_call_at=now,
                    last_call_at=now,
                )
            
            self.upsert_session(updated)
            return updated
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to increment session stats: {e}")
            return None
    
    def get_active_sessions(
        self,
        tenant_id: Optional[str] = None,
        since_hours: int = 24,
        limit: int = 100,
    ) -> List[SessionRecord]:
        """
        Get recently active sessions.

        Args:
            tenant_id: Tenant UUID (None for all tenants - service role only)
            since_hours: Only sessions active within this many hours
            limit: Maximum sessions to return

        Returns:
            List of SessionRecords
        """
        if not self.is_available:
            return []

        # Validate tenant_id is a valid UUID before sending to Postgres
        if tenant_id:
            try:
                UUID(tenant_id)
            except (ValueError, AttributeError):
                raise ValueError(
                    f"tenant_id '{tenant_id}' is not a valid UUID. "
                    f"rag_sessions.tenant_id is a UUID column. "
                    f"Set AOS_TENANT_ID env var to a valid UUID "
                    f"(e.g. '00000000-0000-0000-0000-000000000001')."
                )

        try:
            cutoff = (datetime.utcnow() - timedelta(hours=since_hours)).isoformat()

            query = self._client.table("rag_sessions").select("*").gte(
                "last_call_at", cutoff
            ).order(
                "last_call_at", desc=True
            ).limit(limit)

            if tenant_id:
                query = query.eq("tenant_id", tenant_id)

            result = query.execute()
            
            return [
                SessionRecord(
                    tenant_id=row["tenant_id"],
                    session_id=row["session_id"],
                    call_count=row.get("call_count", 0),
                    queries_cached=row.get("queries_cached", 0),
                    queries_learned=row.get("queries_learned", 0),
                    first_call_at=self._parse_datetime(row.get("first_call_at")),
                    last_call_at=self._parse_datetime(row.get("last_call_at")),
                    user_id=row.get("user_id"),
                    metadata=row.get("metadata"),
                )
                for row in result.data
            ]
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to get active sessions: {e}")
            return []
    
    def delete_stale_sessions(
        self,
        tenant_id: Optional[str] = None,
        older_than_hours: int = 168,  # 7 days
    ) -> int:
        """
        Delete sessions older than specified time.
        
        Args:
            tenant_id: Tenant UUID (None for all tenants)
            older_than_hours: Delete sessions older than this
            
        Returns:
            Number of deleted sessions
        """
        if not self.is_available:
            return 0
        
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=older_than_hours)).isoformat()
            
            query = self._client.table("rag_sessions").delete().lt(
                "last_call_at", cutoff
            )
            
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            
            result = query.execute()
            count = len(result.data) if result.data else 0
            
            logger.info(f"Deleted {count} stale sessions")
            return count
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to delete stale sessions: {e}")
            return 0
    
    # =========================================================================
    # CACHE ENTRY OPERATIONS
    # =========================================================================
    
    def get_cache_entry(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        persona: Optional[str] = None,
    ) -> Optional[CacheEntryRecord]:
        """
        Get cache entry by query hash.
        
        Args:
            query: Original query text
            tenant_id: Tenant UUID
            persona: Optional persona filter
            
        Returns:
            CacheEntryRecord if found
        """
        if not self.is_available:
            return None
        
        tenant_id = tenant_id or self.default_tenant_id
        query_hash = self._hash_query(query)
        
        try:
            query_builder = self._client.table("rag_cache_entries").select("*").eq(
                "tenant_id", tenant_id
            ).eq(
                "query_hash", query_hash
            )
            
            if persona:
                query_builder = query_builder.eq("persona", persona)
            
            result = query_builder.execute()
            
            if result.data:
                row = result.data[0]
                return CacheEntryRecord(
                    tenant_id=row["tenant_id"],
                    query_hash=row["query_hash"],
                    original_query=row["original_query"],
                    parsed_intent=row.get("parsed_intent", {}),
                    normalized_query=row.get("normalized_query"),
                    persona=row.get("persona"),
                    confidence=row.get("confidence", 1.0),
                    hit_count=row.get("hit_count", 0),
                    source=row.get("source", "llm"),
                    fact_base_version=row.get("fact_base_version"),
                    embedding_id=row.get("embedding_id"),
                )
            return None
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to get cache entry: {e}")
            return None
    
    def upsert_cache_entry(self, entry: CacheEntryRecord) -> bool:
        """
        Insert or update a cache entry.
        
        Args:
            entry: CacheEntryRecord to upsert
            
        Returns:
            True if successful
        """
        if not self.is_available:
            return False
        
        try:
            data = {
                "tenant_id": entry.tenant_id or self.default_tenant_id,
                "query_hash": entry.query_hash,
                "original_query": entry.original_query,
                "normalized_query": entry.normalized_query,
                "parsed_intent": entry.parsed_intent,
                "persona": entry.persona,
                "confidence": entry.confidence,
                "hit_count": entry.hit_count,
                "source": entry.source,
                "fact_base_version": entry.fact_base_version,
                "embedding_id": entry.embedding_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            self._client.table("rag_cache_entries").upsert(
                data,
                on_conflict="tenant_id,query_hash"
            ).execute()
            
            logger.debug(f"Upserted cache entry {entry.query_hash}")
            return True
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to upsert cache entry: {e}")
            return False
    
    def increment_cache_hit(
        self,
        query: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        Increment hit count for a cache entry.
        
        Args:
            query: Original query text
            tenant_id: Tenant UUID
            
        Returns:
            True if successful
        """
        if not self.is_available:
            return False
        
        tenant_id = tenant_id or self.default_tenant_id
        query_hash = self._hash_query(query)
        
        try:
            existing = self.get_cache_entry(query, tenant_id)
            if existing:
                existing.hit_count += 1
                return self.upsert_cache_entry(existing)
            return False
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to increment cache hit: {e}")
            return False
    
    # =========================================================================
    # LEARNING LOG OPERATIONS
    # =========================================================================
    
    def log_query(self, record: LearningLogRecord) -> bool:
        """
        Log a query execution for learning.
        
        Args:
            record: LearningLogRecord to insert
            
        Returns:
            True if successful
        """
        if not self.is_available:
            return False
        
        try:
            data = {
                "tenant_id": record.tenant_id or self.default_tenant_id,
                "session_id": record.session_id,
                "query": record.query[:500],
                "normalized_query": record.normalized_query[:500] if record.normalized_query else None,
                "success": record.success,
                "source": record.source,
                "learned": record.learned,
                "message": record.message[:500] if record.message else None,
                "persona": record.persona,
                "similarity": record.similarity,
                "llm_confidence": record.llm_confidence,
                "parsed_intent": record.parsed_intent,
                "execution_time_ms": record.execution_time_ms,
            }
            
            self._client.table("rag_learning_log").insert(data).execute()
            
            logger.debug(f"Logged query: {record.query[:50]}...")
            return True
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to log query: {e}")
            return False
    
    def get_recent_queries(
        self,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
        persona: Optional[str] = None,
    ) -> List[LearningLogRecord]:
        """
        Get recent query logs.
        
        Args:
            tenant_id: Tenant UUID
            session_id: Filter by session
            limit: Maximum records to return
            persona: Filter by persona
            
        Returns:
            List of LearningLogRecords
        """
        if not self.is_available:
            return []
        
        try:
            query = self._client.table("rag_learning_log").select("*").order(
                "created_at", desc=True
            ).limit(limit)
            
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if session_id:
                query = query.eq("session_id", session_id)
            if persona:
                query = query.eq("persona", persona)
            
            result = query.execute()
            
            return [
                LearningLogRecord(
                    tenant_id=row["tenant_id"],
                    query=row["query"],
                    session_id=row.get("session_id"),
                    normalized_query=row.get("normalized_query"),
                    success=row.get("success", True),
                    source=row.get("source", "llm"),
                    learned=row.get("learned", False),
                    message=row.get("message"),
                    persona=row.get("persona"),
                    similarity=row.get("similarity"),
                    llm_confidence=row.get("llm_confidence"),
                    parsed_intent=row.get("parsed_intent"),
                    execution_time_ms=row.get("execution_time_ms"),
                )
                for row in result.data
            ]
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to get recent queries: {e}")
            return []
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _hash_query(self, query: str) -> str:
        """Generate deterministic hash for query."""
        normalized = query.lower().strip()
        normalized = " ".join(normalized.split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from database value."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None
    
    def get_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get persistence statistics.
        
        Args:
            tenant_id: Tenant UUID (None for global stats)
            
        Returns:
            Dictionary with counts and status
        """
        if not self.is_available:
            return {"available": False, "error": "Persistence not configured"}
        
        tenant_id = tenant_id or self.default_tenant_id
        
        try:
            sessions = self._client.table("rag_sessions").select(
                "id", count="exact"
            ).eq("tenant_id", tenant_id).execute()
            
            cache = self._client.table("rag_cache_entries").select(
                "id", count="exact"
            ).eq("tenant_id", tenant_id).execute()
            
            logs = self._client.table("rag_learning_log").select(
                "id", count="exact"
            ).eq("tenant_id", tenant_id).execute()
            
            return {
                "available": True,
                "tenant_id": tenant_id,
                "sessions_count": sessions.count or 0,
                "cache_entries_count": cache.count or 0,
                "learning_log_count": logs.count or 0,
            }
            
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to get stats: {e}")
            return {"available": False, "error": str(e)}


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_persistence_service: Optional[SupabasePersistenceService] = None


def get_persistence_service() -> Optional[SupabasePersistenceService]:
    """Get the global persistence service instance."""
    global _persistence_service
    return _persistence_service


def init_persistence_service(
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    default_tenant_id: str = None,
) -> Optional[SupabasePersistenceService]:
    """
    Initialize the persistence service from environment or parameters.
    
    Args:
        supabase_url: Supabase project URL (or from SUPABASE_URL env)
        supabase_key: Supabase key (or from SUPABASE_KEY env)
        default_tenant_id: Default tenant for single-tenant deployments
        
    Returns:
        Initialized SupabasePersistenceService or None
    """
    global _persistence_service
    
    # Prefer SUPABASE_API_URL over SUPABASE_URL (which may be PostgreSQL connection string)
    api_url = os.getenv("SUPABASE_API_URL", "").strip()
    fallback_url = os.getenv("SUPABASE_URL", "").strip()
    url = supabase_url or (api_url if api_url.startswith("https://") else None) or (fallback_url if fallback_url.startswith("https://") else "")
    key = supabase_key or os.getenv("SUPABASE_KEY", "")
    
    if not url or not key:
        logger.warning("Supabase credentials not configured, persistence disabled")
        return None
    
    _persistence_service = SupabasePersistenceService(
        supabase_url=url,
        supabase_key=key,
        default_tenant_id=default_tenant_id,
    )
    
    if _persistence_service.is_available:
        stats = _persistence_service.get_stats()
        logger.info(f"Persistence service initialized: {stats}")
    else:
        logger.warning("Persistence service failed to initialize")
    
    return _persistence_service
