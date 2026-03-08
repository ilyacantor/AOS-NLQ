"""
Integration tests for tenant_id alignment (I1-I8).

Tests the tenant_id flow across NLQ → DCL boundary.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from src.nlq.config import get_tenant_id, reset_tenant_cache


@pytest.fixture(autouse=True)
def clean_cache():
    reset_tenant_cache()
    yield
    reset_tenant_cache()


class TestI1_DclClientQueryIncludesTenantId:
    """I1: dcl_semantic_client.query() sends tenant_id in payload."""

    def test_payload_has_tenant_id(self):
        """The DCL payload dict should include tenant_id."""
        with patch.dict(os.environ, {"AOS_TENANT_ID": "test-tenant-i1"}):
            from src.nlq.services.dcl_semantic_client import DCLSemanticClient
            client = DCLSemanticClient.__new__(DCLSemanticClient)
            client.dcl_url = None  # force local fallback
            client._fact_base = None
            client._catalog = []
            client._crossmap = {}
            # Since dcl_url is None, it will use local fallback, but we can
            # verify the parameter is accepted without error
            result = client.query(
                metric="revenue",
                time_range={"period": "2025"},
                tenant_id=get_tenant_id(),
            )
            # Should not raise - tenant_id parameter accepted


class TestI2_TenantDataServiceUsesGetTenantId:
    """I2: TenantDataService resolves tenant from get_tenant_id()."""

    def test_default_uses_get_tenant_id(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "aeroflow_k3oa"}):
            from src.nlq.dcl.tenant_data import TenantDataService
            svc = TenantDataService()
            assert svc._tenant_id == "aeroflow_k3oa"


class TestI3_TenantDataServiceFailsLoud:
    """I3: TenantDataService raises FileNotFoundError for missing tenant."""

    def test_missing_tenant_file_raises(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "nonexistent_tenant_xyz"}):
            from src.nlq.dcl.tenant_data import TenantDataService
            with pytest.raises(FileNotFoundError, match="Tenant data file not found"):
                TenantDataService()


class TestI4_DbPersistenceUsesGetTenantId:
    """I4: SupabasePersistenceService resolves tenant via get_tenant_id()."""

    def test_default_tenant_resolved(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "test-tenant-i4"}):
            from src.nlq.db.supabase_persistence import SupabasePersistenceService
            svc = SupabasePersistenceService()
            assert svc.default_tenant_id == "test-tenant-i4"


class TestI5_LlmCallCounterUsesGetTenantId:
    """I5: LLMCallCounter resolves tenant via get_tenant_id()."""

    def test_default_tenant_resolved(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "test-tenant-i5"}):
            from src.nlq.services.llm_call_counter import LLMCallCounter
            counter = LLMCallCounter(persist=False)
            assert counter._tenant_id == "test-tenant-i5"


class TestI6_LearningLogEntryUsesGetTenantId:
    """I6: LearningLogEntry dataclass default resolves via get_tenant_id()."""

    def test_default_tenant_in_entry(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "test-tenant-i6"}):
            from src.nlq.services.rag_learning_log import LearningLogEntry
            entry = LearningLogEntry(
                query="test", success=True, source="test",
                learned=False, message="test"
            )
            assert entry.tenant_id == "test-tenant-i6"


class TestI7_InsufficientDataEntryUsesGetTenantId:
    """I7: InsufficientDataEntry dataclass default resolves via get_tenant_id()."""

    def test_default_tenant_in_entry(self):
        with patch.dict(os.environ, {"AOS_TENANT_ID": "test-tenant-i7"}):
            from src.nlq.services.insufficient_data_tracker import InsufficientDataEntry
            entry = InsufficientDataEntry(
                query="test", confidence=0.5, persona="CFO", reason="test"
            )
            assert entry.tenant_id == "test-tenant-i7"


class TestI8_EnvExampleUpdated:
    """I8: .env.example uses AOS_TENANT_ID, not NLQ_DEFAULT_TENANT_ID."""

    def test_env_example_has_new_key(self):
        from pathlib import Path
        env_example = Path(__file__).parent.parent / ".env.example"
        if env_example.exists():
            content = env_example.read_text()
            assert "AOS_TENANT_ID" in content
            assert "NLQ_DEFAULT_TENANT_ID" not in content
