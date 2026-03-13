"""
FastAPI routes for AOS-NLQ.

This module provides the REST API endpoints:
- POST /v1/query: Submit natural language queries
- GET /v1/health: Health check endpoint
- GET /v1/schema: Available metrics and periods

All responses include bounded confidence scores [0.0, 1.0].
"""

__all__ = ["router"]


def __getattr__(name):
    if name == "router":
        from src.nlq.api.routes import router
        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
