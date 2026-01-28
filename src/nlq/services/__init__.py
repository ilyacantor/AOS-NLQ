"""
NLQ Services module.

Provides RAG-based query caching and routing services.
"""

from .query_cache_service import (
    QueryCacheService,
    CacheConfig,
    CacheLookupResult,
    CacheHitType,
)
from .query_router import (
    NLQQueryRouter,
    QueryMode,
    QueryResult,
)
from .rag_learning_log import (
    RAGLearningLog,
    LearningLogEntry,
)
from .llm_call_counter import (
    LLMCallCounter,
)

__all__ = [
    'QueryCacheService',
    'CacheConfig',
    'CacheLookupResult',
    'CacheHitType',
    'NLQQueryRouter',
    'QueryMode',
    'QueryResult',
    'RAGLearningLog',
    'LearningLogEntry',
    'LLMCallCounter',
]
