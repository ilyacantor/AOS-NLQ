"""
LLM Call Counter Service

Tracks the number of LLM API calls per browser session.
Provides real-time counts for display in the UI.

Now with Supabase persistence for cross-restart session recovery.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass
class SessionStats:
    """Statistics for a single session."""
    session_id: str
    call_count: int = 0
    first_call_at: Optional[datetime] = None
    last_call_at: Optional[datetime] = None
    queries_cached: int = 0
    queries_learned: int = 0


class LLMCallCounter:
    """
    Tracks LLM API calls per browser session.

    This service maintains an in-memory count of LLM calls with
    optional persistence to Supabase PostgreSQL for session recovery.

    Thread-safe for concurrent access.
    """

    def __init__(self, tenant_id: str = DEFAULT_TENANT_ID, persist: bool = True):
        """
        Initialize the LLM call counter.
        
        Args:
            tenant_id: Tenant UUID for multi-tenant isolation
            persist: Whether to persist to database
        """
        self._sessions: Dict[str, SessionStats] = {}
        self._global_count: int = 0
        self._lock = threading.Lock()
        self._start_time = datetime.utcnow()
        self._tenant_id = tenant_id
        self._persist = persist
        self._persistence = None
        
        if persist:
            self._init_persistence()

    def _init_persistence(self):
        """Initialize persistence service connection."""
        try:
            from nlq.db.supabase_persistence import get_persistence_service
            self._persistence = get_persistence_service()
            if self._persistence and self._persistence.is_available:
                logger.info("LLMCallCounter connected to persistence service")
            else:
                logger.warning("Persistence service not available, using memory only")
                self._persistence = None
        except ImportError:
            logger.warning("Persistence module not available")
            self._persistence = None

    def _load_session_from_db(self, session_id: str) -> Optional[SessionStats]:
        """Load session from database if available."""
        if not self._persistence:
            return None
        
        try:
            record = self._persistence.get_session(session_id, self._tenant_id)
            if record:
                return SessionStats(
                    session_id=record.session_id,
                    call_count=record.call_count,
                    first_call_at=record.first_call_at,
                    last_call_at=record.last_call_at,
                    queries_cached=record.queries_cached,
                    queries_learned=record.queries_learned,
                )
        except Exception as e:
            logger.error(f"Failed to load session from DB: {e}")
        return None

    def _save_session_to_db(self, stats: SessionStats):
        """Save session to database asynchronously."""
        if not self._persistence:
            return
        
        try:
            from nlq.db.supabase_persistence import SessionRecord
            record = SessionRecord(
                tenant_id=self._tenant_id,
                session_id=stats.session_id,
                call_count=stats.call_count,
                queries_cached=stats.queries_cached,
                queries_learned=stats.queries_learned,
                first_call_at=stats.first_call_at,
                last_call_at=stats.last_call_at,
            )
            self._persistence.upsert_session(record)
        except Exception as e:
            logger.error(f"Failed to save session to DB: {e}")

    def _get_or_create_session(self, session_id: str) -> SessionStats:
        """Get existing session or create new one, checking DB first."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        db_session = self._load_session_from_db(session_id)
        if db_session:
            self._sessions[session_id] = db_session
            return db_session
        
        new_session = SessionStats(
            session_id=session_id,
            call_count=0,
            first_call_at=datetime.utcnow()
        )
        self._sessions[session_id] = new_session
        return new_session

    def increment(self, session_id: str = "default") -> int:
        """
        Increment the call count for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            New call count for the session
        """
        with self._lock:
            self._global_count += 1
            stats = self._get_or_create_session(session_id)
            stats.call_count += 1
            stats.last_call_at = datetime.utcnow()

            logger.debug(f"LLM call count for session {session_id}: {stats.call_count}")
            
            self._save_session_to_db(stats)
            return stats.call_count

    def increment_cached(self, session_id: str = "default") -> int:
        """
        Increment the cached query count for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            New cached count for the session
        """
        with self._lock:
            stats = self._get_or_create_session(session_id)
            stats.queries_cached += 1
            stats.last_call_at = datetime.utcnow()
            
            self._save_session_to_db(stats)
            return stats.queries_cached

    def increment_learned(self, session_id: str = "default") -> int:
        """
        Increment the learned query count for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            New learned count for the session
        """
        with self._lock:
            stats = self._get_or_create_session(session_id)
            stats.queries_learned += 1
            stats.last_call_at = datetime.utcnow()
            
            self._save_session_to_db(stats)
            return stats.queries_learned

    def get_count(self, session_id: str = "default") -> int:
        """
        Get the current LLM call count for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            Current call count (0 if session not found)
        """
        with self._lock:
            stats = self._get_or_create_session(session_id)
            return stats.call_count

    def get_session_stats(self, session_id: str = "default") -> Dict:
        """
        Get detailed statistics for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            Dictionary with session statistics
        """
        with self._lock:
            stats = self._get_or_create_session(session_id)
            return {
                "session_id": stats.session_id,
                "llm_calls": stats.call_count,
                "cached_queries": stats.queries_cached,
                "learned_queries": stats.queries_learned,
                "first_call_at": stats.first_call_at.isoformat() if stats.first_call_at else None,
                "last_call_at": stats.last_call_at.isoformat() if stats.last_call_at else None,
                "persisted": self._persistence is not None,
            }

    def get_global_stats(self) -> Dict:
        """
        Get global statistics across all sessions.

        Returns:
            Dictionary with global statistics
        """
        with self._lock:
            total_cached = sum(s.queries_cached for s in self._sessions.values())
            total_learned = sum(s.queries_learned for s in self._sessions.values())

            return {
                "total_llm_calls": self._global_count,
                "total_cached_queries": total_cached,
                "total_learned_queries": total_learned,
                "active_sessions": len(self._sessions),
                "server_start_time": self._start_time.isoformat(),
                "uptime_seconds": (datetime.utcnow() - self._start_time).total_seconds(),
                "persistence_enabled": self._persistence is not None,
                "tenant_id": self._tenant_id,
            }

    def reset_session(self, session_id: str = "default") -> bool:
        """
        Reset the counter for a specific session.

        Args:
            session_id: Browser session identifier

        Returns:
            True if session was reset, False if not found
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Reset LLM call counter for session {session_id}")
                return True
            return False

    def cleanup_stale_sessions(self, max_age_hours: int = 24):
        """
        Remove sessions that haven't been active for a while.

        Args:
            max_age_hours: Maximum age in hours before session is removed
        """
        with self._lock:
            now = datetime.utcnow()
            stale_sessions = []

            for session_id, stats in self._sessions.items():
                if stats.last_call_at:
                    age_hours = (now - stats.last_call_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        stale_sessions.append(session_id)

            for session_id in stale_sessions:
                del self._sessions[session_id]

            if stale_sessions:
                logger.info(f"Cleaned up {len(stale_sessions)} stale sessions from memory")
        
        if self._persistence:
            try:
                deleted = self._persistence.delete_stale_sessions(
                    self._tenant_id, 
                    older_than_hours=max_age_hours * 7
                )
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} stale sessions from database")
            except Exception as e:
                logger.error(f"Failed to cleanup stale sessions from DB: {e}")

    def load_active_sessions(self, since_hours: int = 24) -> int:
        """
        Load active sessions from database into memory.
        Called on startup to restore session state.

        Args:
            since_hours: Load sessions active within this many hours

        Returns:
            Number of sessions loaded
        """
        if not self._persistence:
            return 0

        try:
            records = self._persistence.get_active_sessions(
                tenant_id=self._tenant_id,
                since_hours=since_hours,
                limit=500,
            )
            
            with self._lock:
                for record in records:
                    if record.session_id not in self._sessions:
                        self._sessions[record.session_id] = SessionStats(
                            session_id=record.session_id,
                            call_count=record.call_count,
                            first_call_at=record.first_call_at,
                            last_call_at=record.last_call_at,
                            queries_cached=record.queries_cached,
                            queries_learned=record.queries_learned,
                        )
                        self._global_count += record.call_count
            
            logger.info(f"Loaded {len(records)} active sessions from database")
            return len(records)
            
        except Exception as e:
            logger.error(f"Failed to load active sessions: {e}")
            return 0


_counter_instance: Optional[LLMCallCounter] = None


def get_call_counter() -> LLMCallCounter:
    """Get the global LLM call counter instance."""
    global _counter_instance
    if _counter_instance is None:
        _counter_instance = LLMCallCounter()
    return _counter_instance


def init_call_counter(tenant_id: str = DEFAULT_TENANT_ID, persist: bool = True) -> LLMCallCounter:
    """
    Initialize the call counter with specific configuration.
    
    Args:
        tenant_id: Tenant UUID for multi-tenant isolation
        persist: Whether to persist to database
        
    Returns:
        Initialized LLMCallCounter instance
    """
    global _counter_instance
    _counter_instance = LLMCallCounter(tenant_id=tenant_id, persist=persist)
    
    if persist:
        _counter_instance.load_active_sessions()
    
    return _counter_instance
