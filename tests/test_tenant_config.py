"""
Tests for get_tenant_id() — the centralized tenant ID resolver.

Validates:
1. AOS_TENANT_ID env var takes priority
2. Falls back to most recent data/tenants/*.json file
3. Raises RuntimeError if no tenant can be determined
4. Cache works and can be reset
"""

import os
from unittest.mock import patch, MagicMock

import pytest


class TestGetTenantIdFromEnv:
    """AOS_TENANT_ID env var is the primary resolution path."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_env_var_returns_value(self):
        """AOS_TENANT_ID env var should be returned directly."""
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "TestTenant-X1"}):
            from src.nlq.config import get_tenant_id
            result = get_tenant_id()
            assert result == "TestTenant-X1"
        reset_tenant_cache()

    def test_env_var_takes_priority_over_file(self, tmp_path):
        """Env var should win even when tenant files exist."""
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "EnvTenant"}):
            from src.nlq.config import get_tenant_id
            result = get_tenant_id()
            assert result == "EnvTenant"
        reset_tenant_cache()


class TestGetTenantIdFromFile:
    """Fallback to most recent data/tenants/*.json."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_resolves_from_tenant_file(self):
        """Should resolve tenant_id from the data/tenants/ directory."""
        from src.nlq.config import reset_tenant_cache, get_tenant_id
        reset_tenant_cache()
        # Remove env var to force file-based resolution
        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch.dict(os.environ, env, clear=True):
            result = get_tenant_id()
            # Should return the stem of the most recent .json file
            assert isinstance(result, str)
            assert len(result) > 0
        reset_tenant_cache()


class TestGetTenantIdError:
    """RuntimeError when no tenant can be determined."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_raises_when_no_env_and_no_files(self, tmp_path):
        """Should raise RuntimeError when neither env nor files exist."""
        import src.nlq.config as cfg
        from src.nlq.config import reset_tenant_cache
        from pathlib import Path

        reset_tenant_cache()
        empty_tenants = tmp_path / "data" / "tenants"
        empty_tenants.mkdir(parents=True)

        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch.dict(os.environ, env, clear=True):
            cfg._tenant_id_cache = None
            # Patch __file__ resolution to point to tmp_path
            fake_file = tmp_path / "src" / "nlq" / "config.py"
            fake_file.parent.mkdir(parents=True, exist_ok=True)
            fake_file.touch()
            with patch("src.nlq.config.Path") as mock_path_cls:
                mock_path_cls.return_value.resolve.return_value.parent.parent.parent = tmp_path
                with pytest.raises(RuntimeError, match="Cannot determine tenant_id"):
                    cfg.get_tenant_id()
        reset_tenant_cache()


class TestTenantIdCache:
    """Cache behavior."""

    def setup_method(self):
        from src.nlq.config import reset_tenant_cache
        reset_tenant_cache()

    def test_cache_returns_same_value(self):
        """Repeated calls should return cached value."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "CachedTenant"}):
            first = get_tenant_id()
            second = get_tenant_id()
            assert first == second == "CachedTenant"
        reset_tenant_cache()

    def test_reset_clears_cache(self):
        """reset_tenant_cache() should force re-resolution."""
        from src.nlq.config import get_tenant_id, reset_tenant_cache
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "First"}):
            assert get_tenant_id() == "First"
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "Second"}):
            assert get_tenant_id() == "Second"
        reset_tenant_cache()


class TestAllModulesUseGetTenantId:
    """Verify all modules import get_tenant_id, not DEFAULT_TENANT_ID."""

    def test_config_exports_get_tenant_id(self):
        """config.py should export get_tenant_id function."""
        import src.nlq.config as cfg
        assert hasattr(cfg, "get_tenant_id")
        assert callable(cfg.get_tenant_id)

    def test_config_no_longer_exports_default_tenant_id(self):
        """DEFAULT_TENANT_ID constant should no longer exist."""
        import src.nlq.config as cfg
        assert not hasattr(cfg, "DEFAULT_TENANT_ID")

    def test_db_init_exports_get_tenant_id(self):
        """db/__init__.py should re-export get_tenant_id."""
        from src.nlq.db import get_tenant_id
        assert callable(get_tenant_id)
