"""
Maestra test fixtures — shared prerequisites for all Maestra integration tests.
"""

import pytest
import httpx

BASE_URL = "http://localhost:8005"
SEED_CUSTOMER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def maestra_ready(client):
    """Verify Maestra prerequisites before running integration tests.

    Uses pytest.fail (not skip) — per HARNESS_RULES, missing infrastructure
    is a test failure, not a reason to skip.
    """
    try:
        r = client.get(f"/maestra/engagement/{SEED_CUSTOMER_ID}")
        if r.status_code != 200:
            pytest.fail(
                f"Maestra seed engagement not found (HTTP {r.status_code}). "
                f"Apply schema: psql $DATABASE_URL -f sql/maestra/001_maestra_schema.sql"
            )
    except httpx.ConnectError as e:
        pytest.fail(f"NLQ not reachable at {BASE_URL}: {e}")
