"""
Domain knowledge for AOS-NLQ.

This module contains:
- synonyms: Metric and period synonym mappings for normalization
- schema: Financial data schema definitions

The knowledge module enables the NLQ engine to understand various ways
users might refer to the same metrics (e.g., "revenue" = "sales" = "top line").

All data access goes through DCL (Data Control Layer).
"""

from src.nlq.knowledge.synonyms import (
    METRIC_SYNONYMS,
    PERIOD_SYNONYMS,
    normalize_metric,
    normalize_period,
)

__all__ = [
    "METRIC_SYNONYMS",
    "PERIOD_SYNONYMS",
    "normalize_metric",
    "normalize_period",
]
