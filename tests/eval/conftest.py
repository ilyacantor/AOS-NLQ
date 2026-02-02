"""
Shared fixtures and configuration for evaluation tests.

CRITICAL: These tests must NOT mock DCL responses.
If DCL is unavailable, tests should FAIL, not skip silently.
"""

import os
import pytest
from typing import Optional


@pytest.fixture(scope="session")
def dcl_client():
    """
    Get real DCL semantic client.

    This fixture does NOT mock anything. It returns the real client
    that talks to real DCL (or uses local fallback in dev mode).
    """
    from src.nlq.services.dcl_semantic_client import get_semantic_client
    client = get_semantic_client()

    # Verify client can actually fetch catalog
    try:
        catalog = client.get_catalog()
        if not catalog.metrics:
            pytest.fail("DCL catalog has no metrics - is DCL running?")
    except Exception as e:
        pytest.fail(f"Failed to connect to DCL: {e}")

    return client


@pytest.fixture(scope="session")
def dcl_catalog(dcl_client):
    """Get DCL semantic catalog."""
    return dcl_client.get_catalog()


def collect_failures(failures: list) -> Optional[str]:
    """Format failure list for assertion message."""
    if not failures:
        return None
    return f"\n{len(failures)} failures:\n" + "\n".join(f"  - {f}" for f in failures)


@pytest.fixture
def failure_collector():
    """Fixture to collect and report multiple failures."""
    return collect_failures
