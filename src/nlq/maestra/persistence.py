"""
Maestra persistence — Supabase storage for sessions, messages, contour maps, engagements.

Tables:
    maestra_engagements — top-level engagement (one per deal)
    maestra_sessions    — per-entity scoping sessions
    maestra_messages    — conversation messages
    contour_maps        — enterprise contour maps (one per entity per engagement)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from src.nlq.db.supabase_persistence import get_persistence_service

logger = logging.getLogger(__name__)


class MaestraPersistence:
    """
    Persistence layer for Maestra data using Supabase.

    Uses the existing SupabasePersistenceService singleton for the client.
    All operations use the service-role key with explicit tenant_id filtering.
    """

    def __init__(self):
        self._svc = get_persistence_service()

    @property
    def is_available(self) -> bool:
        return self._svc is not None and self._svc.is_available

    @property
    def _client(self):
        if not self.is_available:
            return None
        return self._svc._client

    # =========================================================================
    # ENGAGEMENTS
    # =========================================================================

    def save_engagement(self, engagement: dict[str, Any]) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("maestra_engagements").upsert(
                engagement,
                on_conflict="engagement_id",
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save engagement: {e}")
            return False

    def get_engagement(self, engagement_id: str) -> Optional[dict[str, Any]]:
        if not self._client:
            return None
        try:
            result = self._client.table("maestra_engagements").select("*").eq(
                "engagement_id", engagement_id
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get engagement: {e}")
            return None

    # =========================================================================
    # SESSIONS
    # =========================================================================

    def save_session(self, session: dict[str, Any]) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("maestra_sessions").upsert(
                session,
                on_conflict="session_id",
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        if not self._client:
            return None
        try:
            result = self._client.table("maestra_sessions").select("*").eq(
                "session_id", session_id
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def get_sessions_for_engagement(self, engagement_id: str) -> list[dict[str, Any]]:
        if not self._client:
            return []
        try:
            result = self._client.table("maestra_sessions").select("*").eq(
                "engagement_id", engagement_id
            ).order("created_at").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get sessions for engagement: {e}")
            return []

    # =========================================================================
    # MESSAGES
    # =========================================================================

    def save_message(self, message: dict[str, Any]) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("maestra_messages").insert(message).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return False

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._client:
            return []
        try:
            result = self._client.table("maestra_messages").select("*").eq(
                "session_id", session_id
            ).order("created_at").limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []

    # =========================================================================
    # CONTOUR MAPS
    # =========================================================================

    def save_contour_map(
        self,
        engagement_id: str,
        entity_id: str,
        contour_data: dict[str, Any],
        completeness_score: float,
    ) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("contour_maps").upsert(
                {
                    "engagement_id": engagement_id,
                    "entity_id": entity_id,
                    "contour_data": contour_data,
                    "completeness_score": completeness_score,
                    "updated_at": datetime.utcnow().isoformat(),
                },
                on_conflict="engagement_id,entity_id",
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save contour map: {e}")
            return False

    def get_contour_map(
        self,
        engagement_id: str,
        entity_id: str,
    ) -> Optional[dict[str, Any]]:
        if not self._client:
            return None
        try:
            result = self._client.table("contour_maps").select("*").eq(
                "engagement_id", engagement_id
            ).eq(
                "entity_id", entity_id
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get contour map: {e}")
            return None

    def get_contour_maps_for_engagement(
        self,
        engagement_id: str,
    ) -> list[dict[str, Any]]:
        if not self._client:
            return []
        try:
            result = self._client.table("contour_maps").select("*").eq(
                "engagement_id", engagement_id
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get contour maps: {e}")
            return []


# Singleton
_persistence: Optional[MaestraPersistence] = None


def get_maestra_persistence() -> MaestraPersistence:
    global _persistence
    if _persistence is None:
        _persistence = MaestraPersistence()
    return _persistence
