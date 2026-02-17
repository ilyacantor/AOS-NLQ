"""
Tests for DashboardSessionStore (H1 fix).

Validates that the session store extracted from routes.py:
1. Stores and retrieves dashboard sessions correctly
2. Expires sessions after TTL
3. Evicts oldest sessions when over capacity
4. Exposes stats with persistence_available flag
"""

import time
from unittest.mock import patch

import pytest

from src.nlq.api.session import (
    DashboardSessionStore,
    get_session_dashboard,
    set_session_dashboard,
    clear_session_dashboard,
    get_session_stats,
)


class TestDashboardSessionStore:
    """Unit tests for the DashboardSessionStore."""

    def _make_store(self) -> DashboardSessionStore:
        """Create a fresh store with persistence check mocked out."""
        with patch("src.nlq.api.session.get_persistence_service", return_value=None):
            return DashboardSessionStore()

    def test_set_and_get(self):
        store = self._make_store()
        dashboard = {"title": "Revenue Overview", "widgets": []}
        widget_data = {"w1": {"value": 100}}

        store.set("sess_1", dashboard, widget_data)
        result = store.get("sess_1")

        assert result is not None
        assert result["dashboard"] == dashboard
        assert result["widget_data"] == widget_data
        assert "created_at" in result
        assert "last_accessed" in result

    def test_get_nonexistent_returns_none(self):
        store = self._make_store()
        assert store.get("does_not_exist") is None

    def test_clear_removes_session(self):
        store = self._make_store()
        store.set("sess_1", {"title": "test"}, {})
        assert store.get("sess_1") is not None

        store.clear("sess_1")
        assert store.get("sess_1") is None

    def test_clear_nonexistent_does_not_raise(self):
        store = self._make_store()
        store.clear("does_not_exist")  # Should not raise

    def test_stats_reflect_session_count(self):
        store = self._make_store()
        stats = store.stats()
        assert stats["total_sessions"] == 0
        assert stats["persistence_available"] is False

        store.set("sess_1", {}, {})
        store.set("sess_2", {}, {})
        stats = store.stats()
        assert stats["total_sessions"] == 2

    def test_ttl_expiration(self):
        store = self._make_store()
        store.set("sess_1", {"title": "old"}, {})

        # Simulate time passing beyond TTL
        with patch("src.nlq.api.session.SESSION_TTL_SECONDS", 0):
            # Force cleanup by setting last cleanup time to 0
            store._last_cleanup_time = 0
            result = store.get("sess_1")

        # After TTL expiration and cleanup, session should be gone
        assert result is None

    def test_capacity_eviction(self):
        store = self._make_store()

        # Override MAX_SESSIONS to a small number for testing
        with patch("src.nlq.api.session.MAX_SESSIONS", 2):
            store.set("old", {"title": "oldest"}, {})
            time.sleep(0.01)
            store.set("mid", {"title": "middle"}, {})
            time.sleep(0.01)
            store.set("new", {"title": "newest"}, {})

            # Force cleanup
            store._last_cleanup_time = 0
            store._cleanup_if_due()

        stats = store.stats()
        assert stats["total_sessions"] <= 2
        # Newest should survive, oldest should be evicted
        assert store.get("new") is not None

    def test_get_updates_last_accessed(self):
        store = self._make_store()
        store.set("sess_1", {}, {})

        first_access = store.get("sess_1")["last_accessed"]
        time.sleep(0.01)
        second_access = store.get("sess_1")["last_accessed"]

        assert second_access > first_access


class TestConvenienceWrappers:
    """Test the module-level convenience functions (backward compat with routes.py)."""

    def test_set_get_clear_cycle(self):
        """Verify the drop-in replacement functions work end-to-end."""
        session_id = f"test_{time.time()}"
        dashboard = {"title": "Test Dashboard"}
        widget_data = {"w1": {"value": 42}}

        set_session_dashboard(session_id, dashboard, widget_data)

        result = get_session_dashboard(session_id)
        assert result is not None
        assert result["dashboard"]["title"] == "Test Dashboard"
        assert result["widget_data"]["w1"]["value"] == 42

        clear_session_dashboard(session_id)
        assert get_session_dashboard(session_id) is None

    def test_stats_returns_dict(self):
        stats = get_session_stats()
        assert isinstance(stats, dict)
        assert "total_sessions" in stats
        assert "max_sessions" in stats
        assert "ttl_seconds" in stats
        assert "persistence_available" in stats
