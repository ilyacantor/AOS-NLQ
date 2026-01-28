"""
FastAPI application entry point for AOS-NLQ.

This module initializes the FastAPI app and wires up all routes.
In production, it also serves the React frontend static files.
Run with: uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000
"""

import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.nlq.api.routes import router
from src.nlq.api.rag_routes import router as rag_router
from src.nlq.services.query_cache_service import QueryCacheService, CacheConfig
from src.nlq.services.llm_call_counter import get_call_counter
from src.nlq.services.rag_learning_log import get_learning_log

logger = logging.getLogger(__name__)

# =============================================================================
# APPLICATION SETUP
# =============================================================================

app = FastAPI(
    title="AOS-NLQ",
    description="Natural Language Query engine for enterprise data",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes (both prefixes for dev proxy and production)
app.include_router(router, prefix="/v1")
app.include_router(router, prefix="/api/v1")

# Include RAG routes
app.include_router(rag_router, prefix="/v1")
app.include_router(rag_router, prefix="/api/v1")

# =============================================================================
# RAG CACHE SERVICE SINGLETON
# =============================================================================

_cache_service: Optional[QueryCacheService] = None


def get_cache_service() -> Optional[QueryCacheService]:
    """Get the global cache service instance."""
    global _cache_service
    return _cache_service


def init_cache_service():
    """Initialize the RAG cache service from environment variables."""
    global _cache_service

    pinecone_key = os.getenv("PINECONE_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if not pinecone_key or not openai_key:
        logger.warning("RAG cache disabled: PINECONE_API_KEY or OPENAI_API_KEY not set")
        return

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
        logger.info(f"RAG cache initialized: {stats.get('namespace_vectors', 0)} vectors in cache")
    else:
        logger.warning("RAG cache service initialized but not available (check API keys)")


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting AOS-NLQ server...")

    # Initialize RAG cache service
    init_cache_service()

    # Initialize call counter and learning log (singletons)
    get_call_counter()
    get_learning_log()

    logger.info("AOS-NLQ server started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down AOS-NLQ server...")

# Serve static React build in production
DIST_DIR = Path(__file__).parent.parent.parent / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")
else:
    @app.get("/")
    async def root():
        """Root endpoint with API info (dev mode)."""
        return {
            "name": "AOS-NLQ",
            "version": "0.1.0",
            "description": "Natural Language Query engine for enterprise data",
            "docs": "/docs",
            "mode": "development"
        }
