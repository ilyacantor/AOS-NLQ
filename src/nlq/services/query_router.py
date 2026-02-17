"""
NLQ Query Router

Routes queries through cache and/or LLM based on mode and cache hits.
Implements the Static/AI mode toggle functionality.
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime

from .query_cache_service import (
    QueryCacheService,
    CacheLookupResult,
    CacheHitType,
)
from .rag_learning_log import RAGLearningLog, LearningLogEntry
from .llm_call_counter import LLMCallCounter

logger = logging.getLogger(__name__)


class QueryMode(Enum):
    """Operating mode for query processing."""
    STATIC = "static"  # Cache-only, fast, deterministic
    AI = "ai"          # Cache + LLM fallback, learns


@dataclass
class QueryResult:
    """Result of processing a query through the router."""
    success: bool
    source: str              # "cache", "llm", "bypass", "error"
    data: Optional[Any]      # The actual answer/data
    parsed: Optional[Dict]   # The parsed query structure
    confidence: float        # Overall confidence (0.0-1.0)
    similarity: float        # Cache similarity (0.0-1.0 or 0 if not from cache)
    cached: bool             # Whether this result was cached
    message: Optional[str]   # Human-readable message
    metadata: Dict = field(default_factory=dict)  # Additional metadata
    learned: bool = False    # Whether this query was learned (stored in cache)


class NLQQueryRouter:
    """
    Routes NLQ queries through the cache and LLM layers.

    Supports two modes:
    - STATIC: Cache-only, returns quickly, fails if no cache hit
    - AI: Cache first, LLM fallback, learns new patterns
    """

    def __init__(
        self,
        cache_service: Optional[QueryCacheService] = None,
        llm_parser: Optional[Callable] = None,
        data_executor: Optional[Callable] = None,
        bypass_checker: Optional[Callable] = None,
        learning_log: Optional[RAGLearningLog] = None,
        call_counter: Optional[LLMCallCounter] = None,
    ):
        """
        Initialize the query router.

        Args:
            cache_service: RAG cache service for query lookup/storage
            llm_parser: Async function to parse query with LLM (query, context) -> parsed_dict
            data_executor: Function to execute parsed query -> data
            bypass_checker: Function to check for bypass conditions (greetings, easter eggs)
            learning_log: Service to log RAG learning events
            call_counter: Service to track LLM API calls
        """
        self.cache = cache_service
        self.llm_parser = llm_parser
        self.data_executor = data_executor
        self.bypass_checker = bypass_checker
        self.learning_log = learning_log
        self.call_counter = call_counter

    async def process(
        self,
        query: str,
        mode: QueryMode = QueryMode.AI,
        persona: str = "CFO",
        session_id: str = None,
    ) -> QueryResult:
        """
        Process a natural language query.

        Args:
            query: The user's natural language query
            mode: STATIC (cache only) or AI (cache + LLM)
            persona: The persona context (CFO, CRO, etc.)
            session_id: Optional session ID for tracking

        Returns:
            QueryResult with data, confidence, and metadata
        """

        # =====================================================================
        # Step 1: Check Bypasses (greetings, easter eggs, etc.)
        # =====================================================================
        if self.bypass_checker:
            bypass_response = self.bypass_checker(query)
            if bypass_response:
                logger.debug(f"Query bypassed: {query[:30]}...")
                return QueryResult(
                    success=True,
                    source="bypass",
                    data=bypass_response,
                    parsed=None,
                    confidence=1.0,
                    similarity=0.0,
                    cached=False,
                    message=None,
                    metadata={"bypass_type": bypass_response.get("type", "unknown")}
                )

        # =====================================================================
        # Step 2: Cache Lookup
        # =====================================================================
        cache_result = None
        if self.cache and self.cache.is_available:
            cache_result = self.cache.lookup(query, persona=persona)
        else:
            # Create a miss result if no cache available
            cache_result = CacheLookupResult(
                hit_type=CacheHitType.MISS,
                similarity=0.0,
                parsed=None,
                original_query=None,
                cache_id=None,
                confidence=0.0
            )

        # =====================================================================
        # Step 3: Route Based on Mode and Cache Result
        # =====================================================================

        if mode == QueryMode.STATIC:
            result = await self._process_static(query, cache_result, persona)
        else:
            result = await self._process_ai(query, cache_result, persona, session_id)

        return result

    async def _process_static(
        self,
        query: str,
        cache_result: CacheLookupResult,
        persona: str
    ) -> QueryResult:
        """
        Process query in STATIC mode (cache only).
        """

        # High confidence hit - use it
        if cache_result.high_confidence:
            try:
                data = None
                if self.data_executor and cache_result.parsed:
                    data = self.data_executor(cache_result.parsed)

                # Log successful cache hit
                if self.learning_log:
                    await self.learning_log.log_entry(LearningLogEntry(
                        query=query,
                        success=True,
                        source="cache",
                        learned=False,
                        message=f"Retrieved from cache (similarity: {cache_result.similarity:.0%})",
                        persona=persona,
                        similarity=cache_result.similarity,
                    ))

                return QueryResult(
                    success=True,
                    source="cache",
                    data=data,
                    parsed=cache_result.parsed,
                    confidence=cache_result.confidence,
                    similarity=cache_result.similarity,
                    cached=True,
                    message=None,
                    metadata={
                        "cache_id": cache_result.cache_id,
                        "hit_type": cache_result.hit_type.value,
                        "original_cached_query": cache_result.original_query
                    }
                )
            except (RuntimeError, KeyError, TypeError, ValueError) as e:
                logger.error(f"Data execution error: {e}")
                return QueryResult(
                    success=False,
                    source="error",
                    data=None,
                    parsed=cache_result.parsed,
                    confidence=0.0,
                    similarity=cache_result.similarity,
                    cached=True,
                    message=f"Error executing cached query: {str(e)}",
                    metadata={"error": str(e)}
                )

        # Partial hit - suggest AI mode
        if cache_result.hit_type == CacheHitType.PARTIAL:
            if self.learning_log:
                await self.learning_log.log_entry(LearningLogEntry(
                    query=query,
                    success=False,
                    source="cache",
                    learned=False,
                    message=f"Partial match ({cache_result.similarity:.0%}) - switch to AI mode",
                    persona=persona,
                    similarity=cache_result.similarity,
                ))

            return QueryResult(
                success=False,
                source="cache",
                data=None,
                parsed=None,
                confidence=0.0,
                similarity=cache_result.similarity,
                cached=False,
                message=(
                    f"Found similar query ({cache_result.similarity:.0%} match) but not confident enough. "
                    "Switch to AI mode to process this query."
                ),
                metadata={
                    "similar_query": cache_result.original_query,
                    "suggestion": "Try AI mode"
                }
            )

        # No hit - fail gracefully
        if self.learning_log:
            await self.learning_log.log_entry(LearningLogEntry(
                query=query,
                success=False,
                source="cache",
                learned=False,
                message="Not found in cache - switch to AI mode",
                persona=persona,
                similarity=0.0,
            ))

        return QueryResult(
            success=False,
            source="cache",
            data=None,
            parsed=None,
            confidence=0.0,
            similarity=cache_result.similarity,
            cached=False,
            message=(
                "This query hasn't been seen before. "
                "Switch to AI mode to process new questions."
            ),
            metadata={"suggestion": "Try AI mode"}
        )

    async def _process_ai(
        self,
        query: str,
        cache_result: CacheLookupResult,
        persona: str,
        session_id: str = None,
    ) -> QueryResult:
        """
        Process query in AI mode (cache + LLM fallback + learning).
        """

        # Exact/High hit - use cache, skip LLM
        if cache_result.hit_type == CacheHitType.EXACT:
            try:
                data = None
                if self.data_executor and cache_result.parsed:
                    data = self.data_executor(cache_result.parsed)

                if self.learning_log:
                    await self.learning_log.log_entry(LearningLogEntry(
                        query=query,
                        success=True,
                        source="cache",
                        learned=False,
                        message=f"Exact match found (similarity: {cache_result.similarity:.0%})",
                        persona=persona,
                        similarity=cache_result.similarity,
                    ))

                return QueryResult(
                    success=True,
                    source="cache",
                    data=data,
                    parsed=cache_result.parsed,
                    confidence=cache_result.confidence,
                    similarity=cache_result.similarity,
                    cached=True,
                    message=None,
                    metadata={
                        "cache_id": cache_result.cache_id,
                        "hit_type": cache_result.hit_type.value,
                        "llm_skipped": True
                    }
                )
            except (RuntimeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"Cached query execution failed, falling back to LLM: {e}")
                # Fall through to LLM

        # High hit - use cache
        if cache_result.hit_type == CacheHitType.HIGH:
            try:
                data = None
                if self.data_executor and cache_result.parsed:
                    data = self.data_executor(cache_result.parsed)

                if self.learning_log:
                    await self.learning_log.log_entry(LearningLogEntry(
                        query=query,
                        success=True,
                        source="cache",
                        learned=False,
                        message=f"High confidence match (similarity: {cache_result.similarity:.0%})",
                        persona=persona,
                        similarity=cache_result.similarity,
                    ))

                return QueryResult(
                    success=True,
                    source="cache",
                    data=data,
                    parsed=cache_result.parsed,
                    confidence=cache_result.confidence,
                    similarity=cache_result.similarity,
                    cached=True,
                    message=None,
                    metadata={
                        "cache_id": cache_result.cache_id,
                        "hit_type": cache_result.hit_type.value,
                        "llm_skipped": True
                    }
                )
            except (RuntimeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"Cached query execution failed, falling back to LLM: {e}")

        # Partial hit or miss - call LLM
        if not self.llm_parser:
            return QueryResult(
                success=False,
                source="error",
                data=None,
                parsed=None,
                confidence=0.0,
                similarity=0.0,
                cached=False,
                message="LLM parser not configured",
                metadata={"error": "no_llm_parser"}
            )

        try:
            # Increment LLM call counter
            if self.call_counter:
                self.call_counter.increment(session_id)

            # Build context from partial cache hit
            context = None
            if cache_result.hit_type == CacheHitType.PARTIAL:
                context = {
                    "similar_query": cache_result.original_query,
                    "similar_parse": cache_result.parsed
                }

            # Parse with LLM
            parsed = await self.llm_parser(query, context=context)

            # Execute query
            data = None
            if self.data_executor:
                data = self.data_executor(parsed)

            # Calculate confidence
            llm_confidence = parsed.get("confidence", 0.9)

            # Learn: store successful parse
            learned = False
            if llm_confidence >= 0.8 and self.cache and self.cache.is_available:
                cache_id = self.cache.store(
                    query=query,
                    parsed=parsed,
                    persona=persona,
                    confidence=llm_confidence,
                    source="llm"
                )
                learned = cache_id is not None

            # Log the learning event
            if self.learning_log:
                await self.learning_log.log_entry(LearningLogEntry(
                    query=query,
                    success=True,
                    source="llm",
                    learned=learned,
                    message=f"Processed with AI{' and learned' if learned else ''}",
                    persona=persona,
                    similarity=cache_result.similarity if cache_result.hit_type == CacheHitType.PARTIAL else 0.0,
                    llm_confidence=llm_confidence,
                ))

            return QueryResult(
                success=True,
                source="llm",
                data=data,
                parsed=parsed,
                confidence=llm_confidence,
                similarity=0.0,
                cached=False,
                message=None,
                learned=learned,
                metadata={
                    "learned": learned,
                    "had_context": context is not None,
                    "llm_call": True,
                }
            )

        except (RuntimeError, KeyError, TypeError, ValueError, OSError) as e:
            logger.error(f"LLM processing error: {e}")

            if self.learning_log:
                await self.learning_log.log_entry(LearningLogEntry(
                    query=query,
                    success=False,
                    source="llm",
                    learned=False,
                    message=f"AI processing failed: {str(e)}",
                    persona=persona,
                ))

            return QueryResult(
                success=False,
                source="error",
                data=None,
                parsed=None,
                confidence=0.0,
                similarity=0.0,
                cached=False,
                message=f"Failed to process query: {str(e)}",
                metadata={"error": str(e)}
            )
