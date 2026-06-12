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
from dotenv import load_dotenv

# Load aos-dev config so the suite touches ONLY dev: DCL :8104, aos-dev
# Supabase. :8004 is PROD — never. override=True forces dev even if a prod
# value leaked into the shell, so `pytest` cannot accidentally hit prod.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.development", override=True)


# Fixed reference date for all tests - ensures reproducibility
REFERENCE_DATE = date(2026, 1, 27)


@pytest.fixture(autouse=True)
def _dcl_singleton_isolation():
    """Test isolation for the DCL client singletons.

    get_semantic_client / get_semantic_client_v2 / get_routed_client each cache a
    client built against whatever DCL_API_URL was set at first call. A test that
    monkeypatches DCL_API_URL (e.g. test_e2e_graph_resolution's `executor` fixture
    sets a mock URL, then QueryExecutor() -> get_routed_client() builds the v2/old
    clients against it) poisons those singletons for the rest of the session — so
    later tests doing a real browse get an unreachable client and no data
    (manifests as map_widget KeyError 'map_data', etc.).

    Before each test, drop any singleton whose target no longer matches the live
    DCL_API_URL so it is rebuilt against the real env. Cheap: resets only on a
    mismatch (the rare poisoned case), never on the common path.
    """
    import src.nlq.services.dcl_semantic_client as _v1
    import src.nlq.services.dcl_semantic_client_v2 as _v2
    import src.nlq.services.dcl_client_router as _router

    current = (os.environ.get("DCL_API_URL") or "").rstrip("/")
    v2c = getattr(_v2, "_v2_client", None)
    v1c = getattr(_v1, "_semantic_client", None)
    stale = (
        (v2c is not None and getattr(v2c, "base_url", current) != current)
        or (v1c is not None and getattr(v1c, "dcl_url", current) != current)
    )
    if stale:
        _v2._v2_client = None
        _v1._semantic_client = None
        _router._routed_client = None
    yield


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
