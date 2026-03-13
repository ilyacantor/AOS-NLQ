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
from src.nlq.api.export_routes import router as export_router
from src.nlq.api.dcl_proxy import router as dcl_proxy_router
from src.nlq.maestra.routes import router as maestra_router
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
app.include_router(export_router, prefix="/api/v1")

# Maestra routes — native NLQ endpoints for engagement lifecycle.
# Mounted BEFORE the DCL proxy so /api/reports/maestra/* is handled here.
app.include_router(maestra_router)

# DCL report proxy — forwards /api/reports/* to DCL backend for combining
# statements and entity overlap data (portal uses these endpoints).
# Note: Maestra requests are handled by maestra_router above, not proxied.
app.include_router(dcl_proxy_router)

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

    # Log external service URLs so missing vars are immediately visible in deploy logs
    _farm_url = os.environ.get("FARM_URL")
    _dcl_url = os.environ.get("DCL_API_URL")
    if _farm_url:
        logger.info(f"FARM_URL = {_farm_url}")
    else:
        logger.error("FARM_URL is NOT SET — reconciliation endpoints will fail")
    if _dcl_url:
        logger.info(f"DCL_API_URL = {_dcl_url}")
    else:
        _allow_no_dcl = os.environ.get("NLQ_ALLOW_NO_DCL")
        if _allow_no_dcl:
            logger.warning(
                "DCL_API_URL is NOT SET — NLQ_ALLOW_NO_DCL is set, starting in degraded mode. "
                "Only demo-mode queries with local data will work. "
                "Set DCL_API_URL to enable real data queries."
            )
        else:
            raise RuntimeError(
                "FATAL: DCL_API_URL environment variable is not set. "
                "NLQ requires a DCL endpoint to serve queries. "
                "Set DCL_API_URL to the DCL service URL (e.g. http://localhost:8004). "
                "For demo-only mode with local data, set NLQ_ALLOW_NO_DCL=1."
            )

    init_call_counter(persist=False)

    asyncio.create_task(_deferred_init())

    logger.info("AOS-NLQ server accepting requests (services initializing in background)")


async def _deferred_init():
    """Heavy service initialization that runs after server is already accepting requests.

    Each init step is isolated so one failure does not cascade to subsequent steps.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    failures = []

    # Step 1: Persistence + session restore
    try:
        persistence = await loop.run_in_executor(None, init_persistence_service)
        if persistence and persistence.is_available:
            logger.info("Supabase persistence service initialized")
            counter = get_call_counter()
            counter.enable_persistence()
            counter.load_active_sessions()
        else:
            logger.warning("Persistence service not available - sessions will not persist")
    except Exception as e:
        failures.append("persistence")
        logger.error(
            f"Persistence/session init failed: {type(e).__name__}: {e} — "
            f"cache, pattern seeding, and other services will still attempt to initialize"
        )

    # Step 2: Cache service
    try:
        await loop.run_in_executor(None, init_cache_service_from_env)
    except Exception as e:
        failures.append("cache")
        logger.error(f"Cache service init failed: {type(e).__name__}: {e}")

    # Step 3: Seed query pattern cache
    try:
        cache = get_cache_service()
        if cache and cache.is_available:
            from src.nlq.knowledge.pattern_seeder import QueryPatternSeeder
            seed_path = Path(__file__).parent.parent.parent / "data" / "query_patterns_seed.yaml"
            seeder = QueryPatternSeeder(cache, str(seed_path))
            seeded = await loop.run_in_executor(None, seeder.seed_if_empty)
            logger.info(f"Query pattern cache seeded: {seeded} patterns")
    except Exception as e:
        failures.append("pattern_seeder")
        logger.error(f"Pattern seeder failed: {type(e).__name__}: {e}")

    # Step 4: Learning log cleanup
    try:
        learning_log = get_learning_log()
        if learning_log.is_available:
            deleted = await learning_log.cleanup_old_entries(retention_days=90)
            if deleted:
                logger.info(f"Learning log cleanup: ~{deleted} old entries removed")
    except Exception as e:
        failures.append("learning_log")
        logger.warning(f"Learning log cleanup failed: {type(e).__name__}: {e}")

    # Step 5: DCL pre-warm
    try:
        client = get_semantic_client()
        if client.dcl_url:
            import time as _time
            _prewarm_deadline = _time.time() + 60  # 60s max wait
            _prewarm_attempt = 0
            while _time.time() < _prewarm_deadline:
                _prewarm_attempt += 1
                health = await loop.run_in_executor(
                    None, client.check_dcl_health
                )
                phase = health.get("phase")
                connected = health.get("connected", False)

                if connected and phase in ("ready", "degraded"):
                    try:
                        logger.info(f"DCL pre-warm: phase={phase}, fetching catalog...")
                        catalog = await loop.run_in_executor(
                            None, lambda: client.get_catalog(force_refresh=True)
                        )
                        logger.info(
                            f"DCL pre-warm SUCCESS: "
                            f"{len(catalog.metrics)} metrics cached "
                            f"(mode={catalog.dcl_mode})"
                        )
                        break
                    except Exception as e:
                        logger.warning(
                            f"DCL pre-warm fetch failed despite phase={phase}: "
                            f"{type(e).__name__}: {e}"
                        )
                else:
                    logger.info(
                        f"DCL pre-warm poll {_prewarm_attempt}: "
                        f"connected={connected}, phase={phase} — waiting..."
                    )

                await asyncio.sleep(3)
            else:
                logger.warning(
                    "DCL pre-warm timed out after 60s. "
                    "First user request will trigger catalog fetch."
                )
        else:
            logger.info("DCL pre-warm skipped (DCL_API_URL not configured)")
    except Exception as e:
        failures.append("dcl_prewarm")
        logger.error(f"DCL pre-warm failed: {type(e).__name__}: {e}")

    if failures:
        logger.warning(f"Background init completed with failures: {failures}")
    else:
        logger.info("All background services initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down AOS-NLQ server...")

# Serve static React build in production
# Primary: project-root/dist (local dev, Docker builds)
# Fallback: src/nlq/_dist (Render Python runtime — build.sh copies dist/ here
#           because Render strips Node artifacts between build and runtime phases)
DIST_DIR = Path(__file__).parent.parent.parent / "dist"
_DIST_FALLBACK = Path(__file__).parent / "_dist"

_static_dir = None
if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    _static_dir = DIST_DIR
elif _DIST_FALLBACK.exists() and (_DIST_FALLBACK / "index.html").exists():
    _static_dir = _DIST_FALLBACK
    logger.info(f"Using _dist fallback for static files: {_DIST_FALLBACK}")

if _static_dir:
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    logger.warning(
        f"No static frontend found. Checked: {DIST_DIR}, {_DIST_FALLBACK}. "
        f"Run 'npm run build' or check build.sh output."
    )

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
