"""
Maestra Engagement API — integration tests.

Tests per session2_engagement_api.md harness specification:
  1. Create engagement via API, assert 201, assert data matches
  2. Read engagement back, assert match
  3. Update deal_phase, assert persisted
  4. Add 3 session memory entries, read back, assert newest-first order
  5. Set module state cache for 'aod', read back, assert match
  6. Create plan with status 'pending', assert in getPendingPlans
  7. Approve plan, assert status='approved', approved_by set
  8. Log interaction, query via API, assert row exists with correct fields
  9. Read seed Meridian/Cascadia engagement, assert scenario_type='convergence'
  10. Attempt create with invalid scenario_type, assert rejection

Rules: hits real Supabase (no mocks), cleans up test data, no xfail.
"""

import uuid
import pytest
import httpx

# Base URL — NLQ runs on port 8005 locally (per CLAUDE.md port table)
# Falls back to 8000 (the default in config.py)
BASE_URL = "http://localhost:8005"

# Unique test customer ID — cleaned up after each test run
TEST_CUSTOMER_ID = str(uuid.uuid4())
# Well-known seed customer ID from the migration
SEED_CUSTOMER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def client():
    """HTTP client scoped to the test module."""
    with httpx.Client(base_url=BASE_URL, timeout=15) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def cleanup(client):
    """Clean up test data after all tests in this module."""
    yield
    # Cleanup: delete test engagement and cascading data
    # Since Supabase doesn't cascade deletes via REST, delete children first
    # Use the engagement service directly via the API (no direct DB access needed)
    # We rely on the test customer_id being unique enough not to collide
    try:
        # Delete plans for test customer
        plans = client.get(f"/maestra/plans/{TEST_CUSTOMER_ID}")
        if plans.status_code == 200 and plans.json():
            for plan in plans.json():
                client.put(
                    f"/maestra/plans/{plan['id']}/status",
                    json={"status": "rejected", "result_summary": "test cleanup"},
                )
        # Note: session_memory, interaction_log, module_state_cache don't have
        # delete endpoints — they'll be orphaned but harmless with the unique
        # test customer_id. The engagement itself can't be deleted via API
        # (no DELETE endpoint specified in session2 doc).
    except Exception:
        pass


@pytest.fixture(scope="module")
def health_check(client):
    """Verify NLQ is running before tests."""
    try:
        r = client.get("/api/v1/health")
        if r.status_code != 200:
            pytest.skip(
                f"NLQ server at {BASE_URL} returned {r.status_code} — "
                f"start NLQ before running engagement tests"
            )
    except httpx.ConnectError:
        pytest.skip(
            f"NLQ server not reachable at {BASE_URL} — "
            f"start NLQ before running engagement tests"
        )


class TestEngagementCRUD:
    """Tests 1-3: Create, read, update engagement."""

    def test_01_create_engagement(self, client, health_check):
        """Test 1: Create a new customer engagement via API."""
        payload = {
            "customer_id": TEST_CUSTOMER_ID,
            "customer_name": "Test Corp",
            "scenario_type": "single",
            "deal_phase": "discovery",
        }
        r = client.post("/maestra/engagement", json=payload)
        assert r.status_code == 201, (
            f"Expected 201 for engagement creation, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["customer_id"] == TEST_CUSTOMER_ID
        assert data["customer_name"] == "Test Corp"
        assert data["scenario_type"] == "single"
        assert data["deal_phase"] == "discovery"
        assert data["onboarding_complete"] is False

    def test_02_read_engagement(self, client, health_check):
        """Test 2: Read the engagement back, assert it matches."""
        r = client.get(f"/maestra/engagement/{TEST_CUSTOMER_ID}")
        assert r.status_code == 200, (
            f"Expected 200 for engagement read, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["customer_id"] == TEST_CUSTOMER_ID
        assert data["customer_name"] == "Test Corp"
        assert data["scenario_type"] == "single"
        assert data["deal_phase"] == "discovery"

    def test_03_update_deal_phase(self, client, health_check):
        """Test 3: Update deal_phase, assert persisted."""
        r = client.put(
            f"/maestra/engagement/{TEST_CUSTOMER_ID}",
            json={"deal_phase": "connection"},
        )
        assert r.status_code == 200, (
            f"Expected 200 for engagement update, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["deal_phase"] == "connection"

        # Verify persistence by reading back
        r2 = client.get(f"/maestra/engagement/{TEST_CUSTOMER_ID}")
        assert r2.json()["deal_phase"] == "connection"


class TestSessionMemory:
    """Test 4: Add and read session memory entries."""

    def test_04_session_memory_ordering(self, client, health_check):
        """Test 4: Add 3 entries, read back, assert newest-first and count."""
        session_id = str(uuid.uuid4())

        entries = [
            {
                "interaction_type": "onboarding",
                "user_message_summary": "First message",
                "maestra_action": "initiated_onboarding",
                "module_context": ["aod"],
            },
            {
                "interaction_type": "status_check",
                "user_message_summary": "Second message",
                "maestra_action": "checked_aod_status",
                "module_context": ["aod", "aam"],
            },
            {
                "interaction_type": "analysis",
                "user_message_summary": "Third message",
                "maestra_action": "ran_analysis",
                "module_context": ["dcl"],
            },
        ]

        for entry in entries:
            r = client.post(
                f"/maestra/memory/{TEST_CUSTOMER_ID}?session_id={session_id}",
                json=entry,
            )
            assert r.status_code == 201, (
                f"Expected 201 for memory add, got {r.status_code}: {r.text}"
            )

        # Read back
        r = client.get(f"/maestra/memory/{TEST_CUSTOMER_ID}?limit=10")
        assert r.status_code == 200
        memories = r.json()
        assert len(memories) >= 3, (
            f"Expected at least 3 memory entries, got {len(memories)}"
        )

        # Assert newest first (third message should be first)
        assert memories[0]["user_message_summary"] == "Third message"
        assert memories[1]["user_message_summary"] == "Second message"
        assert memories[2]["user_message_summary"] == "First message"


class TestModuleState:
    """Test 5: Module state cache."""

    def test_05_module_state_cache(self, client, health_check):
        """Test 5: Set module state for 'aod', read back, assert match."""
        state = {
            "state_json": {
                "status": "healthy",
                "assets_discovered": 42,
                "last_scan": "2026-03-01T00:00:00Z",
            }
        }
        r = client.put(
            f"/maestra/module-state/aod/{TEST_CUSTOMER_ID}",
            json=state,
        )
        assert r.status_code == 200, (
            f"Expected 200 for module state set, got {r.status_code}: {r.text}"
        )

        # Read back
        r2 = client.get(f"/maestra/module-state/aod/{TEST_CUSTOMER_ID}")
        assert r2.status_code == 200
        data = r2.json()
        assert data["module"] == "aod"
        assert data["customer_id"] == TEST_CUSTOMER_ID
        assert data["state_json"]["status"] == "healthy"
        assert data["state_json"]["assets_discovered"] == 42


class TestPlans:
    """Tests 6-7: Create and approve plans."""

    _plan_id: str = ""

    def test_06_create_plan_pending(self, client, health_check):
        """Test 6: Create plan with status 'pending', assert in getPendingPlans."""
        payload = {
            "customer_id": TEST_CUSTOMER_ID,
            "plan_type": "action_dispatch",
            "title": "Test AOD scan",
            "rationale": "Need fresh asset discovery for Test Corp",
            "affected_modules": ["aod", "aam"],
            "plan_body": {
                "action": "trigger_scan",
                "target": "all_endpoints",
            },
        }
        r = client.post("/maestra/plans", json=payload)
        assert r.status_code == 201, (
            f"Expected 201 for plan creation, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["status"] == "pending"
        assert data["title"] == "Test AOD scan"
        TestPlans._plan_id = data["id"]

        # Verify it appears in pending plans
        r2 = client.get(f"/maestra/plans/{TEST_CUSTOMER_ID}")
        assert r2.status_code == 200
        plans = r2.json()
        plan_ids = [p["id"] for p in plans]
        assert TestPlans._plan_id in plan_ids, (
            f"Created plan {TestPlans._plan_id} not found in pending plans"
        )

    def test_07_approve_plan(self, client, health_check):
        """Test 7: Approve plan, assert status changed, approved_by set."""
        assert TestPlans._plan_id, "Plan not created in test_06"

        r = client.put(
            f"/maestra/plans/{TestPlans._plan_id}/status",
            json={"status": "approved", "approved_by": "ilya@autonomos.ai"},
        )
        assert r.status_code == 200, (
            f"Expected 200 for plan approval, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["status"] == "approved"
        assert data["approved_by"] == "ilya@autonomos.ai"
        assert data["approved_at"] is not None


class TestInteractionLog:
    """Test 8: Log interaction."""

    def test_08_log_interaction(self, client, health_check):
        """Test 8: Log interaction via API, verify row exists with correct fields."""
        session_id = str(uuid.uuid4())
        entry = {
            "customer_id": TEST_CUSTOMER_ID,
            "session_id": session_id,
            "input_hash": "abc123hash",
            "model_used": "claude-sonnet-4-6",
            "input_tokens": 1500,
            "output_tokens": 800,
            "latency_ms": 2340,
            "interaction_type": "analysis",
            "action_dispatched": "query_dcl",
        }
        r = client.post("/maestra/interactions", json=entry)
        assert r.status_code == 201, (
            f"Expected 201 for interaction log, got {r.status_code}: {r.text}"
        )
        result = r.json()

        assert result["customer_id"] == TEST_CUSTOMER_ID
        assert result["model_used"] == "claude-sonnet-4-6"
        assert result["input_tokens"] == 1500
        assert result["output_tokens"] == 800
        assert result["latency_ms"] == 2340
        assert result["interaction_type"] == "analysis"
        assert result["action_dispatched"] == "query_dcl"
        assert result["input_hash"] == "abc123hash"
        assert result["id"] is not None  # UUID was generated


class TestSeedData:
    """Test 9: Verify seed data."""

    def test_09_seed_meridian_cascadia(self, client, health_check):
        """Test 9: Read seed engagement, assert scenario_type='convergence'."""
        r = client.get(f"/maestra/engagement/{SEED_CUSTOMER_ID}")
        assert r.status_code == 200, (
            f"Seed engagement not found. Did you run the migration? "
            f"Got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data["customer_name"] == "Demo: Meridian/Cascadia"
        assert data["scenario_type"] == "convergence"
        assert data["deal_phase"] == "analysis"
        assert data["acquirer_entity"] == "Meridian Holdings"
        assert data["target_entity"] == "Cascadia Partners"


class TestValidation:
    """Test 10: Invalid inputs rejected."""

    def test_10_invalid_scenario_type(self, client, health_check):
        """Test 10: Create engagement with invalid scenario_type, assert rejection."""
        payload = {
            "customer_id": str(uuid.uuid4()),
            "customer_name": "Invalid Corp",
            "scenario_type": "invalid_type",  # not in CHECK constraint
        }
        r = client.post("/maestra/engagement", json=payload)
        # The database CHECK constraint should reject this.
        # FastAPI/Supabase will return an error (400 or 500 depending on how
        # PostgREST surfaces the constraint violation).
        assert r.status_code != 201, (
            f"Expected rejection for invalid scenario_type, but got 201: {r.text}"
        )
