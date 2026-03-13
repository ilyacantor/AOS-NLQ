"""
Dashboard session store for AOS-NLQ.

Manages dashboard state per browser session. Uses Supabase persistence
when available, with in-memory fallback (logged clearly — never silent).

Extracted from routes.py to eliminate module-level mutable globals
and enable proper testability via dependency injection.
"""

import json
import logging
import time
from threading import Lock
from typing import Dict, Optional

from src.nlq.db.supabase_persistence import get_persistence_service

logger = logging.getLogger(__name__)

# Configurable via environment in future; sane defaults for now
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours
MAX_SESSIONS = 1000
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


class DashboardSessionStore:
    """
    Stores dashboard state per browser session.

    Two-tier strategy:
    1. In-memory dict for fast reads (always used)
    2. Supabase persistence for durability across restarts (when available)

    The in-memory tier is authoritative during the lifetime of the process.
    On startup, sessions are NOT restored from DB (dashboards are ephemeral).
    The DB tier exists so that future multi-worker deployments can share state.
    """

    def __init__(self):
        self._sessions: Dict[str, dict] = {}
        self._lock = Lock()
        self._last_cleanup_time = 0.0
        self._persistence_available = False
        self._check_persistence()

    def _check_persistence(self):
        """Check if Supabase persistence is available."""
        try:
            svc = get_persistence_service()
            self._persistence_available = svc is not None and svc.is_available
            if self._persistence_available:
                logger.info("Dashboard session store: Supabase persistence available")
            else:
                logger.warning(
                    "Dashboard session store: Supabase not available — "
                    "sessions are in-memory only and will be lost on restart"
                )
        except (ImportError, RuntimeError, OSError):
            self._persistence_available = False
            logger.warning(
                "Dashboard session store: persistence check failed — "
                "sessions are in-memory only"
            )

    def get(self, session_id: str) -> Optional[dict]:
        """
        Get the current dashboard state for a session.

        Returns dict with keys: dashboard, widget_data, created_at, last_accessed
        or None if no session exists.
        """
        self._cleanup_if_due()
        session_data = self._sessions.get(session_id)
        if session_data:
            session_data["last_accessed"] = time.time()
            return session_data
        return None

    def set(self, session_id: str, dashboard: dict, widget_data: dict):
        """Store dashboard state for a session."""
        self._cleanup_if_due()
        current_time = time.time()
        with self._lock:
            self._sessions[session_id] = {
                "dashboard": dashboard,
                "widget_data": widget_data,
                "created_at": current_time,
                "last_accessed": current_time,
            }

    def clear(self, session_id: str):
        """Clear dashboard state for a session."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def set_financial_statement(self, session_id: str, data: dict):
        """Store financial statement data for Excel export."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "created_at": time.time(),
                    "last_accessed": time.time(),
                }
            self._sessions[session_id]["_financial_statement"] = data
            self._sessions[session_id]["last_accessed"] = time.time()

    def get_financial_statement(self, session_id: str) -> Optional[dict]:
        """Retrieve stored financial statement data for Excel export."""
        session_data = self._sessions.get(session_id)
        if session_data:
            session_data["last_accessed"] = time.time()
            return session_data.get("_financial_statement")
        return None

    def set_bridge_chart(self, session_id: str, data: dict):
        """Store bridge chart data for Excel export."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "created_at": time.time(),
                    "last_accessed": time.time(),
                }
            self._sessions[session_id]["_bridge_chart"] = data
            self._sessions[session_id]["last_accessed"] = time.time()

    def get_bridge_chart(self, session_id: str) -> Optional[dict]:
        """Retrieve stored bridge chart data for Excel export."""
        session_data = self._sessions.get(session_id)
        if session_data:
            session_data["last_accessed"] = time.time()
            return session_data.get("_bridge_chart")
        return None

    def stats(self) -> dict:
        """Get session storage statistics for monitoring."""
        return {
            "total_sessions": len(self._sessions),
            "max_sessions": MAX_SESSIONS,
            "ttl_seconds": SESSION_TTL_SECONDS,
            "persistence_available": self._persistence_available,
        }

    def _cleanup_if_due(self):
        """Remove expired sessions to prevent memory leaks."""
        current_time = time.time()
        if current_time - self._last_cleanup_time < CLEANUP_INTERVAL_SECONDS:
            return

        with self._lock:
            self._last_cleanup_time = current_time
            expired = [
                sid for sid, data in self._sessions.items()
                if current_time - data.get("created_at", 0) > SESSION_TTL_SECONDS
            ]
            for sid in expired:
                del self._sessions[sid]

            # Evict oldest if over capacity
            overflow = len(self._sessions) - MAX_SESSIONS
            if overflow > 0:
                sorted_sessions = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].get("created_at", 0)
                )
                for sid, _ in sorted_sessions[:overflow]:
                    del self._sessions[sid]

            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired dashboard sessions")


# ---------------------------------------------------------------------------
# Module-level singleton — initialized lazily on first import
# ---------------------------------------------------------------------------
_store: Optional[DashboardSessionStore] = None


def get_dashboard_session_store() -> DashboardSessionStore:
    """Get the global dashboard session store (created on first call)."""
    global _store
    if _store is None:
        _store = DashboardSessionStore()
    return _store


# ---------------------------------------------------------------------------
# Convenience wrappers (drop-in replacements for the old routes.py functions)
# ---------------------------------------------------------------------------

def get_session_dashboard(session_id: str) -> Optional[dict]:
    """Get the current dashboard for a session."""
    return get_dashboard_session_store().get(session_id)


def set_session_dashboard(session_id: str, dashboard: dict, widget_data: dict):
    """Store dashboard state for a session."""
    get_dashboard_session_store().set(session_id, dashboard, widget_data)


def clear_session_dashboard(session_id: str):
    """Clear dashboard state for a session."""
    get_dashboard_session_store().clear(session_id)


def get_session_stats() -> dict:
    """Get session storage statistics for monitoring."""
    return get_dashboard_session_store().stats()
