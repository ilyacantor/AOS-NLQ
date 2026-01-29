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
from src.nlq.services.query_cache_service import init_cache_service_from_env, get_cache_service
from src.nlq.services.llm_call_counter import init_call_counter, get_call_counter
from src.nlq.services.rag_learning_log import get_learning_log
from src.nlq.db.supabase_persistence import init_persistence_service, get_persistence_service

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

# Note: RAG cache service singleton is managed in query_cache_service.py
# Use get_cache_service() and init_cache_service_from_env() from there


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting AOS-NLQ server...")

    # Initialize Supabase persistence service first (required by other services)
    persistence = init_persistence_service()
    if persistence and persistence.is_available:
        logger.info("Supabase persistence service initialized")
        stats = persistence.get_stats()
        logger.info(f"Persistence stats: {stats}")
    else:
        logger.warning("Persistence service not available - sessions will not persist")

    # Initialize RAG cache service
    init_cache_service_from_env()

    # Initialize call counter with persistence and load active sessions
    counter = init_call_counter(persist=persistence is not None and persistence.is_available)
    if persistence and persistence.is_available:
        loaded = counter.load_active_sessions(since_hours=168)  # 7 days
        logger.info(f"Loaded {loaded} active sessions from database")

    # Initialize learning log (singleton)
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
