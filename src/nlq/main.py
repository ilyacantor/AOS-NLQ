"""
FastAPI application entry point for AOS-NLQ.

This module initializes the FastAPI app and wires up all routes.
In production, it also serves the React frontend static files.
Run with: uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.nlq.api.routes import router

app = FastAPI(
    title="AOS-NLQ",
    description="Natural Language Query engine for enterprise data",
    version="0.1.0",
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

# Include API routes
app.include_router(router, prefix="/v1")

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
