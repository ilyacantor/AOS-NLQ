"""
Dynamic date utilities for AOS-NLQ.

Single source of truth for "current year", "current quarter", etc.
All query defaults derive from here — nothing is hardcoded.
"""

from datetime import date
import math


def current_year() -> str:
    """Return the current calendar year as a string, e.g. '2026'."""
    return str(date.today().year)


def current_quarter() -> str:
    """Return the current quarter label, e.g. '2026-Q1'."""
    today = date.today()
    q = math.ceil(today.month / 3)
    return f"{today.year}-Q{q}"


def prior_year() -> str:
    """Return the previous calendar year as a string, e.g. '2025'."""
    return str(date.today().year - 1)


def prior_quarter() -> str:
    """Return the previous quarter label, e.g. '2025-Q4'."""
    today = date.today()
    q = math.ceil(today.month / 3)
    if q == 1:
        return f"{today.year - 1}-Q4"
    return f"{today.year}-Q{q - 1}"


def reference_date_iso() -> str:
    """Return today's date in ISO format, e.g. '2026-02-19'."""
    return date.today().isoformat()
