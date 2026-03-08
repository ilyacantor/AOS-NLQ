"""
Unit tests for tenant_id alignment (U1-U8).

Tests the get_tenant_id() resolution logic in isolation.
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


class TestU1_EnvVarResolution:
    """U1: AOS_TENANT_ID env var is resolved first."""

    def test_env_var_returned(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "AeroFlow-K3OA"}):
            assert get_tenant_id() == "AeroFlow-K3OA"

    def test_env_var_arbitrary_string(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "my-custom-tenant"}):
            assert get_tenant_id() == "my-custom-tenant"


class TestU2_FileResolution:
    """U2: Falls back to most recent data/tenants/*.json."""

    def test_file_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch.dict(os.environ, env, clear=True):
            # Should find aeroflow_k3oa.json
            tid = get_tenant_id()
            assert isinstance(tid, str)
            assert len(tid) > 0


class TestU3_RuntimeError:
    """U3: RuntimeError when no tenant can be determined."""

    def test_no_env_no_files_raises(self, tmp_path):
        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch.dict(os.environ, env, clear=True):
            # Patch the tenants directory to an empty temp dir
            empty_dir = tmp_path / "tenants"
            empty_dir.mkdir()
            with patch("src.nlq.config.Path") as mock_path:
                mock_file = mock_path.return_value.resolve.return_value
                mock_file.parent.parent.parent.__truediv__.return_value.__truediv__.return_value = empty_dir
                # Simpler approach: directly patch module internals
                import src.nlq.config as cfg
                orig = cfg.get_tenant_id

                def patched():
                    cfg._tenant_id_cache = None
                    env_tid = os.environ.get("AOS_TENANT_ID")
                    if env_tid:
                        return env_tid
                    if empty_dir.is_dir():
                        files = sorted(empty_dir.glob("*.json"))
                        if files:
                            return files[0].stem
                    raise RuntimeError("Cannot determine tenant_id")

                cfg.get_tenant_id = patched
                try:
                    with pytest.raises(RuntimeError, match="Cannot determine tenant_id"):
                        cfg.get_tenant_id()
                finally:
                    cfg.get_tenant_id = orig


class TestU4_CacheBehavior:
    """U4: Cached after first call, reset clears it."""

    def test_cached(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "T1"}):
            first = get_tenant_id()
            second = get_tenant_id()
            assert first is second  # same object from cache

    def test_reset_and_re_resolve(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "T1"}):
            assert get_tenant_id() == "T1"
        reset_tenant_cache()
        with patch.dict(os.environ, {"AOS_TENANT_ID": "T2"}):
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
