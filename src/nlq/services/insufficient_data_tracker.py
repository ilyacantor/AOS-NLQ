"""
Insufficient Data Tracker Service

Tracks queries that return with confidence below the threshold (70%),
indicating possible insufficient data conditions.

These queries are recorded for analysis and UI display to help identify
data gaps or query patterns that need better coverage.
"""

import logging
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import uuid

from src.nlq.config import DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

# Confidence threshold - queries below this are flagged
CONFIDENCE_THRESHOLD = 0.7


@dataclass
class InsufficientDataEntry:
    """A single entry for a low-confidence query."""
    query: str
    confidence: float
    persona: str
    reason: str  # Why the confidence was low
    resolved_metric: Optional[str] = None
    resolved_period: Optional[str] = None
    parsed_intent: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = DEFAULT_TENANT_ID
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "query": self.query,
            "confidence": self.confidence,
            "persona": self.persona,
            "reason": self.reason,
            "resolved_metric": self.resolved_metric,
            "resolved_period": self.resolved_period,
            "parsed_intent": self.parsed_intent,
            "timestamp": self.timestamp.isoformat() + "Z",
            "session_id": self.session_id,
        }

    def to_plain_english(self) -> str:
        """Generate a plain English summary of this entry."""
        query_preview = self.query[:50] + "..." if len(self.query) > 50 else self.query
        conf_pct = f"{self.confidence:.0%}"
        return f'"{query_preview}" returned {conf_pct} confidence - {self.reason}'


class InsufficientDataTracker:
    """
    Tracks queries with low confidence scores.

    Stores entries in Supabase for long-term tracking.
    Also maintains an in-memory buffer for quick access to recent entries.
    """

    def __init__(
        self,
        supabase_url: str = None,
        supabase_key: str = None,
        table_name: str = "insufficient_data_log",
        max_memory_entries: int = 200,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ):
        """
        Initialize the tracker.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase API key
            table_name: Name of the table to store logs
            max_memory_entries: Maximum entries to keep in memory
            confidence_threshold: Threshold below which queries are tracked
        """
        api_url = os.getenv("SUPABASE_API_URL", "").strip()
        fallback_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_url = supabase_url or (api_url if api_url.startswith("https://") else None) or (fallback_url if fallback_url.startswith("https://") else "")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY", "")
        self.table_name = table_name
        self.max_memory_entries = max_memory_entries
        self.confidence_threshold = confidence_threshold

        self._client = None
        self._memory_buffer: List[InsufficientDataEntry] = []
        self._initialized = False

        if self.supabase_url and self.supabase_key:
            self._init_client()

    def _init_client(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            self._client = create_client(self.supabase_url, self.supabase_key)
            self._initialized = True
            logger.info("Insufficient Data Tracker connected to Supabase")
        except ImportError:
            logger.warning("Supabase library not installed, using memory-only mode")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if Supabase connection is available."""
        return self._initialized and self._client is not None

    def should_track(self, confidence: float) -> bool:
        """Check if this confidence score should be tracked."""
        return confidence < self.confidence_threshold

    def get_reason_for_low_confidence(
        self,
        confidence: float,
        metric_found: bool = True,
        period_found: bool = True,
        data_exists: bool = True,
        is_ambiguous: bool = False,
    ) -> str:
        """Determine the reason for low confidence."""
        reasons = []

        if is_ambiguous:
            reasons.append("ambiguous query")
        if not metric_found:
            reasons.append("metric not recognized")
        if not period_found:
            reasons.append("time period unclear")
        if not data_exists:
            reasons.append("data not available")

        if not reasons:
            if confidence < 0.5:
                reasons.append("query not understood")
            elif confidence < 0.6:
                reasons.append("low intent clarity")
            elif confidence < 0.7:
                reasons.append("partial match only")
            else:
                reasons.append("below confidence threshold")

        return "; ".join(reasons)

    async def track_entry(self, entry: InsufficientDataEntry) -> bool:
        """
        Track a low-confidence query.

        Args:
            entry: The insufficient data entry

        Returns:
            True if successfully tracked
        """
        # Always add to memory buffer
        self._add_to_memory(entry)

        # Try to persist to Supabase
        if self.is_available:
            try:
                data = {
                    "id": entry.id,
                    "tenant_id": entry.tenant_id or DEFAULT_TENANT_ID,
                    "session_id": entry.session_id,
                    "query": entry.query[:500],
                    "confidence": entry.confidence,
                    "persona": entry.persona,
                    "reason": entry.reason[:500],
                    "resolved_metric": entry.resolved_metric,
                    "resolved_period": entry.resolved_period,
                    "parsed_intent": entry.parsed_intent,
                    "created_at": entry.timestamp.isoformat(),
                }

                self._client.table(self.table_name).insert(data).execute()
                logger.debug(f"Tracked insufficient data entry: {entry.id}")
                return True
            except Exception as e:
                logger.error(f"Failed to log to Supabase: {e}")
                return False
        else:
            logger.debug("Supabase not available, stored in memory only")
            return True

    def track_sync(
        self,
        query: str,
        confidence: float,
        persona: str = "CFO",
        resolved_metric: Optional[str] = None,
        resolved_period: Optional[str] = None,
        parsed_intent: Optional[str] = None,
        session_id: Optional[str] = None,
        metric_found: bool = True,
        period_found: bool = True,
        data_exists: bool = True,
        is_ambiguous: bool = False,
    ) -> Optional[InsufficientDataEntry]:
        """
        Synchronously track a low-confidence query if below threshold.

        Returns the entry if tracked, None if above threshold.
        """
        if not self.should_track(confidence):
            return None

        reason = self.get_reason_for_low_confidence(
            confidence,
            metric_found=metric_found,
            period_found=period_found,
            data_exists=data_exists,
            is_ambiguous=is_ambiguous,
        )

        entry = InsufficientDataEntry(
            query=query,
            confidence=confidence,
            persona=persona,
            reason=reason,
            resolved_metric=resolved_metric,
            resolved_period=resolved_period,
            parsed_intent=parsed_intent,
            session_id=session_id,
        )

        self._add_to_memory(entry)

        # Async persist would be better but for simplicity sync to memory
        if self.is_available:
            try:
                data = {
                    "id": entry.id,
                    "tenant_id": entry.tenant_id,
                    "session_id": entry.session_id,
                    "query": entry.query[:500],
                    "confidence": entry.confidence,
                    "persona": entry.persona,
                    "reason": entry.reason[:500],
                    "resolved_metric": entry.resolved_metric,
                    "resolved_period": entry.resolved_period,
                    "parsed_intent": entry.parsed_intent,
                    "created_at": entry.timestamp.isoformat(),
                }
                self._client.table(self.table_name).insert(data).execute()
            except Exception as e:
                logger.error(f"Failed to persist to Supabase: {e}")

        return entry

    def _add_to_memory(self, entry: InsufficientDataEntry):
        """Add entry to in-memory buffer (for quick access)."""
        self._memory_buffer.insert(0, entry)

        # Trim if exceeds max
        if len(self._memory_buffer) > self.max_memory_entries:
            self._memory_buffer = self._memory_buffer[:self.max_memory_entries]

    def get_recent_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent entries from memory.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of entries as dictionaries (newest first)
        """
        entries = self._memory_buffer[:limit]
        return [e.to_dict() for e in entries]

    def get_recent_entries_plain(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent entries with plain English descriptions.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of entries with plain English summaries (newest first)
        """
        entries = self._memory_buffer[:limit]
        return [
            {
                "id": e.id,
                "description": e.to_plain_english(),
                "query": e.query,
                "confidence": e.confidence,
                "reason": e.reason,
                "persona": e.persona,
                "timestamp": e.timestamp.isoformat() + "Z",
            }
            for e in entries
        ]

    async def get_entries_from_db(
        self,
        limit: int = 50,
        offset: int = 0,
        persona: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Get entries from Supabase database.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            persona: Optional filter by persona

        Returns:
            List of entries from database (newest first)
        """
        if not self.is_available:
            return self.get_recent_entries(limit)

        try:
            query = self._client.table(self.table_name).select("*")

            if persona:
                query = query.eq("persona", persona)

            result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to fetch from Supabase: {e}")
            return self.get_recent_entries(limit)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about insufficient data conditions.

        Returns:
            Dictionary with statistics
        """
        total = len(self._memory_buffer)

        if total == 0:
            return {
                "total_entries": 0,
                "avg_confidence": 0,
                "by_reason": {},
                "by_persona": {},
                "threshold": self.confidence_threshold,
                "supabase_connected": self.is_available,
            }

        # Calculate average confidence
        avg_conf = sum(e.confidence for e in self._memory_buffer) / total

        # Group by reason
        by_reason: Dict[str, int] = {}
        for e in self._memory_buffer:
            for reason_part in e.reason.split("; "):
                by_reason[reason_part] = by_reason.get(reason_part, 0) + 1

        # Group by persona
        by_persona: Dict[str, int] = {}
        for e in self._memory_buffer:
            by_persona[e.persona] = by_persona.get(e.persona, 0) + 1

        return {
            "total_entries": total,
            "avg_confidence": round(avg_conf, 3),
            "by_reason": by_reason,
            "by_persona": by_persona,
            "threshold": self.confidence_threshold,
            "supabase_connected": self.is_available,
        }

    def clear_memory(self):
        """Clear the in-memory buffer."""
        self._memory_buffer = []
        logger.info("Cleared insufficient data tracker memory buffer")


# Singleton instance
_tracker_instance: Optional[InsufficientDataTracker] = None


def get_insufficient_data_tracker() -> InsufficientDataTracker:
    """Get the global insufficient data tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = InsufficientDataTracker()
    return _tracker_instance
