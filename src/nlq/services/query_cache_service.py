"""
Query Cache Service for AOS-NLQ

Implements RAG-based caching of parsed NLQ queries using Pinecone.
Supports Static (read-only) and AI (read+write) modes.

Usage:
    cache = QueryCacheService(config)

    # Lookup
    result = cache.lookup("What was revenue last quarter?")
    if result.hit:
        use(result.parsed)

    # Store (AI mode learning)
    cache.store(query="...", parsed={...}, confidence=0.95)
"""

import hashlib
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class CacheHitType(Enum):
    """Classification of cache lookup results."""
    EXACT = "exact"           # Very high similarity (>=0.95)
    HIGH = "high"             # High similarity (>=0.92)
    PARTIAL = "partial"       # Usable as context (>=0.85)
    MISS = "miss"             # No useful match (<0.85)


@dataclass
class CacheLookupResult:
    """Result of a cache lookup."""
    hit_type: CacheHitType
    similarity: float
    parsed: Optional[Dict[str, Any]]
    original_query: Optional[str]
    cache_id: Optional[str]
    confidence: float

    @property
    def hit(self) -> bool:
        """True if cache hit is usable (not MISS)."""
        return self.hit_type != CacheHitType.MISS

    @property
    def high_confidence(self) -> bool:
        """True if hit is high enough to use directly."""
        return self.hit_type in (CacheHitType.EXACT, CacheHitType.HIGH)


@dataclass
class CacheConfig:
    """Configuration for QueryCacheService."""
    pinecone_api_key: str = ""
    pinecone_index: str = "aos-nlq"
    openai_api_key: str = ""
    namespace: str = "nlq-query-cache"

    # Similarity thresholds (lowered for better semantic matching)
    threshold_exact: float = 0.92    # Use directly, no question
    threshold_high: float = 0.85     # Use cached result (semantic match)
    threshold_partial: float = 0.75  # Use as context in AI mode

    # Embedding settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Feature flags
    enabled: bool = True  # Can disable cache entirely


class QueryCacheService:
    """
    RAG-based cache for NLQ parsed queries.

    Stores query embeddings in Pinecone with parsed structure as metadata.
    Supports fast lookup for similar queries to avoid repeated LLM calls.
    """

    def __init__(self, config: CacheConfig):
        self.config = config
        self._pc = None
        self._index = None
        self._openai = None
        self._initialized = False

        if config.enabled and config.pinecone_api_key and config.openai_api_key:
            self._init_clients()

    def _init_clients(self):
        """Lazy initialization of API clients."""
        if self._initialized:
            return

        try:
            from pinecone import Pinecone, ServerlessSpec
            from openai import OpenAI

            self._pc = Pinecone(api_key=self.config.pinecone_api_key)
            
            index_name = self.config.pinecone_index
            existing_indexes = [idx.name for idx in self._pc.list_indexes()]
            
            if index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {index_name}")
                self._pc.create_index(
                    name=index_name,
                    dimension=self.config.embedding_dimensions,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                logger.info(f"Pinecone index '{index_name}' created successfully")
            
            self._index = self._pc.Index(index_name)
            self._openai = OpenAI(api_key=self.config.openai_api_key)
            self._initialized = True
            logger.info(f"QueryCacheService initialized with namespace: {self.config.namespace}")
        except ImportError as e:
            logger.warning(f"Cache service dependencies not installed: {e}")
            self._initialized = False
        except Exception as e:
            logger.error(f"Failed to initialize cache service: {e}")
            self._initialized = False

    @property
    def is_available(self) -> bool:
        """Check if cache service is available and properly configured."""
        return self._initialized and self.config.enabled

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def lookup(self, query: str, persona: str = None) -> CacheLookupResult:
        """
        Look up a query in the cache.

        Args:
            query: The natural language query
            persona: Optional persona filter (CFO, CRO, etc.)

        Returns:
            CacheLookupResult with hit type, similarity, and parsed structure
        """
        if not self.is_available:
            print(f"[CACHE] Lookup skipped - cache not available")
            return self._miss_result()

        try:
            print(f"[CACHE] Looking up: '{query[:50]}...'")
            # Generate embedding
            embedding = self._embed_query(query)

            # Build filter if persona specified
            filter_dict = None
            if persona:
                filter_dict = {"persona": {"$eq": persona}}

            # Query Pinecone
            results = self._index.query(
                vector=embedding,
                top_k=1,
                include_metadata=True,
                namespace=self.config.namespace,
                filter=filter_dict
            )

            # No matches
            if not results.matches:
                logger.debug(f"Cache miss (no matches): {query[:50]}...")
                return self._miss_result()

            match = results.matches[0]
            similarity = match.score
            metadata = match.metadata
            print(f"[CACHE] Found match: similarity={similarity:.3f}, original='{metadata.get('original_query', '')[:40]}...'")

            # Classify hit type
            hit_type = self._classify_hit(similarity)

            if hit_type == CacheHitType.MISS:
                logger.debug(f"Cache miss (low similarity {similarity:.3f}): {query[:50]}...")
                return CacheLookupResult(
                    hit_type=CacheHitType.MISS,
                    similarity=similarity,
                    parsed=None,
                    original_query=metadata.get("original_query"),
                    cache_id=match.id,
                    confidence=0.0
                )

            # Extract parsed structure from metadata
            parsed = self._extract_parsed(metadata)

            logger.info(f"Cache {hit_type.value} (similarity {similarity:.3f}): {query[:50]}...")

            return CacheLookupResult(
                hit_type=hit_type,
                similarity=similarity,
                parsed=parsed,
                original_query=metadata.get("original_query"),
                cache_id=match.id,
                confidence=metadata.get("confidence", 1.0) * similarity
            )

        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return self._miss_result()

    def store(
        self,
        query: str,
        parsed: Dict[str, Any],
        persona: str = "CFO",
        confidence: float = 1.0,
        source: str = "llm",
        fact_base_version: str = None
    ) -> Optional[str]:
        """
        Store a parsed query in the cache.

        Args:
            query: The original natural language query
            parsed: The parsed structure from LLM
            persona: The persona context (CFO, CRO, etc.)
            confidence: LLM's confidence in the parse (0.0-1.0)
            source: Origin of the parse (llm, seed, manual)
            fact_base_version: Version string for cache invalidation

        Returns:
            The vector ID if successful, None on error
        """
        if not self.is_available:
            logger.debug("Cache not available, skipping store")
            return None

        try:
            # Generate embedding
            embedding = self._embed_query(query)

            # Generate deterministic ID
            query_id = self._generate_id(query)

            # Build metadata
            now = datetime.utcnow().isoformat() + "Z"
            metadata = {
                # Parsed structure
                "intent": parsed.get("intent") or "",
                "metric": parsed.get("metric") or "",
                "period_type": parsed.get("period_type") or "",
                "period_reference": parsed.get("period_reference") or "",
                "period_year": parsed.get("period_year") or "",
                "comparison_type": parsed.get("comparison_type") or "",
                "comparison_period": parsed.get("comparison_period") or "",
                "group_by": parsed.get("group_by") or "",
                "filters": json.dumps(parsed.get("filters", {})),
                "limit": parsed.get("limit") if parsed.get("limit") is not None else 0,
                "sort_order": parsed.get("sort_order") or "",

                # Query text
                "original_query": query,
                "normalized_query": self._normalize_query(query),

                # Cache metadata
                "created_at": now,
                "updated_at": now,
                "hit_count": 0,
                "source": source,

                # Quality signals
                "confidence": confidence,
                "parse_version": "v1.0",
                "fact_base_version": fact_base_version or now[:10],

                # Persona
                "persona": persona,
                "metrics_referenced": json.dumps(self._extract_metrics(parsed)),
            }

            # Upsert to Pinecone
            self._index.upsert(
                vectors=[{
                    "id": query_id,
                    "values": embedding,
                    "metadata": metadata
                }],
                namespace=self.config.namespace
            )

            logger.info(f"Cached query {query_id}: {query[:50]}...")
            return query_id

        except Exception as e:
            logger.error(f"Cache store error: {e}")
            return None

    def bulk_store(self, items: List[Dict[str, Any]], batch_size: int = 100) -> int:
        """
        Store multiple queries in the cache (for seeding).

        Args:
            items: List of {"query": str, "parsed": dict, "persona": str, ...}
            batch_size: Number of vectors per upsert call

        Returns:
            Number of successfully stored items
        """
        if not self.is_available:
            logger.warning("Cache not available for bulk store")
            return 0

        vectors = []
        stored = 0

        for item in items:
            try:
                query = item["query"]
                parsed = item["parsed"]
                persona = item.get("persona", "CFO")
                confidence = item.get("confidence", 1.0)

                embedding = self._embed_query(query)
                query_id = self._generate_id(query)

                now = datetime.utcnow().isoformat() + "Z"
                metadata = {
                    "intent": parsed.get("intent") or "",
                    "metric": parsed.get("metric") or "",
                    "period_type": parsed.get("period_type") or "",
                    "period_reference": parsed.get("period_reference") or "",
                    "period_year": parsed.get("period_year") or "",
                    "comparison_type": parsed.get("comparison_type") or "",
                    "comparison_period": parsed.get("comparison_period") or "",
                    "group_by": parsed.get("group_by") or "",
                    "filters": json.dumps(parsed.get("filters", {})),
                    "limit": parsed.get("limit") if parsed.get("limit") is not None else 0,
                    "sort_order": parsed.get("sort_order") or "",
                    "original_query": query,
                    "normalized_query": self._normalize_query(query),
                    "created_at": now,
                    "updated_at": now,
                    "hit_count": 0,
                    "source": "seed",
                    "confidence": confidence,
                    "parse_version": "v1.0",
                    "fact_base_version": now[:10],
                    "persona": persona,
                    "metrics_referenced": json.dumps(self._extract_metrics(parsed)),
                }

                vectors.append({
                    "id": query_id,
                    "values": embedding,
                    "metadata": metadata
                })

                # Batch upsert
                if len(vectors) >= batch_size:
                    self._index.upsert(vectors=vectors, namespace=self.config.namespace)
                    stored += len(vectors)
                    vectors = []
                    logger.info(f"Bulk stored {stored} queries...")

            except Exception as e:
                logger.warning(f"Failed to prepare query for bulk store: {e}")

        # Final batch
        if vectors:
            self._index.upsert(vectors=vectors, namespace=self.config.namespace)
            stored += len(vectors)

        logger.info(f"Bulk store complete: {stored} queries cached")
        return stored

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.is_available:
            return {"available": False, "error": "Cache not configured"}

        try:
            stats = self._index.describe_index_stats()
            namespace_stats = stats.namespaces.get(self.config.namespace, {})

            return {
                "available": True,
                "total_vectors": stats.total_vector_count,
                "namespace": self.config.namespace,
                "namespace_vectors": namespace_stats.get("vector_count", 0),
                "dimension": stats.dimension,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"available": False, "error": str(e)}

    def delete_all(self, confirm: bool = False) -> bool:
        """
        Delete all vectors in the cache namespace.
        USE WITH CAUTION.

        Args:
            confirm: Must be True to proceed

        Returns:
            True if successful
        """
        if not confirm:
            logger.warning("delete_all called without confirmation")
            return False

        if not self.is_available:
            return False

        try:
            self._index.delete(delete_all=True, namespace=self.config.namespace)
            logger.info(f"Deleted all vectors in namespace {self.config.namespace}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete all: {e}")
            return False

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _miss_result(self) -> CacheLookupResult:
        """Create a cache miss result."""
        return CacheLookupResult(
            hit_type=CacheHitType.MISS,
            similarity=0.0,
            parsed=None,
            original_query=None,
            cache_id=None,
            confidence=0.0
        )

    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for a query using OpenAI."""
        normalized = self._normalize_query(query)

        response = self._openai.embeddings.create(
            input=normalized,
            model=self.config.embedding_model
        )

        return response.data[0].embedding

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent matching."""
        # Lowercase, strip whitespace, normalize spaces
        normalized = query.lower().strip()
        normalized = " ".join(normalized.split())
        return normalized

    def _generate_id(self, query: str) -> str:
        """Generate deterministic ID from query."""
        normalized = self._normalize_query(query)
        hash_hex = hashlib.md5(normalized.encode()).hexdigest()
        return f"q_{hash_hex[:12]}"

    def _classify_hit(self, similarity: float) -> CacheHitType:
        """Classify a similarity score into hit type."""
        if similarity >= self.config.threshold_exact:
            return CacheHitType.EXACT
        elif similarity >= self.config.threshold_high:
            return CacheHitType.HIGH
        elif similarity >= self.config.threshold_partial:
            return CacheHitType.PARTIAL
        else:
            return CacheHitType.MISS

    def _extract_parsed(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parsed structure from Pinecone metadata."""
        filters = metadata.get("filters", "{}")
        if isinstance(filters, str):
            try:
                filters = json.loads(filters)
            except:
                filters = {}

        return {
            "intent": metadata.get("intent"),
            "metric": metadata.get("metric"),
            "period_type": metadata.get("period_type"),
            "period_reference": metadata.get("period_reference"),
            "period_year": metadata.get("period_year"),
            "comparison_type": metadata.get("comparison_type"),
            "comparison_period": metadata.get("comparison_period"),
            "group_by": metadata.get("group_by"),
            "filters": filters,
            "limit": metadata.get("limit"),
            "sort_order": metadata.get("sort_order"),
        }

    def _extract_metrics(self, parsed: Dict[str, Any]) -> List[str]:
        """Extract list of metrics referenced in a parsed query."""
        metrics = []
        if parsed.get("metric"):
            metrics.append(parsed["metric"])
        return metrics


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_cache_service: Optional["QueryCacheService"] = None


def get_cache_service() -> Optional["QueryCacheService"]:
    """Get the global cache service instance."""
    global _cache_service
    return _cache_service


def init_cache_service_from_env() -> Optional["QueryCacheService"]:
    """Initialize the RAG cache service from environment variables."""
    import os
    global _cache_service

    pinecone_key = os.getenv("PINECONE_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", "")

    if not pinecone_key or not openai_key:
        logger.warning("RAG cache disabled: PINECONE_API_KEY or OPENAI_API_KEY not set")
        print(f"[CACHE] RAG cache disabled: pinecone_key={bool(pinecone_key)}, openai_key={bool(openai_key)}")
        return None
    
    print(f"[CACHE] Initializing RAG cache with Pinecone and OpenAI")

    config = CacheConfig(
        pinecone_api_key=pinecone_key,
        pinecone_index=os.getenv("PINECONE_INDEX", "aos-nlq"),
        openai_api_key=openai_key,
        namespace=os.getenv("PINECONE_NAMESPACE", "nlq-query-cache"),
        threshold_exact=float(os.getenv("CACHE_THRESHOLD_EXACT", "0.95")),
        threshold_high=float(os.getenv("CACHE_THRESHOLD_HIGH", "0.92")),
        threshold_partial=float(os.getenv("CACHE_THRESHOLD_PARTIAL", "0.85")),
        enabled=os.getenv("RAG_CACHE_ENABLED", "true").lower() == "true",
    )

    _cache_service = QueryCacheService(config)

    if _cache_service.is_available:
        stats = _cache_service.get_stats()
        print(f"[CACHE] RAG cache initialized: {stats.get('namespace_vectors', 0)} vectors")
        logger.info(f"RAG cache initialized: {stats.get('namespace_vectors', 0)} vectors in cache")
    else:
        print("[CACHE] RAG cache not available")
        logger.warning("RAG cache service initialized but not available (check API keys)")

    return _cache_service
