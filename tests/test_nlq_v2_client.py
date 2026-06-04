"""
Tests for DCL semantic client v2 — triple-based endpoints.

Per CLAUDE.md:
- B1/B2: Tests hit NLQ's /api/v1/query (user-facing), not DCL directly
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
import subprocess
import sys

import httpx
import pytest


DCL_URL = os.environ.get("DCL_API_URL", "http://localhost:8104")
NLQ_URL = os.environ.get("NLQ_API_URL", "http://localhost:8005")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dcl_client():
    """HTTP client for DCL v2 endpoint cross-checks (not the primary test path)."""
    with httpx.Client(base_url=DCL_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def nlq_client():
    """HTTP client for NLQ user-facing endpoint."""
    with httpx.Client(base_url=NLQ_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="module")
def first_entity_id(nlq_client):
    """PR 2: questions with no entity in text now 422. Resolve the first
    registered entity once so every test can pass an explicit entity_id."""
    resp = nlq_client.get("/api/v1/entities")
    assert resp.status_code == 200, f"entities endpoint failed: {resp.text}"
    entities = resp.json().get("entities", [])
    assert entities, "no entities registered — v2 client tests require at least one"
    return entities[0]["entity_id"]


@pytest.fixture(scope="module")
def tenant_id(nlq_client, first_entity_id):
    """R3: DCL /triples/browse endpoints now require tenant_id for scoping.
    Resolve the demo tenant from an NLQ response — NLQ echoes the I2 pair."""
    resp = nlq_client.post(
        "/api/v1/query",
        json={"question": "What is revenue?", "entity_id": first_entity_id},
    )
    assert resp.status_code == 200, (
        f"NLQ query failed while resolving tenant_id: {resp.text[:300]}"
    )
    tid = resp.json().get("tenant_id")
    assert tid, "NLQ response carried no tenant_id — cannot scope DCL browse (I2)"
    return tid


def _nlq_query(nlq_client, question: str, entity_id: str = None) -> dict:
    """Post a natural language question to NLQ and return the response."""
    payload = {"question": question}
    if entity_id:
        payload["entity_id"] = entity_id
    resp = nlq_client.post("/api/v1/query", json=payload)
    assert resp.status_code == 200, (
        f"NLQ returned {resp.status_code} for '{question}': {resp.text[:500]}"
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

class TestHealthChecks:
    """D2: Verify health first."""

    def test_dcl_health(self, dcl_client):
        resp = dcl_client.get("/api/health")
        assert resp.status_code == 200, f"DCL health check failed: {resp.text}"

    def test_nlq_health(self, nlq_client):
        resp = nlq_client.get("/api/v1/health")
        assert resp.status_code == 200, f"NLQ health check failed: {resp.text}"


# ---------------------------------------------------------------------------
# 1. Revenue query
# ---------------------------------------------------------------------------

class TestRevenueQuery:
    """get_metric('revenue') returns value > 0 with confidence and source."""

    def test_revenue_via_nlq(self, nlq_client, first_entity_id):
        result = _nlq_query(nlq_client, "What is revenue?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"User asked 'What is revenue?'. Expected: numeric value > 0. "
            f"Got: {result}"
        )
        assert isinstance(value, (int, float)), (
            f"User asked 'What is revenue?'. Expected numeric value. Got type: {type(value)}"
        )
        assert value > 0, (
            f"User asked 'What is revenue?'. Expected value > 0. Got: {value}"
        )
        # B12: source field check
        source = (
            result.get("data_source")
            or result.get("metadata", {}).get("source")
            or result.get("source")
        )
        assert source is not None and "fact_base" not in str(source).lower(), (
            f"User asked 'What is revenue?'. "
            f"Expected data_source='dcl_v2' or 'dcl'. Got source='{source}'"
        )

    def test_revenue_via_dcl_triples(self, dcl_client, tenant_id):
        """Cross-check: DCL v2 triples have revenue data."""
        resp = dcl_client.get("/api/dcl/triples/browse", params={
            "tenant_id": tenant_id,
            "domain": "revenue",
            "property": "amount",
            "limit": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        triples = data.get("triples", [])
        assert len(triples) > 0, (
            "DCL v2 /triples/browse returned zero triples for domain=revenue, property=amount"
        )


# ---------------------------------------------------------------------------
# 2. Entity-scoped query
# ---------------------------------------------------------------------------

class TestEntityScoped:
    """get_metric('revenue', entity_id='...') returns entity-specific revenue."""

    def test_entity_scoped_via_nlq(self, nlq_client, first_entity_id):
        # Pick the entity from NLQ's own entity list (first_entity_id), the
        # queryable, DCL-sourced, richest-first roster NLQ exposes — the same source
        # the sibling tests use. The raw DCL /triples/overview ranks by is_active
        # triple count, which in the pre-rebuild dev store surfaces stale "ghost"
        # entities (flagged-active triples no longer in any current run, e.g.
        # finops-demo-co) that NLQ correctly answers as "insufficient data". Those
        # are not a valid target for an entity-scoped answerability check. Ghost
        # exclusion from the roster is a post-store-rebuild cleanup — see
        # nlq_deferred_work.md.
        entity = first_entity_id
        result = _nlq_query(
            nlq_client,
            f"What is {entity}'s revenue?",
            entity_id=entity,
        )
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"User asked 'What is {entity}'s revenue?'. "
            f"Expected: numeric value. Got: {result}"
        )


# ---------------------------------------------------------------------------
# 3. Derived metric
# ---------------------------------------------------------------------------

class TestDerivedMetric:
    """get_derived_metric('gross_margin_pct') returns a percentage."""

    def test_gross_margin_via_nlq(self, nlq_client, first_entity_id):
        result = _nlq_query(nlq_client, "What is gross margin?", entity_id=first_entity_id)
        value = result.get("value") or result.get("data", {}).get("value")
        assert value is not None, (
            f"User asked 'What is gross margin?'. Expected: numeric value. Got: {result}"
        )
        # B12: source field
        source = (
            result.get("data_source")
            or result.get("metadata", {}).get("source")
            or result.get("source")
        )
        assert source is not None and "fact_base" not in str(source).lower(), (
            f"User asked 'What is gross margin?'. "
            f"Expected data_source from DCL. Got source='{source}'"
        )


# ---------------------------------------------------------------------------
# 4. Dashboard metrics
# ---------------------------------------------------------------------------

class TestDashboardMetrics:
    """get_dashboard_metrics('CFO') returns multiple metrics with values."""

    def test_cfo_dashboard_via_nlq(self, nlq_client, first_entity_id):
        result = _nlq_query(nlq_client, "Show me the CFO dashboard", entity_id=first_entity_id)
        # Dashboard responses return structured dashboard with widgets
        dashboard = result.get("dashboard")
        assert dashboard is not None, (
            f"User asked 'Show me the CFO dashboard'. "
            f"Expected: dashboard object with widgets. Got keys: {list(result.keys())}"
        )
        widgets = dashboard.get("widgets", [])
        assert len(widgets) > 0, (
            f"User asked 'Show me the CFO dashboard'. "
            f"Expected: dashboard with metric widgets. Got 0 widgets. "
            f"Dashboard: {str(dashboard)[:300]}"
        )
        # B12: source field check
        source = (
            result.get("data_source")
            or result.get("source")
        )
        assert source is not None, (
            f"User asked 'Show me the CFO dashboard'. "
            f"Expected data_source field present. Got source='{source}'"
        )


# ---------------------------------------------------------------------------
# 5. Income statement
# ---------------------------------------------------------------------------

class TestIncomeStatement:
    """Removed: tested DCL Convergence endpoint (/api/dcl/reports/v2/combining/income-statement)
    from NLQ repo — RACI violation. Convergence endpoints belong in Convergence test suite."""
    pass


# ---------------------------------------------------------------------------
# 6. Metric mapping completeness
# ---------------------------------------------------------------------------

class TestMetricMapping:
    """Every metric in metric_concept_map.yaml resolves to a valid concept."""

    def test_all_metrics_in_map_resolve(self):
        """Verify the YAML loads and every entry has required fields."""
        from src.nlq.services.dcl_semantic_client_v2 import METRIC_CONCEPT_MAP

        assert len(METRIC_CONCEPT_MAP) > 0, "Metric concept map is empty"

        for metric_name, defn in METRIC_CONCEPT_MAP.items():
            assert "type" in defn, f"Metric '{metric_name}' missing 'type' field"
            if defn["type"] == "direct":
                assert "concept" in defn, f"Direct metric '{metric_name}' missing 'concept'"
                assert "property" in defn, f"Direct metric '{metric_name}' missing 'property'"
            elif defn["type"] == "derived":
                assert "formula" in defn, f"Derived metric '{metric_name}' missing 'formula'"
                assert "components" in defn, f"Derived metric '{metric_name}' missing 'components'"
                for i, comp in enumerate(defn["components"]):
                    assert "concept" in comp, (
                        f"Derived metric '{metric_name}' component {i} missing 'concept'"
                    )
                    assert "property" in comp, (
                        f"Derived metric '{metric_name}' component {i} missing 'property'"
                    )

    def test_metric_concepts_exist_in_dcl(self, dcl_client):
        """Verify direct metrics' domains exist in DCL triples."""
        from src.nlq.services.dcl_semantic_client_v2 import METRIC_CONCEPT_MAP

        overview = dcl_client.get("/api/dcl/triples/overview").json()
        available_domains = {d["domain"] for d in overview.get("domains", [])}

        missing = []
        for metric_name, defn in METRIC_CONCEPT_MAP.items():
            if defn["type"] == "direct":
                domain = defn["concept"].split(".")[0]
                if domain not in available_domains:
                    missing.append(f"{metric_name} → domain '{domain}'")

        # Some domains may not have data (service, bench, etc.) — that's OK
        # But core financial domains MUST exist
        core_domains = {"revenue", "cogs", "opex", "pnl", "asset", "liability", "employee"}
        core_missing = [m for m in missing if m.split("→")[1].strip().strip("'") in core_domains]
        assert len(core_missing) == 0, (
            f"Core metric domains missing from DCL triples: {core_missing}. "
            f"Available domains: {sorted(available_domains)}"
        )


# ---------------------------------------------------------------------------
# 7. Missing metric error
# ---------------------------------------------------------------------------

class TestMissingMetric:
    """get_metric('nonexistent_metric') returns structured error, not silent fallback."""

    def test_unknown_metric_returns_error(self):
        """V2 client raises ValueError for unknown metrics."""
        from src.nlq.services.dcl_semantic_client_v2 import DCLSemanticClientV2

        client = DCLSemanticClientV2.__new__(DCLSemanticClientV2)
        client.base_url = DCL_URL
        client._http = httpx.Client(base_url=DCL_URL, timeout=30.0)

        with pytest.raises(ValueError, match="Unknown metric"):
            client.get_metric("nonexistent_metric_xyz_12345")

        client._http.close()


# ---------------------------------------------------------------------------
# 8. No hardcoded semantic data in v2 client
# ---------------------------------------------------------------------------

class TestNoHardcodedData:
    """Grep DCLSemanticClientV2 for _HIERARCHY, _SYSTEM_MAP, _DIMENSION_SYSTEM → zero hits."""

    def test_no_hardcoded_hierarchy(self):
        source = open(
            os.path.join(
                os.path.dirname(__file__),
                "..", "src", "nlq", "services", "dcl_semantic_client_v2.py"
            )
        ).read()
        assert "_HIERARCHY" not in source, (
            "DCLSemanticClientV2 contains hardcoded _HIERARCHY — "
            "hierarchy data belongs in DCL (RACI)"
        )
        assert "_SYSTEM_MAP" not in source, (
            "DCLSemanticClientV2 contains hardcoded _SYSTEM_MAP — "
            "system-of-record data belongs in DCL (RACI)"
        )
        assert "_DIMENSION_SYSTEM" not in source, (
            "DCLSemanticClientV2 contains hardcoded _DIMENSION_SYSTEM — "
            "dimension system data belongs in DCL (RACI)"
        )
