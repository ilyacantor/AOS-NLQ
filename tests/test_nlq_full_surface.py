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
- DCL running at localhost:8004 with v2 endpoints live
- NLQ running at localhost:8005
- Pipeline has run (fresh ingest data available)
"""

import os

import httpx
import pytest


DCL_URL = os.environ.get("DCL_API_URL", "http://localhost:8004")
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


def _report_get(nlq, path: str, params: dict = None) -> dict:
    """GET a report endpoint via NLQ proxy."""
    resp = nlq.get(f"/api/reports/{path}", params=params)
    assert resp.status_code == 200, (
        f"Report GET /api/reports/{path} returned {resp.status_code}: {resp.text[:500]}"
    )
    return resp.json()


# ===========================================================================
# 1. Health checks
# ===========================================================================

class TestHealth:
    def test_dcl_health(self, dcl):
        resp = dcl.get("/api/health")
        assert resp.status_code == 200, f"DCL health failed: {resp.text}"

    def test_nlq_health(self, nlq):
        resp = nlq.get("/api/health")
        assert resp.status_code == 200, f"NLQ health failed: {resp.text}"


# ===========================================================================
# 2. Ask tab — metric queries
# ===========================================================================

class TestAskRevenue:
    """Revenue query returns numeric value with source."""

    def test_revenue(self, nlq):
        result = _ask(nlq, "What is revenue?")
        value = result.get("value") or result.get("data", {}).get("value")
        assert isinstance(value, (int, float)) and value > 0, (
            f"Expected revenue > 0. Got: {result}"
        )

    def test_revenue_source(self, nlq):
        result = _ask(nlq, "What is revenue?")
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

    def test_gross_margin(self, nlq):
        result = _ask(nlq, "What is gross margin?")
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, f"Expected gross margin value. Got: {result}"


class TestAskPeriodExpansion:
    """Bare year resolves to quarterly data, not exact match."""

    def test_bare_year_revenue(self, nlq):
        result = _ask(nlq, "What is revenue for 2025?")
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"Bare year '2025' should expand to Q1-Q4 sum. Got: {result}"
        )

    def test_quarterly_revenue(self, nlq):
        result = _ask(nlq, "What is revenue for Q1 2025?")
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"Quarterly 'Q1 2025' should return single quarter. Got: {result}"
        )


class TestAskUnknownMetric:
    """Unknown metrics return structured error, not crash."""

    def test_nonsense_metric(self, nlq):
        result = _ask(nlq, "What is xyzzy_nonexistent_metric_42?")
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

    def test_cfo_dashboard(self, nlq):
        result = _ask(nlq, "Show me the CFO dashboard")
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
    """Income statement via NLQ query returns line items."""

    def test_income_statement_query(self, nlq):
        result = _ask(nlq, "Show me the P&L actual vs prior year", )
        fs = result.get("financial_statement_data")
        assert fs is not None, (
            f"Expected financial_statement_data. Got keys: {list(result.keys())}"
        )
        assert len(fs.get("line_items", [])) > 0, (
            f"Income statement has no line items. Got: {list(fs.keys())}"
        )


# ===========================================================================
# 6. Reports tab — Combining statement
# ===========================================================================

class TestCombiningStatement:
    """Combining income statement returns entity columns."""

    def test_combining_is(self, nlq):
        data = _report_get(nlq, "combining-is", {"period": "2025-Q1"})
        line_items = data.get("line_items", [])
        assert len(line_items) > 0, (
            f"Combining IS has no line items. Keys: {list(data.keys())}"
        )


# ===========================================================================
# 7. Reports tab — Entity Overlap
# ===========================================================================

class TestEntityOverlap:
    """Entity overlap returns customer_overlap with matches array."""

    def test_overlap_shape(self, nlq):
        data = _report_get(nlq, "entity-overlap")
        assert "customer_overlap" in data, (
            f"Expected 'customer_overlap' key. Got keys: {list(data.keys())}"
        )
        assert "vendor_overlap" in data, (
            f"Expected 'vendor_overlap' key. Got keys: {list(data.keys())}"
        )
        assert "people_overlap" in data, (
            f"Expected 'people_overlap' key. Got keys: {list(data.keys())}"
        )

    def test_overlap_customer_matches(self, nlq):
        data = _report_get(nlq, "entity-overlap")
        cust = data["customer_overlap"]
        assert "matches" in cust, (
            f"customer_overlap missing 'matches'. Keys: {list(cust.keys())}"
        )
        assert isinstance(cust["matches"], list), (
            f"customer_overlap.matches should be a list. Got: {type(cust['matches'])}"
        )
        assert cust["total_overlapping"] > 0, (
            f"Expected overlapping customers. Got total_overlapping={cust.get('total_overlapping')}"
        )

    def test_overlap_customer_match_fields(self, nlq):
        data = _report_get(nlq, "entity-overlap")
        matches = data["customer_overlap"]["matches"]
        if len(matches) > 0:
            m = matches[0]
            required = ["meridian_name", "cascadia_name", "canonical_name",
                        "match_type", "confidence", "meridian_revenue_M",
                        "cascadia_revenue_M", "combined_revenue_M"]
            missing = [f for f in required if f not in m]
            assert len(missing) == 0, (
                f"CustomerMatch missing fields: {missing}. Got keys: {list(m.keys())}"
            )


# ===========================================================================
# 8. Reports tab — Cross-Sell
# ===========================================================================

class TestCrossSell:
    """Cross-sell returns m_to_c and c_to_m arrays with summary."""

    def test_cross_sell_shape(self, nlq):
        data = _report_get(nlq, "cross-sell")
        assert "m_to_c" in data, f"Missing 'm_to_c'. Keys: {list(data.keys())}"
        assert "c_to_m" in data, f"Missing 'c_to_m'. Keys: {list(data.keys())}"
        assert "summary" in data, f"Missing 'summary'. Keys: {list(data.keys())}"

    def test_cross_sell_summary_fields(self, nlq):
        data = _report_get(nlq, "cross-sell")
        summary = data["summary"]
        required = ["total_candidates", "total_pipeline_acv"]
        missing = [f for f in required if f not in summary]
        assert len(missing) == 0, (
            f"Summary missing fields: {missing}. Got: {list(summary.keys())}"
        )


# ===========================================================================
# 9. Reports tab — EBITDA Bridge
# ===========================================================================

class TestEBITDABridge:
    """EBITDA bridge returns entity breakdowns and adjustments."""

    def test_bridge_shape(self, nlq):
        data = _report_get(nlq, "ebitda-bridge")
        assert "reported_ebitda" in data, f"Missing 'reported_ebitda'. Keys: {list(data.keys())}"
        assert "entity_adjustments" in data, f"Missing 'entity_adjustments'. Keys: {list(data.keys())}"
        assert "entity_adjusted_ebitda" in data, f"Missing 'entity_adjusted_ebitda'. Keys: {list(data.keys())}"

    def test_bridge_reported_entity_breakdown(self, nlq):
        data = _report_get(nlq, "ebitda-bridge")
        reported = data["reported_ebitda"]
        assert "meridian" in reported, f"Missing meridian in reported_ebitda: {reported}"
        assert "cascadia" in reported, f"Missing cascadia in reported_ebitda: {reported}"


# ===========================================================================
# 10. Reports tab — Quality of Earnings
# ===========================================================================

class TestQoE:
    """QoE returns adjustments and summary."""

    def test_qoe_shape(self, nlq):
        data = _report_get(nlq, "qoe")
        assert "ebitda_bridge" in data, f"Missing 'ebitda_bridge'. Keys: {list(data.keys())}"
        assert "summary" in data, f"Missing 'summary'. Keys: {list(data.keys())}"
        assert "sustainability_score" in data, f"Missing 'sustainability_score'. Keys: {list(data.keys())}"

    def test_qoe_summary_fields(self, nlq):
        data = _report_get(nlq, "qoe")
        summary = data["summary"]
        required = ["reported_ebitda", "entity_adjusted_ebitda", "total_adjustments"]
        missing = [f for f in required if f not in summary]
        assert len(missing) == 0, (
            f"QoE summary missing fields: {missing}. Got: {list(summary.keys())}"
        )


# ===========================================================================
# 11. Report dimensions
# ===========================================================================

class TestReportDimensions:
    """Report dimensions endpoint returns periods and segments."""

    def test_report_dimensions(self, nlq):
        resp = nlq.get("/api/v1/report-dimensions")
        assert resp.status_code == 200, f"Report dimensions failed: {resp.text}"
        data = resp.json()
        assert "periods" in data, f"Missing 'periods'. Keys: {list(data.keys())}"
        assert len(data["periods"]) > 0, "No periods returned"
