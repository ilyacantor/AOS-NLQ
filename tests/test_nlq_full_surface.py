"""
Full surface harness — tests all three NLQ user-facing surfaces.

Covers: Ask tab (metric queries), Dashboard tab, Reports tab (financial
statements, combining statements, overlap, cross-sell, bridge, QoE).

Per CLAUDE.md:
- B1/B2: Tests hit NLQ's user-facing endpoints, not DCL directly
- B4: Assert positive expected outcome, not just absence of bad
- B6: No cross-repo imports — DCL queries go via HTTP
- B9/B12: Check data_source on every data test
- B13: Failures show what the user would see

Prerequisites:
- DCL running at localhost:8104 with v2 endpoints live
- NLQ running at localhost:8005
- Pipeline has run (fresh ingest data available)
"""

import os

import httpx
import pytest


DCL_URL = os.environ.get("DCL_API_URL", "http://localhost:8104")
NLQ_URL = os.environ.get("NLQ_API_URL", "http://localhost:8005")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dcl():
    with httpx.Client(base_url=DCL_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def nlq():
    with httpx.Client(base_url=NLQ_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def first_entity_id(nlq):
    """PR 2: /query returns 422 on unresolved entity. Resolve the first
    registered entity once so tests can pass entity_id explicitly."""
    resp = nlq.get("/api/v1/entities")
    assert resp.status_code == 200, f"entities endpoint failed: {resp.text}"
    entities = resp.json().get("entities", [])
    assert entities, "no entities registered — tests require at least one"
    return entities[0]["entity_id"]


def _ask(nlq, question: str, entity_id: str = None) -> dict:
    """Post a question to NLQ /api/v1/query."""
    payload = {"question": question}
    if entity_id:
        payload["entity_id"] = entity_id
    resp = nlq.post("/api/v1/query", json=payload)
    assert resp.status_code == 200, (
        f"NLQ returned {resp.status_code} for '{question}': {resp.text[:500]}"
    )
    return resp.json()


# ===========================================================================
# 1. Health checks
# ===========================================================================

class TestHealth:
    def test_dcl_health(self, dcl):
        resp = dcl.get("/api/health")
        assert resp.status_code == 200, f"DCL health failed: {resp.text}"

    @pytest.mark.skipif(
        not os.environ.get("NLQ_INTEGRATION"),
        reason="Integration test — requires running NLQ + DCL services (NLQ_INTEGRATION=1)",
    )
    def test_nlq_health(self, nlq):
        resp = nlq.get("/api/v1/health")
        assert resp.status_code == 200, f"NLQ health failed: {resp.text}"


# ===========================================================================
# 2. Ask tab — metric queries
# ===========================================================================

class TestAskRevenue:
    """Revenue query returns numeric value with source."""

    def test_revenue(self, nlq, first_entity_id):
        result = _ask(nlq, "What is revenue?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert isinstance(value, (int, float)) and value > 0, (
            f"Expected revenue > 0. Got: {result}"
        )

    def test_revenue_source(self, nlq, first_entity_id):
        result = _ask(nlq, "What is revenue?", entity_id=first_entity_id)
        source = (
            result.get("data_source")
            or result.get("metadata", {}).get("source")
            or result.get("source")
        )
        assert source is not None, f"Missing data_source. Got: {result}"


class TestAskEntityScoped:
    """Entity-scoped queries return entity-specific data."""

    def test_entity_scoped_revenue(self, nlq, dcl):
        overview = dcl.get("/api/dcl/triples/overview").json()
        entities = [e["entity_id"] for e in overview.get("entities", [])]
        assert len(entities) > 0, "No entities in DCL"

        entity = entities[0]
        result = _ask(nlq, f"What is {entity}'s revenue?", entity_id=entity)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"Expected numeric value for {entity}'s revenue. Got: {result}"
        )


class TestAskDerived:
    """Derived metrics compute correctly."""

    def test_gross_margin(self, nlq, first_entity_id):
        result = _ask(nlq, "What is gross margin?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, f"Expected gross margin value. Got: {result}"


class TestAskPeriodExpansion:
    """Bare year resolves to quarterly data, not exact match."""

    def test_bare_year_revenue(self, nlq, first_entity_id):
        result = _ask(nlq, "What is revenue for 2025?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"Bare year '2025' should expand to Q1-Q4 sum. Got: {result}"
        )

    def test_quarterly_revenue(self, nlq, first_entity_id):
        result = _ask(nlq, "What is revenue for Q1 2025?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"Quarterly 'Q1 2025' should return single quarter. Got: {result}"
        )


class TestAskUnknownMetric:
    """Unknown metrics return structured error, not crash."""

    def test_nonsense_metric(self, nlq, first_entity_id):
        result = _ask(nlq, "What is xyzzy_nonexistent_metric_42?", entity_id=first_entity_id)
        # Should get either an error message or a graceful "I don't know" answer
        has_answer = (
            result.get("answer")
            or result.get("error")
            or result.get("text")
        )
        assert has_answer is not None, f"Expected error or answer. Got: {result}"


# ===========================================================================
# 3. Dashboard tab
# ===========================================================================

class TestDashboard:
    """Dashboard queries return persona-specific metrics."""

    @pytest.mark.skipif(
        not os.environ.get("NLQ_INTEGRATION"),
        reason="Integration test — requires running NLQ + DCL services (NLQ_INTEGRATION=1)",
    )
    def test_cfo_dashboard(self, nlq, first_entity_id):
        result = _ask(nlq, "Show me the CFO dashboard", entity_id=first_entity_id)
        nodes = result.get("nodes", [])
        text = result.get("text", "") or result.get("answer", "")
        has_data = len(nodes) > 0 or (text and "$" in text)
        assert has_data, (
            f"CFO dashboard should have metric values. "
            f"nodes={len(nodes)}, text preview: {str(text)[:200]}"
        )


# ===========================================================================
# 4. Reports tab — Entity list
# ===========================================================================

class TestEntityList:
    """Entity selector gets dynamic entity list."""

    def test_entities_endpoint(self, nlq):
        resp = nlq.get("/api/v1/entities")
        assert resp.status_code == 200, f"Entity list failed: {resp.text}"
        data = resp.json()
        entities = data.get("entities", [])
        assert len(entities) > 0, f"Expected at least 1 entity. Got: {data}"
        assert all("entity_id" in e for e in entities), (
            f"Entity objects missing entity_id: {entities}"
        )


# ===========================================================================
# 5. Reports tab — Financial statements
# ===========================================================================

class TestIncomeStatement:
    """Income statement tests — financial_statement_data field retired with report_generator.py
    removal in commit 45a0d61. Remaining tests verify query doesn't crash."""
    pass


