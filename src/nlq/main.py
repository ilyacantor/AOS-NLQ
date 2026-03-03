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

from dotenv import load_dotenv
load_dotenv()  # Load .env into os.environ before any service reads env vars

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.nlq.api.routes import router
from src.nlq.api.rag_routes import router as rag_router
from src.nlq.api.dashboard_routes import router as dashboard_router
from src.nlq.api.health import router as health_router
from src.nlq.api.eval import router as eval_router
from src.nlq.dcl.routes import router as dcl_router
from src.nlq.services.query_cache_service import init_cache_service_from_env, get_cache_service
from src.nlq.services.llm_call_counter import init_call_counter, get_call_counter
from src.nlq.services.rag_learning_log import get_learning_log
from src.nlq.services.dcl_semantic_client import get_semantic_client
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

# CORS middleware — origins controlled via CORS_ORIGINS env var.
# Comma-separated list of allowed origins. Defaults to common dev origins.
# Set to "*" only if you truly need open access (credentials will be disabled).
_cors_origins_raw = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5000,http://localhost:3000,http://localhost:8000",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
_allow_credentials = "*" not in _cors_origins  # Browsers reject credentials + wildcard

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# H7: Single canonical prefix — Vite proxy forwards /api/v1 as-is (no rewrite).
# C1: Query routes (routes.py) + extracted health/eval routers
app.include_router(router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(eval_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")

# Include DCL routes (Data Connectivity Layer - entity resolution, conflicts, provenance)
app.include_router(dcl_router)

# Note: RAG cache service singleton is managed in query_cache_service.py
# Use get_cache_service() and init_cache_service_from_env() from there


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup — heavy inits run in background."""
    import asyncio
    logger.info("Starting AOS-NLQ server...")

    init_call_counter(persist=False)

    asyncio.create_task(_deferred_init())

    logger.info("AOS-NLQ server accepting requests (services initializing in background)")


async def _deferred_init():
    """Heavy service initialization that runs after server is already accepting requests."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()

        persistence = await loop.run_in_executor(None, init_persistence_service)
        if persistence and persistence.is_available:
            logger.info("Supabase persistence service initialized")
            counter = get_call_counter()
            counter.enable_persistence()
            counter.load_active_sessions()
        else:
            logger.warning("Persistence service not available - sessions will not persist")

        await loop.run_in_executor(None, init_cache_service_from_env)

        # Layer 4: Seed the query pattern cache from curated corpus
        cache = get_cache_service()
        if cache and cache.is_available:
            from src.nlq.knowledge.pattern_seeder import QueryPatternSeeder
            seed_path = Path(__file__).parent.parent.parent / "data" / "query_patterns_seed.yaml"
            seeder = QueryPatternSeeder(cache, str(seed_path))
            seeded = await loop.run_in_executor(None, seeder.seed_if_empty)
            logger.info(f"Query pattern cache seeded: {seeded} patterns")

        learning_log = get_learning_log()

        # Layer 4b: 90-day retention cleanup — best-effort, non-blocking
        if learning_log.is_available:
            try:
                deleted = await learning_log.cleanup_old_entries(retention_days=90)
                if deleted:
                    logger.info(f"Learning log cleanup: ~{deleted} old entries removed")
            except Exception as e:
                logger.warning(f"Learning log cleanup failed (non-fatal): {e}")

        # Layer 5: Pre-warm DCL catalog in background so first user request
        # doesn't block on a cold-starting DCL (Render free tier cold starts
        # take 15-30s).  Retries with backoff — logs each attempt for
        # visibility in Render logs.  Does NOT block startup.
        client = get_semantic_client()
        if client.dcl_url:
            warmup_backoffs = [2, 5, 10, 15, 20]  # seconds between attempts
            for attempt, wait in enumerate(warmup_backoffs, 1):
                try:
                    logger.info(f"DCL pre-warm attempt {attempt}/{len(warmup_backoffs)}...")
                    catalog = await loop.run_in_executor(
                        None, lambda: client.get_catalog(force_refresh=True)
                    )
                    logger.info(
                        f"DCL pre-warm SUCCESS on attempt {attempt}: "
                        f"{len(catalog.metrics)} metrics cached "
                        f"(mode={catalog.dcl_mode})"
                    )
                    break  # Catalog is now cached — first user request will be instant
                except Exception as e:
                    logger.warning(
                        f"DCL pre-warm attempt {attempt}/{len(warmup_backoffs)} failed: "
                        f"{type(e).__name__}: {e}"
                    )
                    if attempt < len(warmup_backoffs):
                        await asyncio.sleep(wait)
                    else:
                        logger.warning(
                            "DCL pre-warm exhausted all attempts. "
                            "First user request will trigger catalog fetch."
                        )
        else:
            logger.info("DCL pre-warm skipped (DCL_API_URL not configured)")

        logger.info("All background services initialized")
    except Exception as e:
        logger.error(f"Background service initialization error: {e}")


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
