"""
NLQ Services module.

Provides RAG-based query caching and routing services.
"""

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


def __getattr__(name):
    if name in ('QueryCacheService', 'CacheConfig', 'CacheLookupResult', 'CacheHitType'):
        from .query_cache_service import QueryCacheService, CacheConfig, CacheLookupResult, CacheHitType
        return locals()[name]
    if name in ('NLQQueryRouter', 'QueryMode', 'QueryResult'):
        from .query_router import NLQQueryRouter, QueryMode, QueryResult
        return locals()[name]
    if name in ('RAGLearningLog', 'LearningLogEntry'):
        from .rag_learning_log import RAGLearningLog, LearningLogEntry
        return locals()[name]
    if name == 'LLMCallCounter':
        from .llm_call_counter import LLMCallCounter
        return LLMCallCounter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
