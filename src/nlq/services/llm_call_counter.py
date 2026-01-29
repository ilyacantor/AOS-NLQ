"""
LLM Call Counter Service

Tracks the number of LLM API calls per browser session.
Provides real-time counts for display in the UI.
Supports persistence via Pinecone for cross-restart recovery.
"""

import logging
import os
import atexit
from datetime import datetime
from typing import Dict, Optional, Set
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)

SESSIONS_NAMESPACE = "nlq-sessions"


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

    This service maintains session statistics with optional Pinecone persistence.
    When Pinecone is configured, sessions persist across server restarts.
    Uses buffered writes to avoid blocking on every request.

    Thread-safe for concurrent access.
    """

    def __init__(self, pinecone_api_key: str = None):
        self._sessions: Dict[str, SessionStats] = {}
        self._dirty_sessions: Set[str] = set()
        self._global_count: int = 0
        self._lock = threading.Lock()
        self._start_time = datetime.utcnow()
        
        self._index = None
        self._persistence_enabled = False
        self._flush_timer: Optional[threading.Timer] = None
        self._flush_interval = 5.0
        
        pc_key = pinecone_api_key or os.getenv("PINECONE_API_KEY", "")
        
        if pc_key:
            self._init_pinecone(pc_key)
            atexit.register(self._flush_dirty_sessions)

    def _init_pinecone(self, api_key: str):
        """Initialize Pinecone for session persistence using existing index."""
        try:
            from pinecone import Pinecone
            
            pc = Pinecone(api_key=api_key)
            index_name = os.getenv("PINECONE_INDEX", "aos-nlq")
            
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            
            if index_name not in existing_indexes:
                logger.warning(f"Pinecone index '{index_name}' not found. Session persistence disabled.")
                logger.info("Run the RAG cache initialization first to create the index.")
                return
            
            self._index = pc.Index(index_name)
            self._persistence_enabled = True
            logger.info(f"Session persistence enabled via Pinecone (namespace: {SESSIONS_NAMESPACE})")
            
        except ImportError:
            logger.warning("Pinecone not installed, session persistence disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone for sessions: {e}")

    @property
    def persistence_enabled(self) -> bool:
        """Check if session persistence is available."""
        return self._persistence_enabled

    def _load_session_from_pinecone(self, session_id: str) -> Optional[SessionStats]:
        """Load a session from Pinecone if it exists."""
        if not self._persistence_enabled:
            return None
            
        try:
            result = self._index.fetch(
                ids=[f"ses_{session_id}"],
                namespace=SESSIONS_NAMESPACE
            )
            
            vectors = result.get("vectors", {})
            if not vectors:
                return None
                
            vector_data = vectors.get(f"ses_{session_id}")
            if not vector_data:
                return None
                
            metadata = vector_data.get("metadata", {})
            
            first_call = None
            if metadata.get("first_call_at"):
                try:
                    first_call = datetime.fromisoformat(metadata["first_call_at"].replace("Z", "+00:00"))
                except:
                    first_call = None
                    
            last_call = None
            if metadata.get("last_call_at"):
                try:
                    last_call = datetime.fromisoformat(metadata["last_call_at"].replace("Z", "+00:00"))
                except:
                    last_call = None
            
            stats = SessionStats(
                session_id=session_id,
                call_count=int(metadata.get("call_count", 0)),
                queries_cached=int(metadata.get("queries_cached", 0)),
                queries_learned=int(metadata.get("queries_learned", 0)),
                first_call_at=first_call,
                last_call_at=last_call,
            )
            
            logger.info(f"Loaded session {session_id} from Pinecone: {stats.call_count} calls")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to load session from Pinecone: {e}")
            return None

    def _mark_dirty(self, session_id: str):
        """Mark a session as needing persistence and schedule flush."""
        self._dirty_sessions.add(session_id)
        self._schedule_flush()

    def _schedule_flush(self):
        """Schedule a flush of dirty sessions (debounced)."""
        if self._flush_timer is not None:
            return
            
        def do_flush():
            self._flush_timer = None
            self._flush_dirty_sessions()
            
        self._flush_timer = threading.Timer(self._flush_interval, do_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_dirty_sessions(self):
        """Flush all dirty sessions to Pinecone in a batch."""
        if not self._persistence_enabled:
            return
            
        with self._lock:
            if not self._dirty_sessions:
                return
                
            sessions_to_save = list(self._dirty_sessions)
            self._dirty_sessions.clear()
        
        vectors = []
        for session_id in sessions_to_save:
            stats = self._sessions.get(session_id)
            if not stats:
                continue
                
            dummy_vector = [0.0] * 1536
            metadata = {
                "session_id": stats.session_id,
                "call_count": stats.call_count,
                "queries_cached": stats.queries_cached,
                "queries_learned": stats.queries_learned,
                "first_call_at": stats.first_call_at.isoformat() + "Z" if stats.first_call_at else "",
                "last_call_at": stats.last_call_at.isoformat() + "Z" if stats.last_call_at else "",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
            
            vectors.append({
                "id": f"ses_{stats.session_id}",
                "values": dummy_vector,
                "metadata": metadata
            })
        
        if vectors:
            try:
                self._index.upsert(
                    vectors=vectors,
                    namespace=SESSIONS_NAMESPACE
                )
                logger.debug(f"Flushed {len(vectors)} sessions to Pinecone")
            except Exception as e:
                logger.error(f"Failed to flush sessions to Pinecone: {e}")
                with self._lock:
                    self._dirty_sessions.update(sessions_to_save)

    def _get_or_create_session(self, session_id: str) -> SessionStats:
        """Get existing session or create new one, checking Pinecone first."""
        if session_id in self._sessions:
            return self._sessions[session_id]
            
        persisted = self._load_session_from_pinecone(session_id)
        if persisted:
            self._sessions[session_id] = persisted
            return persisted
            
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
            self._mark_dirty(session_id)
            
            logger.debug(f"LLM call count for session {session_id}: {stats.call_count}")
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
            self._mark_dirty(session_id)
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
            self._mark_dirty(session_id)
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
                "persistence_enabled": self._persistence_enabled,
            }

    def get_global_stats(self) -> Dict:
        """
        Get global statistics across all sessions.
        Note: Global counts are per-server-lifetime, not persisted.

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
                "persistence_enabled": self._persistence_enabled,
                "pending_flush": len(self._dirty_sessions),
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
                self._dirty_sessions.discard(session_id)
                
                if self._persistence_enabled:
                    try:
                        self._index.delete(
                            ids=[f"ses_{session_id}"],
                            namespace=SESSIONS_NAMESPACE
                        )
                        logger.info(f"Deleted session {session_id} from Pinecone")
                    except Exception as e:
                        logger.error(f"Failed to delete session from Pinecone: {e}")
                
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
                self._dirty_sessions.discard(session_id)

            if stale_sessions:
                logger.info(f"Cleaned up {len(stale_sessions)} stale sessions from memory")

    def force_flush(self):
        """Force immediate flush of all dirty sessions."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None
        self._flush_dirty_sessions()


_counter_instance: Optional[LLMCallCounter] = None


def get_call_counter() -> LLMCallCounter:
    """Get the global LLM call counter instance."""
    global _counter_instance
    if _counter_instance is None:
        _counter_instance = LLMCallCounter()
    return _counter_instance
