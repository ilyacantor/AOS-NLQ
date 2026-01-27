"""
Date and period resolution for AOS-NLQ.

CRITICAL: Relative periods ("last quarter", "last year") are resolved
based on an injected reference_date, NOT system time. This ensures
reproducible results and proper testing.

Handles:
- Relative periods: last_year, this_year, last_quarter, etc.
- Absolute periods: 2024, Q4 2025, 2025-Q1, etc.
- Edge cases: Q1 "last quarter" resolves to Q4 of previous year
"""

from datetime import date
from typing import Dict, Optional

from src.nlq.models.query import PeriodType


class PeriodResolver:
    """Resolves relative period references to absolute periods."""

    def __init__(self, reference_date: Optional[date] = None):
        """
        Initialize the period resolver.

        Args:
            reference_date: The date to use as "today" for relative resolution.
                          Defaults to actual today if not provided.
        """
        self.reference_date = reference_date or date.today()
        self.current_year = self.reference_date.year
        self.current_quarter = (self.reference_date.month - 1) // 3 + 1

    def resolve(self, period_reference: str, period_type: PeriodType = None) -> Dict:
        """
        Convert a period reference to an absolute period specification.

        Args:
            period_reference: Either relative ("last_year") or absolute ("2024")
            period_type: Hint about period type (annual, quarterly, etc.)

        Returns:
            Dict with type, year, and optionally quarter

        Examples:
            resolve("last_year") -> {"type": "annual", "year": 2025}
            resolve("last_quarter") -> {"type": "quarterly", "year": 2025, "quarter": 4}
            resolve("2024") -> {"type": "annual", "year": 2024}
            resolve("Q4 2025") -> {"type": "quarterly", "year": 2025, "quarter": 4}
        """
        # Normalize the reference
        ref = period_reference.lower().replace(" ", "_").replace("-", "_")

        # Check for relative references
        relative_mappings = {
            "last_year": self._last_year,
            "prior_year": self._last_year,
            "previous_year": self._last_year,
            "this_year": self._this_year,
            "current_year": self._this_year,
            "last_quarter": self._last_quarter,
            "prior_quarter": self._last_quarter,
            "previous_quarter": self._last_quarter,
            "this_quarter": self._this_quarter,
            "current_quarter": self._this_quarter,
        }

        if ref in relative_mappings:
            return relative_mappings[ref]()

        # Try to parse as absolute period
        return self._parse_absolute(period_reference)

    def _last_year(self) -> Dict:
        """Resolve 'last year' to the previous calendar year."""
        return {"type": "annual", "year": self.current_year - 1}

    def _this_year(self) -> Dict:
        """Resolve 'this year' to the current calendar year."""
        return {"type": "annual", "year": self.current_year}

    def _last_quarter(self) -> Dict:
        """
        Resolve 'last quarter' to the previous quarter.

        EDGE CASE: If current quarter is Q1, last quarter is Q4 of previous year.
        """
        if self.current_quarter == 1:
            return {
                "type": "quarterly",
                "year": self.current_year - 1,
                "quarter": 4
            }
        return {
            "type": "quarterly",
            "year": self.current_year,
            "quarter": self.current_quarter - 1
        }

    def _this_quarter(self) -> Dict:
        """Resolve 'this quarter' to the current quarter."""
        return {
            "type": "quarterly",
            "year": self.current_year,
            "quarter": self.current_quarter
        }

    def _parse_absolute(self, period_reference: str) -> Dict:
        """
        Parse an absolute period reference.

        Supports formats:
        - "2024" -> annual
        - "Q4 2025", "2025-Q4", "2025_Q4" -> quarterly
        """
        ref = period_reference.strip()

        # Try to parse as year only
        if ref.isdigit() and len(ref) == 4:
            return {"type": "annual", "year": int(ref)}

        # Try to parse quarterly formats
        ref_upper = ref.upper()

        # Format: Q4 2025
        import re
        match = re.match(r'Q(\d)\s*(\d{4})', ref_upper)
        if match:
            return {
                "type": "quarterly",
                "year": int(match.group(2)),
                "quarter": int(match.group(1))
            }

        # Format: 2025-Q4 or 2025_Q4
        match = re.match(r'(\d{4})[-_]Q(\d)', ref_upper)
        if match:
            return {
                "type": "quarterly",
                "year": int(match.group(1)),
                "quarter": int(match.group(2))
            }

        # Unable to parse - return as-is with unknown type
        return {"type": "unknown", "raw": period_reference}

    def to_period_key(self, resolved: Dict) -> str:
        """
        Convert a resolved period dict to a string key for fact base lookup.

        Args:
            resolved: Dict from resolve() method

        Returns:
            String key like "2024" or "2025-Q4"
        """
        if resolved["type"] == "annual":
            return str(resolved["year"])
        elif resolved["type"] == "quarterly":
            return f"{resolved['year']}-Q{resolved['quarter']}"
        else:
            return resolved.get("raw", "unknown")
