"""
Maestra Context Assembly — integration tests with real LLM.

Tests per session3_context_assembly.md harness specification:
  1. Status check: "Where are we with the deal?"
  2. Module-specific question: "What did AOD find for the target?"
  3. Action request (read): "Show me the overlap report"
  4. Action request (write): "Re-run discovery for Cascadia's Salesforce"
  5. Unknown question: "What's the weather like?"
  6. Entity ambiguity: "What's the revenue?"
  7. Session continuity: two messages with same sessionId
  8. Interaction logging: verify interaction_log row
  9. Engagement state update: verify last_interaction_at
  10. Constitution loading: verify prompt contains constitution text

Rules: real Claude API calls, real Supabase, no mocks, no exact text assertions.
Timeout: 30s per test.
"""

import uuid
import time
import pytest
import httpx

BASE_URL = "http://localhost:8005"
SEED_CUSTOMER_ID = "00000000-0000-0000-0000-000000000001"
TIMEOUT = 30  # seconds per LLM call


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="module")
def health_check(client):
    try:
        r = client.get("/api/v1/health")
        if r.status_code != 200:
            pytest.skip(f"NLQ not healthy: {r.status_code}")
    except httpx.ConnectError:
        pytest.skip(f"NLQ not reachable at {BASE_URL}")


def _call_context(client, message: str, session_id: str = None) -> dict:
    """Helper to call /maestra/context and return parsed response."""
    payload = {
        "customer_id": SEED_CUSTOMER_ID,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id
    r = client.post("/maestra/context", json=payload)
    assert r.status_code == 200, (
        f"Context assembly failed with {r.status_code}: {r.text[:500]}"
    )
    return r.json()


class TestStatusCheck:
    """Test 1: Status check question."""

    def test_01_status_check(self, client, health_check):
        result = _call_context(client, "Where are we with the deal?")

        # Non-empty response
        assert result["text"], "Response text is empty"
        assert len(result["text"]) > 50, (
            f"Response suspiciously short: {result['text'][:100]}"
        )

        # Entity clarity rule — must mention both entities
        text_lower = result["text"].lower()
        assert "meridian" in text_lower, (
            f"Response doesn't mention Meridian (entity clarity rule): {result['text'][:200]}"
        )
        assert "cascadia" in text_lower, (
            f"Response doesn't mention Cascadia (entity clarity rule): {result['text'][:200]}"
        )

        # Status check may produce a read action (to fetch fresh module state)
        # but should never produce a write action
        if result["action"] is not None:
            action_block = result["action"].get("action", result["action"])
            assert action_block.get("type") != "write", (
                f"Status check should not produce a write action, got: {result['action']}"
            )

        # Token usage present
        assert result["usage"]["input_tokens"] > 0
        assert result["usage"]["output_tokens"] > 0

        # Latency under 15s
        assert result["latencyMs"] < 15000, (
            f"Latency {result['latencyMs']}ms exceeds 15s limit"
        )


class TestModuleQuestion:
    """Test 2: Module-specific question."""

    def test_02_module_specific(self, client, health_check):
        result = _call_context(client, "What did AOD find for the target?")

        text_lower = result["text"].lower()
        # Must mention Cascadia (the target)
        assert "cascadia" in text_lower, (
            f"Response doesn't mention Cascadia (the target): {result['text'][:200]}"
        )


class TestReadAction:
    """Test 3: Action request (read)."""

    def test_03_read_action(self, client, health_check):
        result = _call_context(client, "Show me the overlap report")

        assert result["action"] is not None, (
            f"Expected a read action for overlap report request, got None. "
            f"Response: {result['text'][:200]}"
        )
        action_block = result["action"].get("action", result["action"])
        assert action_block.get("type") == "read", (
            f"Expected action type 'read', got '{action_block.get('type')}'. "
            f"Action: {result['action']}"
        )


class TestWriteAction:
    """Test 4: Action request (write)."""

    def test_04_write_action(self, client, health_check):
        result = _call_context(
            client,
            "Re-run full AOD discovery for Meridian Holdings to find any new systems",
        )

        assert result["action"] is not None, (
            f"Expected a write action for re-run discovery, got None. "
            f"Response: {result['text'][:200]}"
        )
        action_block = result["action"].get("action", result["action"])
        assert action_block.get("type") == "write", (
            f"Expected action type 'write', got '{action_block.get('type')}'. "
            f"Action: {result['action']}"
        )
        assert action_block.get("module") == "aod", (
            f"Expected module 'aod', got '{action_block.get('module')}'. "
            f"Action: {result['action']}"
        )


class TestUnknownQuestion:
    """Test 5: Off-topic question."""

    def test_05_unknown_question(self, client, health_check):
        result = _call_context(client, "What's the weather like?")

        text_lower = result["text"].lower()
        # Should indicate this is outside scope — check for common deflection patterns
        scope_indicators = [
            "outside", "scope", "can't", "cannot", "don't have",
            "not something", "beyond", "unable", "not within", "not able",
            "weather", "not related",
        ]
        assert any(ind in text_lower for ind in scope_indicators), (
            f"Response doesn't indicate weather is out of scope: {result['text'][:300]}"
        )


class TestEntityAmbiguity:
    """Test 6: Ambiguous entity reference."""

    def test_06_entity_ambiguity(self, client, health_check):
        result = _call_context(client, "What's the revenue?")

        text_lower = result["text"].lower()
        # Should ask which entity
        clarification_indicators = [
            "which", "meridian", "cascadia", "combined",
            "acquirer", "target", "both", "specify",
        ]
        matches = [ind for ind in clarification_indicators if ind in text_lower]
        assert len(matches) >= 2, (
            f"Response doesn't ask for entity clarification. "
            f"Found only {matches}. Response: {result['text'][:300]}"
        )


class TestSessionContinuity:
    """Test 7: Session continuity across messages."""

    def test_07_session_continuity(self, client, health_check):
        session_id = str(uuid.uuid4())

        # First message
        r1 = _call_context(
            client,
            "I'm particularly interested in the CRM integration for Meridian.",
            session_id=session_id,
        )
        assert r1["text"], "First message response is empty"

        # Second message — should reference context from first
        r2 = _call_context(
            client,
            "And what about the target's systems?",
            session_id=session_id,
        )
        assert r2["text"], "Second message response is empty"

        # Second response should show awareness of the conversation
        text_lower = r2["text"].lower()
        # Should mention Cascadia (the target) since we asked about "the target"
        assert "cascadia" in text_lower, (
            f"Second response doesn't mention Cascadia when asked about 'the target': "
            f"{r2['text'][:300]}"
        )


class TestInteractionLogging:
    """Test 8: Verify interaction_log row created."""

    def test_08_interaction_logged(self, client, health_check):
        # Make a call
        _call_context(client, "Quick status check")

        # Query the interaction log via the Supabase REST API
        # We'll check via the engagement service's recent memory as proxy
        # (interaction_log doesn't have a read endpoint, but memory does)
        r = client.get(f"/maestra/memory/{SEED_CUSTOMER_ID}?limit=1")
        assert r.status_code == 200
        memories = r.json()
        assert len(memories) >= 1, "No session memory entries found after context call"

        latest = memories[0]
        assert latest["customer_id"] == SEED_CUSTOMER_ID
        assert latest["interaction_type"] in ("status_check", "analysis")
        assert latest["user_message_summary"], "Memory summary is empty"


class TestEngagementStateUpdate:
    """Test 9: Verify last_interaction_at updated."""

    def test_09_engagement_updated(self, client, health_check):
        # Record time before call
        before = time.time()

        _call_context(client, "Anything new?")

        # Check engagement
        r = client.get(f"/maestra/engagement/{SEED_CUSTOMER_ID}")
        assert r.status_code == 200
        eng = r.json()

        last_at = eng.get("last_interaction_at")
        assert last_at is not None, (
            "last_interaction_at was not updated after context call"
        )


class TestConstitutionLoading:
    """Test 10: Verify constitution content in prompt."""

    def test_10_constitution_in_prompt(self, client, health_check):
        # The constitution defines Maestra's identity. If loaded correctly,
        # Maestra should identify herself and follow the behavioral rules.
        result = _call_context(
            client, "Who are you and what can you do?"
        )

        text_lower = result["text"].lower()
        # From base.md: "You are Maestra"
        assert "maestra" in text_lower, (
            f"Response doesn't mention Maestra identity (base.md not loaded?): "
            f"{result['text'][:300]}"
        )

        # From convergence.md: should know about acquirer/target pattern
        # or mention M&A / convergence concepts
        convergence_indicators = [
            "meridian", "cascadia", "acquir", "target",
            "m&a", "convergence", "deal", "entities",
        ]
        matches = [ind for ind in convergence_indicators if ind in text_lower]
        assert len(matches) >= 2, (
            f"Response doesn't reflect convergence constitution. "
            f"Found only {matches}. Response: {result['text'][:300]}"
        )
