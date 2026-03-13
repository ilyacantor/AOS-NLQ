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
