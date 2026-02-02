"""
Dashboard Debug Info - Tracks all decisions made during dashboard generation.

This module provides visibility into the dashboard generation pipeline for debugging.
Instead of silently falling back to defaults, the system now tracks every decision
and can report exactly what happened and why.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Categories of failures that can occur during dashboard generation."""
    METRIC_EXTRACTION = "metric_extraction"
    METRIC_VALIDATION = "metric_validation"
    INTENT_DETECTION = "intent_detection"
    DIMENSION_RESOLUTION = "dimension_resolution"
    DATA_RESOLUTION = "data_resolution"
    SCHEMA_GENERATION = "schema_generation"
    REFINEMENT = "refinement"


class DecisionSource(str, Enum):
    """Source of a decision in the pipeline."""
    USER_REQUEST = "user_request"  # Explicitly requested by user
    SEMANTIC_RESOLUTION = "semantic_resolution"  # Resolved via semantic matching
    PATTERN_MATCH = "pattern_match"  # Matched via regex/pattern
    PERSONA_DEFAULT = "persona_default"  # Defaulted based on persona
    GENERIC_DEFAULT = "generic_default"  # Generic fallback (BAD - should fail)
    PADDING = "padding"  # Added to meet minimum count (BAD - should fail)


@dataclass
class DebugDecision:
    """A single decision made during processing."""
    stage: str
    decision: str
    source: DecisionSource
    details: Optional[str] = None
    is_fallback: bool = False  # True if this was a fallback/default


@dataclass
class DebugWarning:
    """A warning about something that might be wrong."""
    category: FailureCategory
    message: str
    suggestion: Optional[str] = None


@dataclass
class DebugError:
    """An error that should have caused failure but was silently handled."""
    category: FailureCategory
    message: str
    original_exception: Optional[str] = None
    should_have_failed: bool = True


@dataclass
class DashboardDebugInfo:
    """
    Tracks all decisions made during dashboard generation for debugging.

    This is returned with every dashboard response so developers can see
    exactly what happened in the pipeline.
    """

    # What was requested
    original_query: str = ""

    # Metric extraction tracking
    metrics_requested: List[str] = field(default_factory=list)  # What user asked for
    metrics_extracted: List[str] = field(default_factory=list)  # What was extracted
    metrics_extraction_method: str = ""  # How extraction happened
    metrics_padded: List[str] = field(default_factory=list)  # Metrics added via padding (BAD)
    metrics_failed_validation: List[str] = field(default_factory=list)  # Metrics that failed

    # Intent detection tracking
    intent_detected: str = ""
    intent_confidence: float = 0.0
    intent_triggers: List[str] = field(default_factory=list)  # What triggered this intent

    # Dimension handling
    dimensions_requested: List[str] = field(default_factory=list)
    dimensions_resolved: List[str] = field(default_factory=list)
    dimensions_fallback: List[str] = field(default_factory=list)  # Dimensions that fell back

    # Data resolution tracking
    data_sources: Dict[str, str] = field(default_factory=dict)  # widget_id -> source
    data_missing: List[str] = field(default_factory=list)  # Widgets with no data
    data_estimated: List[str] = field(default_factory=list)  # Widgets with fabricated data

    # All decisions made
    decisions: List[DebugDecision] = field(default_factory=list)

    # Warnings and errors
    warnings: List[DebugWarning] = field(default_factory=list)
    errors: List[DebugError] = field(default_factory=list)

    # Summary flags
    used_fallbacks: bool = False
    used_padding: bool = False
    used_estimated_data: bool = False

    def add_decision(
        self,
        stage: str,
        decision: str,
        source: DecisionSource,
        details: Optional[str] = None,
    ) -> None:
        """Record a decision made during processing."""
        is_fallback = source in (
            DecisionSource.GENERIC_DEFAULT,
            DecisionSource.PADDING,
            DecisionSource.PERSONA_DEFAULT,
        )

        self.decisions.append(DebugDecision(
            stage=stage,
            decision=decision,
            source=source,
            details=details,
            is_fallback=is_fallback,
        ))

        if is_fallback:
            self.used_fallbacks = True
            logger.warning(f"[DEBUG] Fallback used at {stage}: {decision} (source: {source.value})")

        if source == DecisionSource.PADDING:
            self.used_padding = True

    def add_warning(
        self,
        category: FailureCategory,
        message: str,
        suggestion: Optional[str] = None,
    ) -> None:
        """Add a warning about potential issues."""
        self.warnings.append(DebugWarning(
            category=category,
            message=message,
            suggestion=suggestion,
        ))
        logger.warning(f"[DEBUG] Warning ({category.value}): {message}")

    def add_error(
        self,
        category: FailureCategory,
        message: str,
        original_exception: Optional[str] = None,
    ) -> None:
        """Record an error that was silently handled."""
        self.errors.append(DebugError(
            category=category,
            message=message,
            original_exception=original_exception,
        ))
        logger.error(f"[DEBUG] Silent error ({category.value}): {message}")

    def record_metric_padding(self, padded_metrics: List[str]) -> None:
        """Record that metrics were padded (this is bad!)."""
        self.metrics_padded = padded_metrics
        self.used_padding = True
        self.add_warning(
            FailureCategory.METRIC_EXTRACTION,
            f"Metrics were padded with defaults: {padded_metrics}",
            "User requested fewer metrics than dashboard template expects. "
            "Should generate a simpler dashboard instead of padding.",
        )

    def record_estimated_data(self, widget_id: str) -> None:
        """Record that data was estimated/fabricated (this is bad!)."""
        self.data_estimated.append(widget_id)
        self.used_estimated_data = True
        self.add_warning(
            FailureCategory.DATA_RESOLUTION,
            f"Data for widget '{widget_id}' was estimated/fabricated",
            "No real data available. Should show empty state or error instead.",
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "original_query": self.original_query,
            "metrics": {
                "requested": self.metrics_requested,
                "extracted": self.metrics_extracted,
                "extraction_method": self.metrics_extraction_method,
                "padded": self.metrics_padded,
                "failed_validation": self.metrics_failed_validation,
            },
            "intent": {
                "detected": self.intent_detected,
                "confidence": self.intent_confidence,
                "triggers": self.intent_triggers,
            },
            "dimensions": {
                "requested": self.dimensions_requested,
                "resolved": self.dimensions_resolved,
                "fallback": self.dimensions_fallback,
            },
            "data": {
                "sources": self.data_sources,
                "missing": self.data_missing,
                "estimated": self.data_estimated,
            },
            "decisions": [
                {
                    "stage": d.stage,
                    "decision": d.decision,
                    "source": d.source.value,
                    "details": d.details,
                    "is_fallback": d.is_fallback,
                }
                for d in self.decisions
            ],
            "warnings": [
                {
                    "category": w.category.value,
                    "message": w.message,
                    "suggestion": w.suggestion,
                }
                for w in self.warnings
            ],
            "errors": [
                {
                    "category": e.category.value,
                    "message": e.message,
                    "original_exception": e.original_exception,
                }
                for e in self.errors
            ],
            "summary": {
                "used_fallbacks": self.used_fallbacks,
                "used_padding": self.used_padding,
                "used_estimated_data": self.used_estimated_data,
                "warning_count": len(self.warnings),
                "error_count": len(self.errors),
            },
        }

    def get_summary_message(self) -> str:
        """Get a human-readable summary of issues."""
        issues = []

        if self.used_padding:
            issues.append(f"- PADDING: Added {len(self.metrics_padded)} unrequested metrics: {self.metrics_padded}")

        if self.used_estimated_data:
            issues.append(f"- ESTIMATED DATA: {len(self.data_estimated)} widgets have fabricated data")

        if self.metrics_failed_validation:
            issues.append(f"- INVALID METRICS: {self.metrics_failed_validation}")

        if self.dimensions_fallback:
            issues.append(f"- DIMENSION FALLBACKS: {self.dimensions_fallback}")

        for error in self.errors:
            issues.append(f"- ERROR ({error.category.value}): {error.message}")

        if not issues:
            return "No issues detected"

        return "Dashboard generation issues:\n" + "\n".join(issues)


class DashboardGenerationError(Exception):
    """
    Raised when dashboard generation fails in a way that should NOT be silently handled.

    This replaces the old pattern of `except: pass` or silent fallbacks.
    """

    def __init__(
        self,
        message: str,
        category: FailureCategory,
        debug_info: Optional[DashboardDebugInfo] = None,
        suggestion: Optional[str] = None,
    ):
        super().__init__(message)
        self.category = category
        self.debug_info = debug_info
        self.suggestion = suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self),
            "category": self.category.value,
            "suggestion": self.suggestion,
            "debug_info": self.debug_info.to_dict() if self.debug_info else None,
        }


# Global flag to control strict mode
# In development: True (fail loudly)
# In production: False (fall back but log warnings)
STRICT_MODE = True


def set_strict_mode(enabled: bool) -> None:
    """Enable or disable strict mode for dashboard generation."""
    global STRICT_MODE
    STRICT_MODE = enabled
    logger.info(f"Dashboard strict mode: {'ENABLED' if enabled else 'DISABLED'}")


def is_strict_mode() -> bool:
    """Check if strict mode is enabled."""
    return STRICT_MODE
