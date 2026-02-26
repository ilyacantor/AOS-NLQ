"""
Query Pattern Seeder — Layer 4 of NLQ target architecture.

Loads curated NL→semantic query pairs from query_patterns_seed.yaml and
seeds the Pinecone-backed query cache on startup. This gives every persona
a warm, accurate cache from the first query — no runtime learning needed.

The seeder never overwrites learned patterns from real queries. It only
seeds when the cache has fewer than 10 entries (fresh or wiped state).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Intent classification based on pattern properties
_INTENT_MAP = {
    "comparison": "COMPARISON",
    "composite": "COMPOSITE",
}


def _infer_intent(pattern: Dict[str, Any]) -> str:
    """Infer query intent from pattern properties."""
    period_type = pattern.get("period_type", "")
    tags = pattern.get("tags", [])
    dimension = pattern.get("dimension")

    if period_type == "comparison" or "comparison" in tags:
        return "COMPARISON"
    if "composite" in tags:
        return "COMPOSITE"
    if "superlative" in tags:
        return "SUPERLATIVE"
    if "trend" in tags:
        return "TREND"
    if dimension:
        return "BREAKDOWN"
    return "POINT_QUERY"


def _pattern_to_cache_item(persona: str, pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a seed YAML pattern into the format expected by bulk_store."""
    intent = _infer_intent(pattern)
    return {
        "query": pattern["nl"],
        "parsed": {
            "intent": intent,
            "metric": pattern["canonical_metric"],
            "period_type": pattern.get("period_type", "current"),
            "group_by": pattern.get("dimension", ""),
        },
        "persona": persona.upper(),
        "confidence": 1.0,
    }


class QueryPatternSeeder:
    """Loads seed corpus and populates the query cache on startup."""

    def __init__(self, cache_client, seed_file_path: str):
        """
        Args:
            cache_client: QueryCacheService instance (must have bulk_store/get_stats).
            seed_file_path: Path to query_patterns_seed.yaml.
        """
        self.cache = cache_client
        self.seed_path = Path(seed_file_path)

    def seed_if_empty(self) -> int:
        """Seed the cache only if it has fewer than 10 entries.

        Returns the number of patterns seeded (0 if skipped).
        """
        if not self.cache or not self.cache.is_available:
            logger.warning("[SEED] Cache not available — skipping seed")
            return 0

        stats = self.cache.get_stats()
        existing = stats.get("namespace_vectors", 0)

        if existing >= 10:
            logger.info(f"[SEED] Cache already has {existing} entries — skipping seed")
            return 0

        logger.info(f"[SEED] Cache has {existing} entries — seeding from {self.seed_path.name}")
        return self.seed_all()

    def seed_all(self) -> int:
        """Load seed YAML and store all patterns in the cache.

        Returns the number of patterns successfully stored.
        """
        if not self.cache or not self.cache.is_available:
            logger.warning("[SEED] Cache not available — cannot seed")
            return 0

        if not self.seed_path.exists():
            logger.error(f"[SEED] Seed file not found: {self.seed_path}")
            return 0

        # Load YAML
        with open(self.seed_path) as f:
            data = yaml.safe_load(f)

        patterns_by_persona = data.get("patterns", {})
        if not patterns_by_persona:
            logger.warning("[SEED] No patterns found in seed file")
            return 0

        # Transform all patterns into bulk_store format
        items: List[Dict[str, Any]] = []
        per_persona: Dict[str, int] = {}

        for persona, patterns in patterns_by_persona.items():
            count = 0
            for pattern in patterns:
                items.append(_pattern_to_cache_item(persona, pattern))
                count += 1
            per_persona[persona] = count

        # Log per-persona counts
        for persona, count in per_persona.items():
            logger.info(f"[SEED] {persona}: {count} patterns")

        # Bulk store
        stored = self.cache.bulk_store(items)
        logger.info(f"[SEED] Seeded {stored}/{len(items)} patterns into query cache")

        return stored
