"""
Metric Embedding Index for Tier 2 intent recognition.

This module provides embedding-based metric lookup as an alternative to
regex patterns. It's cheaper than full LLM parsing (~$0.0001 vs ~$0.003+)
and scales automatically without manual pattern maintenance.

Architecture:
    Tier 1: FREE (no API calls)
    ├── RAG Cache hit (>0.85 similarity)
    ├── Off-topic filter
    └── Canonical metric lookup (exact match)

    Tier 2: CHEAP (~$0.0001/query)  ← THIS MODULE
    └── Embedding-based metric classification

    Tier 3: EXPENSIVE (~$0.003+/query)
    └── Full LLM parse (only when needed)

Usage:
    index = MetricEmbeddingIndex()
    await index.initialize()  # One-time: builds embeddings

    result = await index.lookup("ebitda")
    if result and result.confidence > 0.85:
        # Direct point query, no LLM needed
        metric = result.canonical_metric
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MetricLookupResult:
    """Result from metric embedding lookup."""
    canonical_metric: str
    similarity: float
    confidence: float
    matched_term: str  # What the embedding actually matched
    display_name: str
    unit: str

    @property
    def is_high_confidence(self) -> bool:
        """True if this is a confident match that can skip LLM."""
        return self.confidence >= 0.85


class MetricEmbeddingIndex:
    """
    In-memory embedding index for canonical metrics.

    Uses OpenAI embeddings (same as RAG cache) but stores in-memory
    for fast cosine similarity lookup. Since there are only ~100 metrics,
    this is more efficient than hitting Pinecone for every query.
    """

    # Similarity thresholds
    THRESHOLD_HIGH = 0.88      # Very confident match
    THRESHOLD_MEDIUM = 0.80    # Likely match, may need verification
    THRESHOLD_MIN = 0.70       # Minimum to consider

    def __init__(self, openai_client: Any = None):
        """
        Initialize the metric embedding index.

        Args:
            openai_client: OpenAI client instance. If None, will create one.
        """
        self._openai = openai_client
        self._embeddings: Dict[str, np.ndarray] = {}  # term -> embedding
        self._term_to_metric: Dict[str, str] = {}     # term -> canonical metric
        self._metric_metadata: Dict[str, Dict] = {}   # metric -> {display_name, unit, ...}
        self._initialized = False
        self._embedding_model = "text-embedding-3-small"
        self._embedding_dim = 1536

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """
        Build the embedding index for all metrics.

        This should be called once at startup. It:
        1. Loads all canonical metrics and their synonyms
        2. Generates embeddings for each term
        3. Stores them in-memory for fast lookup
        """
        if self._initialized:
            return

        # Lazy import to avoid circular dependencies
        from src.nlq.knowledge.schema import FINANCIAL_SCHEMA
        from src.nlq.knowledge.synonyms import METRIC_SYNONYMS

        # Initialize OpenAI client if needed
        if self._openai is None:
            try:
                import openai
                self._openai = openai.OpenAI()
            except (ImportError, OSError, ValueError, RuntimeError) as e:
                logger.warning(f"Could not initialize OpenAI client: {e}")
                return

        # Collect all terms to embed
        terms_to_embed: List[Tuple[str, str]] = []  # (term, canonical_metric)

        for metric_name, metric_def in FINANCIAL_SCHEMA.items():
            # Add canonical metric name
            terms_to_embed.append((metric_name, metric_name))
            terms_to_embed.append((metric_def.display_name.lower(), metric_name))

            # Store metadata
            self._metric_metadata[metric_name] = {
                "display_name": metric_def.display_name,
                "unit": metric_def.unit,
                "metric_type": metric_def.metric_type.value,
                "description": metric_def.description or "",
            }

            # Add synonyms
            if metric_name in METRIC_SYNONYMS:
                for synonym in METRIC_SYNONYMS[metric_name]:
                    terms_to_embed.append((synonym.lower(), metric_name))

        # Deduplicate terms
        seen_terms = set()
        unique_terms = []
        for term, metric in terms_to_embed:
            if term not in seen_terms:
                seen_terms.add(term)
                unique_terms.append((term, metric))
                self._term_to_metric[term] = metric

        logger.info(f"Building metric embedding index with {len(unique_terms)} terms")

        # Generate embeddings in batches
        batch_size = 100
        all_terms = [t[0] for t in unique_terms]

        for i in range(0, len(all_terms), batch_size):
            batch = all_terms[i:i + batch_size]
            try:
                response = self._openai.embeddings.create(
                    input=batch,
                    model=self._embedding_model
                )
                for j, embedding_data in enumerate(response.data):
                    term = batch[j]
                    self._embeddings[term] = np.array(embedding_data.embedding)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.error(f"Failed to generate embeddings: {e}")
                return

        self._initialized = True
        logger.info(f"Metric embedding index initialized with {len(self._embeddings)} embeddings")

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def lookup(self, query: str) -> Optional[MetricLookupResult]:
        """
        Look up a query in the metric embedding index.

        Args:
            query: User's query text (e.g., "ebitda", "what's our margin")

        Returns:
            MetricLookupResult if a confident match is found, None otherwise
        """
        if not self._initialized:
            return None

        # Normalize query
        query_normalized = query.lower().strip()

        # First, try exact match (free - no embedding needed)
        if query_normalized in self._term_to_metric:
            metric = self._term_to_metric[query_normalized]
            metadata = self._metric_metadata.get(metric, {})
            return MetricLookupResult(
                canonical_metric=metric,
                similarity=1.0,
                confidence=1.0,
                matched_term=query_normalized,
                display_name=metadata.get("display_name", metric),
                unit=metadata.get("unit", ""),
            )

        # Generate embedding for query
        try:
            response = self._openai.embeddings.create(
                input=query_normalized,
                model=self._embedding_model
            )
            query_embedding = np.array(response.data[0].embedding)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to embed query: {e}")
            return None

        # Find best match
        best_match: Optional[Tuple[str, float]] = None

        for term, embedding in self._embeddings.items():
            similarity = self._cosine_similarity(query_embedding, embedding)
            if similarity >= self.THRESHOLD_MIN:
                if best_match is None or similarity > best_match[1]:
                    best_match = (term, similarity)

        if best_match is None:
            return None

        term, similarity = best_match
        metric = self._term_to_metric[term]
        metadata = self._metric_metadata.get(metric, {})

        # Calculate confidence (adjusted by how close to thresholds)
        if similarity >= self.THRESHOLD_HIGH:
            confidence = 0.90 + (similarity - self.THRESHOLD_HIGH) * 0.5
        elif similarity >= self.THRESHOLD_MEDIUM:
            confidence = 0.75 + (similarity - self.THRESHOLD_MEDIUM) * 1.5
        else:
            confidence = 0.50 + (similarity - self.THRESHOLD_MIN) * 2.5

        confidence = min(1.0, max(0.0, confidence))

        return MetricLookupResult(
            canonical_metric=metric,
            similarity=similarity,
            confidence=confidence,
            matched_term=term,
            display_name=metadata.get("display_name", metric),
            unit=metadata.get("unit", ""),
        )

    def lookup_sync(self, query: str) -> Optional[MetricLookupResult]:
        """Synchronous version of lookup for non-async contexts."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, need to run in new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.lookup(query))
                    return future.result()
            else:
                return loop.run_until_complete(self.lookup(query))
        except RuntimeError:
            return asyncio.run(self.lookup(query))


# Global instance for singleton pattern
_metric_index: Optional[MetricEmbeddingIndex] = None


def get_metric_embedding_index() -> MetricEmbeddingIndex:
    """Get or create the global metric embedding index."""
    global _metric_index
    if _metric_index is None:
        _metric_index = MetricEmbeddingIndex()
    return _metric_index


async def initialize_metric_index() -> None:
    """Initialize the global metric embedding index."""
    index = get_metric_embedding_index()
    await index.initialize()
