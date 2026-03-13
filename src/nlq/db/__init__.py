"""
Database persistence module for AOS-NLQ RAG.

Provides multi-tenant Supabase PostgreSQL integration with RLS.
"""

from .supabase_persistence import (
    SupabasePersistenceService,
    SessionRecord,
    CacheEntryRecord,
    LearningLogRecord,
    get_persistence_service,
    init_persistence_service,
)
from src.nlq.config import get_tenant_id

__all__ = [
    "SupabasePersistenceService",
    "SessionRecord",
    "CacheEntryRecord",
    "LearningLogRecord",
    "get_persistence_service",
    "init_persistence_service",
    "get_tenant_id",
]
