"""
Unit tests for period resolution.

CRITICAL: Tests verify that relative dates resolve based on
injected reference_date, NOT system time.

Tests cover:
- last_year, this_year resolution
- last_quarter, this_quarter resolution
- Edge case: Q1 "last quarter" -> Q4 previous year
- Absolute period parsing
"""

import pytest
from datetime import date

from src.nlq.core.resolver import PeriodResolver


class TestPeriodResolver:
    """Tests for PeriodResolver."""

    def test_last_year_resolution(self, reference_date):
        """Test 'last year' resolves to previous year."""
        resolver = PeriodResolver(reference_date=reference_date)  # 2026-01-27

        result = resolver.resolve("last_year")

        assert result["type"] == "annual"
        assert result["year"] == 2025

    def test_this_year_resolution(self, reference_date):
        """Test 'this year' resolves to current year."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("this_year")

        assert result["type"] == "annual"
        assert result["year"] == 2026

    def test_last_quarter_from_q1(self, reference_date):
        """Test 'last quarter' from Q1 resolves to Q4 of previous year."""
        # Reference date is January 2026 (Q1)
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("last_quarter")

        assert result["type"] == "quarterly"
        assert result["year"] == 2025
        assert result["quarter"] == 4

    def test_last_quarter_from_q2(self):
        """Test 'last quarter' from Q2 resolves to Q1 same year."""
        resolver = PeriodResolver(reference_date=date(2026, 4, 15))  # Q2

        result = resolver.resolve("last_quarter")

        assert result["type"] == "quarterly"
        assert result["year"] == 2026
        assert result["quarter"] == 1

    def test_this_quarter_resolution(self, reference_date):
        """Test 'this quarter' resolves correctly."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("this_quarter")

        assert result["type"] == "quarterly"
        assert result["year"] == 2026
        assert result["quarter"] == 1

    def test_prior_year_synonym(self, reference_date):
        """Test 'prior year' is a synonym for 'last year'."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("prior_year")

        assert result["type"] == "annual"
        assert result["year"] == 2025

    def test_previous_quarter_synonym(self, reference_date):
        """Test 'previous quarter' is a synonym for 'last quarter'."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("previous_quarter")

        assert result["type"] == "quarterly"
        assert result["year"] == 2025
        assert result["quarter"] == 4

    def test_absolute_year_parsing(self, reference_date):
        """Test parsing absolute year."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("2024")

        assert result["type"] == "annual"
        assert result["year"] == 2024

    def test_absolute_quarter_format_q4_2025(self, reference_date):
        """Test parsing 'Q4 2025' format."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("Q4 2025")

        assert result["type"] == "quarterly"
        assert result["year"] == 2025
        assert result["quarter"] == 4

    def test_absolute_quarter_format_2025_q4(self, reference_date):
        """Test parsing '2025-Q4' format."""
        resolver = PeriodResolver(reference_date=reference_date)

        result = resolver.resolve("2025-Q4")

        assert result["type"] == "quarterly"
        assert result["year"] == 2025
        assert result["quarter"] == 4

    def test_to_period_key_annual(self, reference_date):
        """Test converting annual resolution to period key."""
        resolver = PeriodResolver(reference_date=reference_date)
        resolved = resolver.resolve("2024")

        key = resolver.to_period_key(resolved)

        assert key == "2024"

    def test_to_period_key_quarterly(self, reference_date):
        """Test converting quarterly resolution to period key."""
        resolver = PeriodResolver(reference_date=reference_date)
        resolved = resolver.resolve("Q4 2025")

        key = resolver.to_period_key(resolved)

        assert key == "2025-Q4"

    def test_uses_injected_date_not_system_time(self):
        """
        CRITICAL: Verify resolver uses injected date, not system time.

        This is essential for reproducible tests and correct behavior.
        """
        # Use a specific date far in the past
        old_date = date(2020, 6, 15)  # Q2 2020
        resolver = PeriodResolver(reference_date=old_date)

        result = resolver.resolve("this_year")
        assert result["year"] == 2020

        result = resolver.resolve("last_year")
        assert result["year"] == 2019

        result = resolver.resolve("this_quarter")
        assert result["year"] == 2020
        assert result["quarter"] == 2
