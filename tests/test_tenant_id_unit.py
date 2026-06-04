"""
Unit tests for tenant_id alignment (U1-U8).

Tests the get_tenant_id() resolution logic in isolation. NLQ mirrors DCL:
the active tenant is DCL's most-recent run (config._current_tenant_from_dcl),
with AOS_TENANT_ID only as a fallback when DCL is unreachable.
"""

import os
from unittest.mock import patch

import pytest

from src.nlq.config import get_tenant_id, reset_tenant_cache


@pytest.fixture(autouse=True)
def clean_cache():
    """Reset tenant cache before and after every test."""
    reset_tenant_cache()
    yield
    reset_tenant_cache()


class TestU1_DclResolution:
    """U1: the active tenant is DCL's current run (primary path)."""

    def test_dcl_current_returned(self):
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="AeroFlow-K3OA"):
            assert get_tenant_id() == "AeroFlow-K3OA"

    def test_dcl_wins_over_env(self):
        """DCL is primary — AOS_TENANT_ID no longer pins."""
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="DclWins"), \
             patch.dict(os.environ, {"AOS_TENANT_ID": "EnvLoses"}):
            assert get_tenant_id() == "DclWins"


class TestU2_EnvFallback:
    """U2: AOS_TENANT_ID is the fallback when DCL is unreachable."""

    def test_env_fallback_when_dcl_down(self):
        with patch("src.nlq.config._current_tenant_from_dcl", return_value=None), \
             patch.dict(os.environ, {"AOS_TENANT_ID": "FallbackTenant"}):
            assert get_tenant_id() == "FallbackTenant"


class TestU3_RuntimeError:
    """U3: RuntimeError when neither DCL nor env resolves."""

    def test_no_dcl_no_env_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch("src.nlq.config._current_tenant_from_dcl", return_value=None), \
             patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="Cannot determine tenant_id"):
                get_tenant_id()


class TestU4_CacheBehavior:
    """U4: TTL cache — follows DCL, served from cache within the window."""

    def test_cached_within_ttl(self):
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="T1") as m:
            first = get_tenant_id()
            second = get_tenant_id()
            assert first == second == "T1"
            assert m.call_count == 1  # second served from the TTL cache

    def test_reset_and_re_resolve(self):
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="T1"):
            assert get_tenant_id() == "T1"
        reset_tenant_cache()
        with patch("src.nlq.config._current_tenant_from_dcl", return_value="T2"):
            assert get_tenant_id() == "T2"


class TestU5_NoDefaultTenantIdConstant:
    """U5: DEFAULT_TENANT_ID constant no longer exists in config."""

    def test_no_constant(self):
        import src.nlq.config as cfg
        assert not hasattr(cfg, "DEFAULT_TENANT_ID")


class TestU6_NoUuidInConfig:
    """U6: The hardcoded UUID is gone from config.py."""

    def test_no_uuid_in_source(self):
        import src.nlq.config as cfg
        import inspect
        source = inspect.getsource(cfg)
        assert "00000000-0000-0000-0000-000000000001" not in source


class TestU7_SettingsNoTenantField:
    """U7: Settings class no longer has default_tenant_id field."""

    def test_no_field(self):
        from src.nlq.config import Settings
        assert "default_tenant_id" not in Settings.model_fields


class TestU8_ServiceModulesImportGetTenantId:
    """U8: All service modules import get_tenant_id, not DEFAULT_TENANT_ID."""

    def test_supabase_persistence(self):
        import inspect
        import src.nlq.db.supabase_persistence as mod
        source = inspect.getsource(mod)
        assert "from src.nlq.config import get_tenant_id" in source
        assert "DEFAULT_TENANT_ID" not in source

    def test_llm_call_counter(self):
        import inspect
        import src.nlq.services.llm_call_counter as mod
        source = inspect.getsource(mod)
        assert "from src.nlq.config import get_tenant_id" in source
        assert "DEFAULT_TENANT_ID" not in source

    def test_rag_learning_log(self):
        import inspect
        import src.nlq.services.rag_learning_log as mod
        source = inspect.getsource(mod)
        assert "from src.nlq.config import get_tenant_id" in source
        assert "DEFAULT_TENANT_ID" not in source

    def test_insufficient_data_tracker(self):
        import inspect
        import src.nlq.services.insufficient_data_tracker as mod
        source = inspect.getsource(mod)
        assert "from src.nlq.config import get_tenant_id" in source
        assert "DEFAULT_TENANT_ID" not in source
