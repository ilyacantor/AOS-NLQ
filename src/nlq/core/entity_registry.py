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
        """Fetch financial entity list from DCL's active engagement.

        Uses engagement_state (entity_a, entity_b) — not a raw distinct
        query on semantic_triples, which could include non-financial entities.

        MUST NOT fall back to hardcoded values. If DCL is unreachable,
        raises ConnectionError with message naming the DCL URL and what failed.
        """
        engagement_url = f"{self._dcl_base_url}/api/dcl/triples/engagement"
        try:
            resp = self._client.get(engagement_url)
        except httpx.ConnectError:
            raise ConnectionError(
                f"EntityRegistry could not reach DCL at {engagement_url} — "
                f"connection refused. Ensure DCL backend is running at "
                f"{self._dcl_base_url}."
            )
        except httpx.TimeoutException:
            raise ConnectionError(
                f"EntityRegistry timed out waiting for DCL at {engagement_url}. "
                f"DCL may be overloaded or unreachable."
            )

        if resp.status_code != 200:
            raise ConnectionError(
                f"EntityRegistry got HTTP {resp.status_code} from {engagement_url}: "
                f"{resp.text[:200]}"
            )

        data = resp.json()
        entities = []

        def _format_name(eid: str) -> str:
            if any(c.isupper() for c in eid) or "-" in eid:
                return eid
            return eid.replace("_", " ").title()

        ea = data.get("entity_a")
        if ea and ea.get("id"):
            entities.append({
                "entity_id": ea["id"],
                "display_name": ea.get("display_name") or _format_name(ea["id"]),
                "role": "acquirer",
            })
        eb = data.get("entity_b")
        if eb and eb.get("id"):
            entities.append({
                "entity_id": eb["id"],
                "display_name": eb.get("display_name") or _format_name(eb["id"]),
                "role": "target",
            })

        return entities

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
