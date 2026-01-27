"""
Core processing logic for AOS-NLQ.

This module contains:
- parser: Query parsing and intent extraction using Claude
- resolver: Date/period resolution (relative to absolute)
- executor: Query execution against the fact base
- confidence: Confidence scoring with bounded [0, 1] output

All confidence scores are guaranteed to be in the [0.0, 1.0] range.
"""

from src.nlq.core.confidence import ConfidenceCalculator, bounded_confidence
from src.nlq.core.executor import QueryExecutor
from src.nlq.core.parser import QueryParser
from src.nlq.core.resolver import PeriodResolver

__all__ = [
    "QueryParser",
    "PeriodResolver",
    "QueryExecutor",
    "ConfidenceCalculator",
    "bounded_confidence",
]
