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
            or os.environ.get("DCL_API_URL", "http://localhost:8104")
        ).rstrip("/")
        self._cache: Optional[list[dict]] = None
        self._cache_expires: float = 0.0

    def _fetch_entities_from_dcl(self) -> list[dict]:
        """Fetch the full entity list from DCL — every entity an operator can name.

        NLQ answers any named entity by resolving its tenant (entity↔tenant 1:1), so
        the registry is the whole nameable universe, not one tenant's slice. The list
        comes from config.dcl_entities_ranked() — the SAME active-run index that
        resolves tenant-from-entity — so the entities shown are exactly the ones NLQ
        can answer, richest (most current data) first. That shared source is why the
        first entity is always a queryable one and never a stale "ghost": list order
        and tenant resolution can't drift apart. The "current entity when none is
        named" default stays config.get_tenant_id()'s job at query time; the registry
        does not scope to it.

        MUST NOT fall back to hardcoded values. If DCL is unreachable, raises
        ConnectionError naming the DCL URL — config returns an empty roster rather
        than fabricating one.
        """
        from ..config import dcl_entities_ranked

        # Pass this registry's configured DCL URL so an instance constructed against
        # a specific (or unreachable) DCL reads from THAT one, not the env default.
        ranked = dcl_entities_ranked(self._dcl_base_url)
        if not ranked:
            raise ConnectionError(
                f"EntityRegistry could not load entities from DCL at "
                f"{self._dcl_base_url}/api/dcl/triples/runs — DCL is unreachable or "
                f"has no ingest runs. Ensure DCL backend is running at "
                f"{self._dcl_base_url}."
            )

        def _format_name(eid: str) -> str:
            if any(c.isupper() for c in eid) or "-" in eid:
                return eid
            return eid.replace("_", " ").title()

        return [
            {"entity_id": eid, "display_name": _format_name(eid)}
            for eid, _tenant in ranked
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
        Returns list of: {"entity_id": str, "display_name": str}

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
