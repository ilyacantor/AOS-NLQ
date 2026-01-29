"""
RAG Learning Log Service

Provides persistent logging of RAG cache interactions for observability.
Stores entries in Supabase for long-term tracking and analysis.
"""

import logging
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import uuid
import json

logger = logging.getLogger(__name__)


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

@dataclass
class LearningLogEntry:
    """A single entry in the RAG learning log."""
    query: str
    success: bool
    source: str  # "cache", "llm", "bypass", "error"
    learned: bool  # Whether this query was added to the cache
    message: str  # Plain English description of what happened
    persona: str = "CFO"
    similarity: float = 0.0  # Cache similarity score if applicable
    llm_confidence: float = 0.0  # LLM confidence if applicable
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = DEFAULT_TENANT_ID
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "query": self.query,
            "success": self.success,
            "source": self.source,
            "learned": self.learned,
            "message": self.message,
            "persona": self.persona,
            "similarity": self.similarity,
            "llm_confidence": self.llm_confidence,
            "timestamp": self.timestamp.isoformat() + "Z",
        }

    def to_plain_english(self) -> str:
        """
        Generate a plain English summary of this entry.
        Example: "Query 'What is revenue?' was successfully retrieved from cache"
        """
        query_preview = self.query[:50] + "..." if len(self.query) > 50 else self.query

        if self.source == "cache" and self.success:
            return f'"{query_preview}" retrieved from learned patterns ({self.similarity:.0%} match)'
        elif self.source == "llm" and self.success:
            if self.learned:
                return f'"{query_preview}" processed by AI and learned for future use'
            else:
                return f'"{query_preview}" processed by AI (not confident enough to learn)'
        elif self.source == "bypass":
            return f'"{query_preview}" handled as special query'
        elif not self.success:
            return f'"{query_preview}" could not be processed: {self.message}'
        else:
            return f'"{query_preview}": {self.message}'


class RAGLearningLog:
    """
    Persistent log of RAG learning events.

    Stores entries in Supabase for long-term tracking.
    Also maintains an in-memory buffer for quick access to recent entries.
    """

    def __init__(
        self,
        supabase_url: str = None,
        supabase_key: str = None,
        table_name: str = "rag_learning_log",
        max_memory_entries: int = 100,
    ):
        """
        Initialize the RAG learning log.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase API key
            table_name: Name of the table to store logs
            max_memory_entries: Maximum entries to keep in memory
        """
        # Prefer SUPABASE_API_URL over SUPABASE_URL (which may be PostgreSQL connection string)
        api_url = os.getenv("SUPABASE_API_URL", "").strip()
        fallback_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_url = supabase_url or (api_url if api_url.startswith("https://") else None) or (fallback_url if fallback_url.startswith("https://") else "")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY", "")
        self.table_name = table_name
        self.max_memory_entries = max_memory_entries

        self._client = None
        self._memory_buffer: List[LearningLogEntry] = []
        self._initialized = False

        if self.supabase_url and self.supabase_key:
            self._init_client()

    def _init_client(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            self._client = create_client(self.supabase_url, self.supabase_key)
            self._initialized = True
            logger.info("RAG Learning Log connected to Supabase")
        except ImportError:
            logger.warning("Supabase library not installed, using memory-only mode")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if Supabase connection is available."""
        return self._initialized and self._client is not None

    async def log_entry(self, entry: LearningLogEntry) -> bool:
        """
        Log a learning event.

        Args:
            entry: The learning log entry

        Returns:
            True if successfully logged
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
                    "query": entry.query[:500],  # Limit query length
                    "success": entry.success,
                    "source": entry.source,
                    "learned": entry.learned,
                    "message": entry.message[:500],
                    "persona": entry.persona,
                    "similarity": entry.similarity,
                    "llm_confidence": entry.llm_confidence,
                    "created_at": entry.timestamp.isoformat(),
                }

                self._client.table(self.table_name).insert(data).execute()
                logger.debug(f"Logged learning event: {entry.id}")
                return True
            except Exception as e:
                logger.error(f"Failed to log to Supabase: {e}")
                return False
        else:
            logger.debug("Supabase not available, stored in memory only")
            return True

    def _add_to_memory(self, entry: LearningLogEntry):
        """Add entry to in-memory buffer (for quick access)."""
        self._memory_buffer.insert(0, entry)  # Add to beginning (newest first)

        # Trim if exceeds max
        if len(self._memory_buffer) > self.max_memory_entries:
            self._memory_buffer = self._memory_buffer[:self.max_memory_entries]

    def get_recent_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent log entries from memory.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of log entries as dictionaries (newest first)
        """
        entries = self._memory_buffer[:limit]
        return [e.to_dict() for e in entries]

    def get_recent_entries_plain(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent log entries with plain English descriptions.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of log entries with plain English summaries (newest first)
        """
        entries = self._memory_buffer[:limit]
        return [
            {
                "id": e.id,
                "description": e.to_plain_english(),
                "success": e.success,
                "source": e.source,
                "learned": e.learned,
                "timestamp": e.timestamp.isoformat() + "Z",
                "persona": e.persona,
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
        Get log entries from Supabase database.

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            persona: Optional filter by persona

        Returns:
            List of log entries from database (newest first)
        """
        if not self.is_available:
            # Fall back to memory
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
        Get learning statistics.

        Returns:
            Dictionary with learning statistics
        """
        total = len(self._memory_buffer)
        successful = sum(1 for e in self._memory_buffer if e.success)
        learned = sum(1 for e in self._memory_buffer if e.learned)
        from_cache = sum(1 for e in self._memory_buffer if e.source == "cache" and e.success)
        from_llm = sum(1 for e in self._memory_buffer if e.source == "llm" and e.success)

        return {
            "total_queries": total,
            "successful_queries": successful,
            "queries_learned": learned,
            "from_cache": from_cache,
            "from_llm": from_llm,
            "cache_hit_rate": from_cache / total if total > 0 else 0,
            "learning_rate": learned / total if total > 0 else 0,
            "supabase_connected": self.is_available,
        }

    def clear_memory(self):
        """Clear the in-memory buffer."""
        self._memory_buffer = []
        logger.info("Cleared RAG learning log memory buffer")


# Singleton instance
_log_instance: Optional[RAGLearningLog] = None


def get_learning_log() -> RAGLearningLog:
    """Get the global RAG learning log instance."""
    global _log_instance
    if _log_instance is None:
        _log_instance = RAGLearningLog()
    return _log_instance
