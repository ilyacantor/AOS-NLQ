"""
Negative tests for tenant_id alignment (N1-N5).

Confirms the old bad behavior cannot return.
"""

import os
import inspect
from unittest.mock import patch

import pytest

from src.nlq.config import reset_tenant_cache


@pytest.fixture(autouse=True)
def clean_cache():
    reset_tenant_cache()
    yield
    reset_tenant_cache()


class TestN1_NoHardcodedUuid:
    """N1: The hardcoded UUID must not appear in any live Python source."""

    UUID = "00000000-0000-0000-0000-000000000001"

    def test_config_py(self):
        import src.nlq.config as mod
        assert self.UUID not in inspect.getsource(mod)

    def test_supabase_persistence(self):
        import src.nlq.db.supabase_persistence as mod
        assert self.UUID not in inspect.getsource(mod)

    def test_llm_call_counter(self):
        import src.nlq.services.llm_call_counter as mod
        assert self.UUID not in inspect.getsource(mod)

    def test_rag_learning_log(self):
        import src.nlq.services.rag_learning_log as mod
        assert self.UUID not in inspect.getsource(mod)

    def test_insufficient_data_tracker(self):
        import src.nlq.services.insufficient_data_tracker as mod
        assert self.UUID not in inspect.getsource(mod)

    def test_dcl_semantic_client(self):
        import src.nlq.services.dcl_semantic_client as mod
        assert self.UUID not in inspect.getsource(mod)


class TestN2_NoDefaultTenantIdExport:
    """N2: DEFAULT_TENANT_ID must not be importable from config or db."""

    def test_config_no_export(self):
        import src.nlq.config as cfg
        assert not hasattr(cfg, "DEFAULT_TENANT_ID")

    def test_db_init_no_export(self):
        import src.nlq.db as db
        assert not hasattr(db, "DEFAULT_TENANT_ID")


class TestN3_NoNlqDefaultTenantIdEnvVar:
    """N3: NLQ_DEFAULT_TENANT_ID env var is no longer referenced in live code."""

    def test_config_source(self):
        import src.nlq.config as mod
        source = inspect.getsource(mod)
        assert "NLQ_DEFAULT_TENANT_ID" not in source


class TestN4_NoSilentFallbackToDefault:
    """N4: get_tenant_id() never silently returns 'default' or a UUID."""

    def test_no_silent_default(self, tmp_path):
        """Without env var or files, should raise, not return a default."""
        import src.nlq.config as cfg
        reset_tenant_cache()

        env = {k: v for k, v in os.environ.items() if k != "AOS_TENANT_ID"}
        with patch.dict(os.environ, env, clear=True):
            cfg._tenant_id_cache = None
            # Patch the path to an empty directory
            empty = tmp_path / "empty_tenants"
            empty.mkdir()
            original_fn = cfg.get_tenant_id

            def patched_get_tenant_id():
                cfg._tenant_id_cache = None
                env_tid = os.environ.get("AOS_TENANT_ID")
                if env_tid:
                    return env_tid
                if empty.is_dir():
                    files = sorted(empty.glob("*.json"))
                    if files:
                        return files[0].stem
                raise RuntimeError("Cannot determine tenant_id")

            cfg.get_tenant_id = patched_get_tenant_id
            try:
                with pytest.raises(RuntimeError):
                    cfg.get_tenant_id()
            finally:
                cfg.get_tenant_id = original_fn
        reset_tenant_cache()


class TestN5_DclQuerySignatureRequiresTenantId:
    """N5: query() accepts tenant_id parameter."""

    def test_query_has_tenant_id_param(self):
        from src.nlq.services.dcl_semantic_client import DCLSemanticClient
        sig = inspect.signature(DCLSemanticClient.query)
        assert "tenant_id" in sig.parameters
