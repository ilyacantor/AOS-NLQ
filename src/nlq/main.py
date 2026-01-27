"""
FastAPI application entry point for AOS-NLQ.

This module initializes the FastAPI app and wires up all routes.
Run with: uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/v1")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "AOS-NLQ",
        "version": "0.1.0",
        "description": "Natural Language Query engine for enterprise data",
        "docs": "/docs",
    }
