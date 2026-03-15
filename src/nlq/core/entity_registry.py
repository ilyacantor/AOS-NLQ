"""
Dynamic entity resolution from DCL engagement state.

Replaces all hardcoded entity references in NLQ app code.
Entities are discovered from DCL's active engagement, not hardcoded.
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes


class EntityRegistry:
    """
    Dynamic entity resolution from DCL engagement state.

    Replaces all hardcoded entity references in NLQ app code.
    Entities are discovered from DCL's active engagement, not hardcoded.
    """

    def __init__(self, dcl_base_url: str = None):
        """
        Initialize with DCL backend URL.
        Caches entity list with TTL (5 minutes).
        """
        self._dcl_base_url = (
            dcl_base_url
            or os.environ.get("DCL_API_URL", "http://localhost:8004")
        ).rstrip("/")
        self._cache: Optional[list[dict]] = None
        self._cache_expires: float = 0.0
        self._client = httpx.Client(timeout=10.0)

    def _fetch_entities_from_dcl(self) -> list[dict]:
        """
        Fetch entity list from DCL.

        Tries multiple discovery strategies:
        1. GET /api/dcl/resolution/v2/stats — parse entity breakdowns
        2. POST /api/dcl/query with metric=revenue, no entity filter — collect distinct entity_ids

        MUST NOT fall back to hardcoded values. If DCL is unreachable,
        raises ConnectionError with message naming the DCL URL and what failed.
        """
        # Strategy 1: resolution stats endpoint
        stats_url = f"{self._dcl_base_url}/api/dcl/resolution/v2/stats"
        try:
            resp = self._client.get(stats_url)
            if resp.status_code == 200:
                data = resp.json()
                entities = self._parse_entities_from_stats(data)
                if entities:
                    return entities
        except httpx.ConnectError:
            raise ConnectionError(
                f"EntityRegistry could not reach DCL at {stats_url} — "
                f"connection refused. Ensure DCL backend is running at "
                f"{self._dcl_base_url}."
            )
        except httpx.TimeoutException:
            raise ConnectionError(
                f"EntityRegistry timed out waiting for DCL at {stats_url}. "
                f"DCL may be overloaded or unreachable."
            )

        # Strategy 2: query DCL for revenue to discover entity_ids from data
        query_url = f"{self._dcl_base_url}/api/dcl/query"
        try:
            resp = self._client.post(
                query_url,
                json={
                    "metric": "revenue",
                    "time_range": {"start": "2024-Q1", "end": "2026-Q4"},
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                entities = self._parse_entities_from_query(data)
                if entities:
                    return entities
        except httpx.ConnectError:
            raise ConnectionError(
                f"EntityRegistry could not reach DCL at {query_url} — "
                f"connection refused after stats endpoint returned no entities. "
                f"Ensure DCL backend is running at {self._dcl_base_url}."
            )
        except httpx.TimeoutException:
            raise ConnectionError(
                f"EntityRegistry timed out waiting for DCL at {query_url}. "
                f"DCL may be overloaded or unreachable."
            )

        # DCL responded but returned no entity data — valid (empty engagement)
        return []

    def _parse_entities_from_stats(self, data: dict) -> list[dict]:
        """Extract entity list from resolution/v2/stats response."""
        entities = []

        # Try entity_stats field
        if "entity_stats" in data and isinstance(data["entity_stats"], dict):
            for eid, stats in data["entity_stats"].items():
                if eid == "combined":
                    continue
                entities.append({
                    "entity_id": eid,
                    "display_name": stats.get("display_name", eid.replace("_", " ").title()),
                    "role": stats.get("role", "entity"),
                })

        # Try entities field (alternate format)
        if not entities and "entities" in data and isinstance(data["entities"], list):
            for item in data["entities"]:
                if isinstance(item, dict) and item.get("entity_id"):
                    eid = item["entity_id"]
                    if eid == "combined":
                        continue
                    entities.append({
                        "entity_id": eid,
                        "display_name": item.get("display_name", eid.replace("_", " ").title()),
                        "role": item.get("role", "entity"),
                    })
                elif isinstance(item, str) and item != "combined":
                    entities.append({
                        "entity_id": item,
                        "display_name": item.replace("_", " ").title(),
                        "role": "entity",
                    })

        return entities

    def _parse_entities_from_query(self, data: dict) -> list[dict]:
        """Extract distinct entity_ids from DCL query response data rows."""
        entity_ids = set()
        for row in data.get("data", []):
            if isinstance(row, dict):
                eid = row.get("entity_id")
                if eid and eid != "combined":
                    entity_ids.add(eid)

        # Also check metadata
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            eid = metadata.get("entity_id")
            if eid and eid != "combined":
                entity_ids.add(eid)

        return [
            {
                "entity_id": eid,
                "display_name": eid.replace("_", " ").title(),
                "role": "entity",
            }
            for eid in sorted(entity_ids)
        ]

    # ── Sync accessors (for use in sync code paths) ──────────────────────

    def get_entities_sync(self) -> list[dict]:
        """Get entities synchronously, using cache if available."""
        now = time.time()
        if self._cache is not None and now < self._cache_expires:
            return self._cache
        entities = self._fetch_entities_from_dcl()
        self._cache = entities
        self._cache_expires = now + _CACHE_TTL
        return entities

    def get_entity_name_sync(self, entity_id: str) -> str:
        """Get display name for an entity_id. Raises ValueError if not found."""
        if entity_id == "combined":
            entities = self.get_entities_sync()
            names = [e["display_name"] for e in entities]
            return f"Combined ({' + '.join(names)})" if names else "Combined"
        entities = self.get_entities_sync()
        for e in entities:
            if e["entity_id"] == entity_id:
                return e["display_name"]
        raise ValueError(
            f"Entity '{entity_id}' not found in registry. "
            f"Known entities: {[e['entity_id'] for e in entities]}"
        )

    def get_entity_ids_sync(self) -> list[str]:
        """Returns just the entity_id strings."""
        return [e["entity_id"] for e in self.get_entities_sync()]

    def is_valid_entity_sync(self, entity_id: str) -> bool:
        """Check if entity_id is registered. 'combined' is always valid."""
        if entity_id == "combined":
            return True
        return any(e["entity_id"] == entity_id for e in self.get_entities_sync())

    # ── Async accessors (per spec interface) ─────────────────────────────

    async def get_entities(self) -> list[dict]:
        """
        Fetch active entities from DCL.
        Returns list of: {"entity_id": str, "display_name": str, "role": str}

        MUST NOT fall back to hardcoded values. If DCL is unreachable,
        raises ConnectionError with message naming the DCL URL and what failed.
        """
        now = time.time()
        if self._cache is not None and now < self._cache_expires:
            return self._cache
        entities = await asyncio.to_thread(self._fetch_entities_from_dcl)
        self._cache = entities
        self._cache_expires = now + _CACHE_TTL
        return entities

    async def get_entity_name(self, entity_id: str) -> str:
        """
        Get display name for an entity_id.
        Raises ValueError if entity_id not found in registry.
        """
        if entity_id == "combined":
            entities = await self.get_entities()
            names = [e["display_name"] for e in entities]
            return f"Combined ({' + '.join(names)})" if names else "Combined"
        entities = await self.get_entities()
        for e in entities:
            if e["entity_id"] == entity_id:
                return e["display_name"]
        raise ValueError(
            f"Entity '{entity_id}' not found in registry. "
            f"Known entities: {[e['entity_id'] for e in entities]}"
        )

    async def get_entity_ids(self) -> list[str]:
        """Returns just the entity_id strings."""
        entities = await self.get_entities()
        return [e["entity_id"] for e in entities]

    async def is_valid_entity(self, entity_id: str) -> bool:
        """Check if entity_id is registered. 'combined' is always valid."""
        if entity_id == "combined":
            return True
        entities = await self.get_entities()
        return any(e["entity_id"] == entity_id for e in entities)

    def invalidate_cache(self):
        """Force refresh on next call."""
        self._cache = None
        self._cache_expires = 0.0


# ── Module-level singleton ───────────────────────────────────────────────

_registry: Optional[EntityRegistry] = None


def get_entity_registry() -> EntityRegistry:
    """Get the module-level EntityRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = EntityRegistry()
    return _registry
