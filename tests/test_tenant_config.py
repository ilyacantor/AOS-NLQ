"""
Tests for get_tenant_id() — NLQ mirrors DCL's current entity.

Validates the resolution contract (dcl mirrors, not an env pin):
1. DCL's most-recent run (config._current_tenant_from_dcl) is the PRIMARY source
2. AOS_TENANT_ID is a FALLBACK only, used when DCL is unreachable
3. Raises RuntimeError when neither resolves
4. TTL cache works and can be reset
"""

import os
from unittest.mock import patch

import pytest


class TestFollowsDcl:
    """DCL's current run is the primary resolution path."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_dcl_current_run_returned(self):
        """get_tenant_id returns DCL's most-recent-run tenant."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="DclTenant-A1"):
            assert get_tenant_id() == "DclTenant-A1"
        reset_tenant_cache()

    def test_dcl_wins_over_env_var(self):
        """DCL is primary — it wins even when AOS_TENANT_ID is set (no longer a pin)."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="DclTenant"), \
             patch.dict(os.environ, {"AOS_TENANT_ID": "EnvTenant"}):
            assert get_tenant_id() == "DclTenant"
        reset_tenant_cache()


class TestEnvFallback:
    """AOS_TENANT_ID is used only when DCL is unreachable."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_env_var_fallback_when_dcl_unreachable(self):
        """DCL returns None (unreachable) → fall back to AOS_TENANT_ID."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value=None), \
             patch.dict(os.environ, {"AOS_TENANT_ID": "FallbackTenant"}):
            assert get_tenant_id() == "FallbackTenant"
        reset_tenant_cache()


class TestGetTenantIdError:
    """RuntimeError when neither DCL nor env resolves — no silent fallback."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_raises_when_no_dcl_and_no_env(self):
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch("src.nlq.config._current_tenant_from_dcl", return_value=None), \
             patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="Cannot determine tenant_id"):
                get_tenant_id()
        reset_tenant_cache()


class TestTenantIdCache:
    """TTL cache behavior — follows DCL but does not hit it on every call."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_cache_returns_same_value_within_ttl(self):
        """Repeated calls within the TTL return the cached DCL tenant (one DCL hit)."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="T1") as m:
            first = get_tenant_id()
            second = get_tenant_id()
            assert first == second == "T1"
            assert m.call_count == 1  # second served from the TTL cache
        reset_tenant_cache()

    def test_reset_clears_cache(self):
        """reset_tenant_cache() forces re-resolution from DCL."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="First"):
            assert get_tenant_id() == "First"
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="Second"):
            assert get_tenant_id() == "Second"
        reset_tenant_cache()


class TestAllModulesUseGetTenantId:
    """Verify all modules import get_tenant_id, not DEFAULT_TENANT_ID."""

    def test_config_exports_get_tenant_id(self):
        import src.nlq.config as cfg
        assert hasattr(cfg, "get_tenant_id")
        assert callable(cfg.get_tenant_id)

    def test_config_no_longer_exports_default_tenant_id(self):
        import src.nlq.config as cfg
        assert not hasattr(cfg, "DEFAULT_TENANT_ID")

    def test_db_init_exports_get_tenant_id(self):
        from src.nlq.db import get_tenant_id
        assert callable(get_tenant_id)
