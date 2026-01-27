"""
Domain knowledge for AOS-NLQ.

This module contains:
- synonyms: Metric and period synonym mappings for normalization
- schema: Financial data schema definitions
- fact_base: Fact base loader and query interface

The knowledge module enables the NLQ engine to understand various ways
users might refer to the same metrics (e.g., "revenue" = "sales" = "top line").
"""

from src.nlq.knowledge.synonyms import (
    METRIC_SYNONYMS,
    PERIOD_SYNONYMS,
    normalize_metric,
    normalize_period,
)
from src.nlq.knowledge.fact_base import FactBase

__all__ = [
    "METRIC_SYNONYMS",
    "PERIOD_SYNONYMS",
    "normalize_metric",
    "normalize_period",
    "FactBase",
]
