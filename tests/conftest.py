"""
Pytest fixtures for AOS-NLQ tests.

Provides shared test fixtures including:
- test_questions: Ground truth test questions
- mock_claude_client: Mock Claude client for unit tests
- reference_date: Fixed date for reproducible tests
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

import pytest


# Fixed reference date for all tests - ensures reproducibility
REFERENCE_DATE = date(2026, 1, 27)


@pytest.fixture
def reference_date() -> date:
    """Fixed reference date for testing relative periods."""
    return REFERENCE_DATE


@pytest.fixture
def test_questions_path() -> Path:
    """Path to the test questions JSON file."""
    paths = [
        Path("data/nlq_test_questions.json"),
        Path("/home/user/AOS-NLQ/data/nlq_test_questions.json"),
        Path(__file__).parent.parent / "data" / "nlq_test_questions.json",
    ]
    for p in paths:
        if p.exists():
            return p
    pytest.skip("Test questions file not found")


@pytest.fixture
def test_questions(test_questions_path) -> Dict:
    """Loaded test questions with ground truth."""
    with open(test_questions_path, "r") as f:
        return json.load(f)


@pytest.fixture
def mock_claude_response():
    """Factory for mock Claude API responses."""
    def _make_response(
        intent: str = "POINT_QUERY",
        metric: str = "revenue",
        period_type: str = "annual",
        period_reference: str = "2024",
        is_relative: bool = False
    ) -> Dict:
        return {
            "intent": intent,
            "metric": metric,
            "period_type": period_type,
            "period_reference": period_reference,
            "is_relative": is_relative
        }
    return _make_response


@pytest.fixture
def mock_claude_client(mock_claude_response):
    """Mock Claude client for unit tests (no API calls)."""
    client = MagicMock()
    client.parse_query.return_value = mock_claude_response()
    return client


@pytest.fixture
def period_resolver(reference_date):
    """PeriodResolver instance with fixed reference date."""
    from src.nlq.core.resolver import PeriodResolver
    return PeriodResolver(reference_date=reference_date)


@pytest.fixture
def confidence_calculator():
    """ConfidenceCalculator instance."""
    from src.nlq.core.confidence import ConfidenceCalculator
    return ConfidenceCalculator()
