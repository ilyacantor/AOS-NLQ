"""
LLM Call Counter Service

Tracks the number of LLM API calls per browser session.
Provides real-time counts for display in the UI.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


@dataclass
class SessionStats:
    """Statistics for a single session."""
    session_id: str
    call_count: int = 0
    first_call_at: Optional[datetime] = None
    last_call_at: Optional[datetime] = None
    queries_cached: int = 0  # Queries served from cache
    queries_learned: int = 0  # Queries that were learned


class LLMCallCounter:
    """
    Tracks LLM API calls per browser session.

    This service maintains an in-memory count of LLM calls.
    The count resets when the browser session ends (client-side)
    or when the server restarts (server-side).

    Thread-safe for concurrent access.
    """

    def __init__(self):
        self._sessions: Dict[str, SessionStats] = {}
        self._global_count: int = 0
        self._lock = threading.Lock()
        self._start_time = datetime.utcnow()

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

            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(
                    session_id=session_id,
                    call_count=0,
                    first_call_at=datetime.utcnow()
                )

            stats = self._sessions[session_id]
            stats.call_count += 1
            stats.last_call_at = datetime.utcnow()

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
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(
                    session_id=session_id,
                    first_call_at=datetime.utcnow()
                )

            stats = self._sessions[session_id]
            stats.queries_cached += 1
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
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStats(
                    session_id=session_id,
                    first_call_at=datetime.utcnow()
                )

            stats = self._sessions[session_id]
            stats.queries_learned += 1
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
            if session_id not in self._sessions:
                return 0
            return self._sessions[session_id].call_count

    def get_session_stats(self, session_id: str = "default") -> Dict:
        """
        Get detailed statistics for a session.

        Args:
            session_id: Browser session identifier

        Returns:
            Dictionary with session statistics
        """
        with self._lock:
            if session_id not in self._sessions:
                return {
                    "session_id": session_id,
                    "llm_calls": 0,
                    "cached_queries": 0,
                    "learned_queries": 0,
                    "first_call_at": None,
                    "last_call_at": None,
                }

            stats = self._sessions[session_id]
            return {
                "session_id": stats.session_id,
                "llm_calls": stats.call_count,
                "cached_queries": stats.queries_cached,
                "learned_queries": stats.queries_learned,
                "first_call_at": stats.first_call_at.isoformat() if stats.first_call_at else None,
                "last_call_at": stats.last_call_at.isoformat() if stats.last_call_at else None,
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
                logger.info(f"Cleaned up {len(stale_sessions)} stale sessions")


# Singleton instance for the application
_counter_instance: Optional[LLMCallCounter] = None


def get_call_counter() -> LLMCallCounter:
    """Get the global LLM call counter instance."""
    global _counter_instance
    if _counter_instance is None:
        _counter_instance = LLMCallCounter()
    return _counter_instance
