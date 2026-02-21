"""
End-to-end integration tests for NLQ → DCL graph resolution pipeline.

Tests the full chain:
  NLQ parses intent → calls DCL resolve via graph → formats response → falls back to flat query

Uses mocked DCL graph responses to test the pipeline without a running DCL server.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from src.nlq.core.executor import QueryExecutor
from src.nlq.models.query import ParsedQuery, QueryIntent, PeriodType
from src.nlq.models.response import QueryResult
from src.nlq.services.dcl_semantic_client import DCLSemanticClient


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def mock_dcl_client():
    """DCL semantic client with mocked HTTP calls."""
    client = DCLSemanticClient(dcl_base_url="http://localhost:8001")
    client._http_client = MagicMock()
    return client


@pytest.fixture
def executor(mock_dcl_client):
    """QueryExecutor wired to mock DCL client."""
    ex = QueryExecutor()
    ex.dcl_client = mock_dcl_client
    return ex


def _make_parsed(
    metric="revenue",
    intent=QueryIntent.POINT_QUERY,
    period="2025-Q4",
    dimension=None,
    entity=None,
):
    """Helper to build a ParsedQuery."""
    return ParsedQuery(
        intent=intent,
        metric=metric,
        period_type=PeriodType.QUARTERLY,
        period_reference=period,
        resolved_period=period,
        dimension=dimension,
        entity=entity,
    )


def _graph_response(
    can_answer=True,
    confidence=0.85,
    concepts=None,
    warnings=None,
    provenance=None,
    join_paths=None,
    filters_resolved=None,
    data=None,
):
    """Helper to build a mock graph resolution response."""
    return {
        "can_answer": can_answer,
        "confidence": confidence,
        "resolved_concepts": concepts or [
            {"concept": "revenue", "system": "netsuite", "field": "SalesOrder.total", "confidence": 0.95}
        ],
        "warnings": warnings or [],
        "provenance": provenance or {"systems": ["netsuite"], "edges": ["normalizer"]},
        "join_paths": join_paths,
        "filters_resolved": filters_resolved,
        "data": data,
        "source": "dcl_graph",
    }


# =========================================================================
# Test: Basic concept lookup (simplest case)
# =========================================================================

class TestGraphBasicConcept:
    """Test: 'What is total revenue?' — basic concept lookup via graph."""

    def test_graph_resolves_single_concept(self, executor, mock_dcl_client):
        """Graph finds revenue in NetSuite with high confidence."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.95,
            concepts=[{
                "concept": "revenue",
                "system": "netsuite",
                "field": "SalesOrder.total",
                "confidence": 0.95,
                "value": 125_000_000,
            }],
        ))

        parsed = _make_parsed(metric="revenue")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.confidence >= 0.7
        assert result.query_type == "graph_resolution"
        assert result.value == 125_000_000
        mock_dcl_client.resolve_via_graph.assert_called_once_with(
            concepts=["revenue"], dimensions=None, filters=None,
        )

    def test_graph_returns_provenance(self, executor, mock_dcl_client):
        """Graph result includes provenance metadata."""
        provenance = {
            "systems": ["netsuite"],
            "edges": ["normalizer", "ontology"],
            "path": "revenue -> SalesOrder.total (NetSuite)",
        }
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            provenance=provenance,
            concepts=[{"concept": "revenue", "system": "netsuite", "value": 100}],
        ))

        parsed = _make_parsed(metric="revenue")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["provenance"] == provenance
        assert result.metadata["resolution_source"] == "dcl_graph"


# =========================================================================
# Test: Concept + dimension (single dimension)
# =========================================================================

class TestGraphWithDimension:
    """Test: 'Show me revenue by region' — concept + dimension."""

    def test_graph_with_dimension(self, executor, mock_dcl_client):
        """Graph resolves revenue sliced by region."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.85,
            data=[
                {"region": "AMER", "value": 75_000_000},
                {"region": "EMEA", "value": 35_000_000},
                {"region": "APAC", "value": 15_000_000},
            ],
        ))

        parsed = _make_parsed(metric="revenue", dimension="region")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.confidence >= 0.7
        assert isinstance(result.value, list)
        assert len(result.value) == 3
        mock_dcl_client.resolve_via_graph.assert_called_once_with(
            concepts=["revenue"], dimensions=["region"], filters=None,
        )


# =========================================================================
# Test: Cross-system join (concept + two dimensions)
# =========================================================================

class TestGraphCrossSystemJoin:
    """Test: 'Revenue by cost center for Cloud division' — cross-system join."""

    def test_graph_with_cross_system_join(self, executor, mock_dcl_client):
        """Graph finds join path NetSuite ↔ Workday and resolves hierarchy."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.73,
            join_paths=[{"from": "netsuite", "to": "workday", "via": "aam_edge"}],
            filters_resolved=[{
                "dimension": "division",
                "value": "Cloud",
                "resolved_to": ["Cloud East", "Cloud West"],
            }],
            data=[
                {"cost_center": "Cloud East", "value": 40_000_000},
                {"cost_center": "Cloud West", "value": 35_000_000},
            ],
        ))

        parsed = _make_parsed(
            metric="revenue",
            dimension="cost_center",
            entity="Cloud",
        )
        result = executor.execute(parsed)

        assert result.success is True
        assert result.confidence >= 0.5
        assert result.metadata["join_paths"] is not None
        assert result.metadata["filters_resolved"] is not None


# =========================================================================
# Test: Invalid dimension combination
# =========================================================================

class TestGraphInvalidDimension:
    """Test: 'Sprint velocity by profit center' — invalid combination."""

    def test_graph_rejects_invalid_dimension(self, executor, mock_dcl_client):
        """Graph returns can_answer=false for invalid dimension combo."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value={
            "can_answer": False,
            "reason": "sprint_velocity cannot be sliced by profit_center",
            "confidence": 0.0,
            "source": "dcl_graph",
        })

        # Graph says no → executor falls back to flat query
        # Flat query will also fail since sprint_velocity is not in catalog
        parsed = _make_parsed(metric="sprint_velocity", dimension="profit_center")

        # Mock the catalog to not have sprint_velocity
        mock_catalog = MagicMock()
        mock_catalog.metrics = {}
        mock_dcl_client.get_catalog = MagicMock(return_value=mock_catalog)

        result = executor.execute(parsed)

        # Falls through to flat path which returns UNKNOWN_METRIC
        assert result.success is False
        assert result.error == "UNKNOWN_METRIC"


# =========================================================================
# Test: Fallback to flat query when graph unavailable
# =========================================================================

class TestGraphFallbackToFlat:
    """Test: Graph unavailable → falls back to existing flat query path."""

    def test_fallback_when_graph_unavailable(self, executor, mock_dcl_client):
        """When DCL graph endpoint is unreachable, falls back to flat query."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value={
            "can_answer": False,
            "reason": "DCL server unreachable",
            "source": "connection_error",
        })

        # Mock the flat query path
        mock_catalog = MagicMock()
        mock_catalog.metrics = {"revenue": MagicMock(allowed_dimensions=["region"])}
        mock_dcl_client.get_catalog = MagicMock(return_value=mock_catalog)
        mock_dcl_client.query = MagicMock(return_value={
            "status": "ok",
            "data": [{"period": "2025-Q4", "value": 125}],
        })

        parsed = _make_parsed(metric="revenue")
        result = executor.execute(parsed)

        assert result.success is True
        # Should have used flat query, not graph
        assert result.query_type != "graph_resolution"

    def test_fallback_when_graph_returns_cannot_answer(self, executor, mock_dcl_client):
        """When graph says can_answer=false, falls back to flat query."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value={
            "can_answer": False,
            "reason": "Concept 'revenue' has no dimension bindings for 'color'",
            "source": "dcl_graph",
        })

        mock_catalog = MagicMock()
        mock_catalog.metrics = {"revenue": MagicMock(allowed_dimensions=["region"])}
        mock_dcl_client.get_catalog = MagicMock(return_value=mock_catalog)
        mock_dcl_client.query = MagicMock(return_value={
            "status": "ok",
            "data": [{"period": "2025-Q4", "value": 42}],
        })

        parsed = _make_parsed(metric="revenue")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.value == 42

    def test_fallback_when_graph_raises_exception(self, executor, mock_dcl_client):
        """When graph resolution throws, falls back gracefully to flat query."""
        mock_dcl_client.resolve_via_graph = MagicMock(side_effect=Exception("network error"))

        mock_catalog = MagicMock()
        mock_catalog.metrics = {"revenue": MagicMock(allowed_dimensions=[])}
        mock_dcl_client.get_catalog = MagicMock(return_value=mock_catalog)
        mock_dcl_client.query = MagicMock(return_value={
            "status": "ok",
            "data": [{"period": "2025-Q4", "value": 99}],
        })

        parsed = _make_parsed(metric="revenue")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.value == 99


# =========================================================================
# Test: Warnings (e.g., cross-system join degraded)
# =========================================================================

class TestGraphWarnings:
    """Test: Graph returns result with warnings (e.g., AAM unavailable)."""

    def test_graph_result_with_warnings(self, executor, mock_dcl_client):
        """Graph answers but includes cross-system warning."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.65,
            warnings=["cross-system join via AAM unavailable; using fallback path"],
            concepts=[{"concept": "revenue", "value": 100}],
        ))

        parsed = _make_parsed(metric="revenue", dimension="cost_center")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.metadata["warnings"] is not None
        assert "cross-system" in result.metadata["warnings"][0]


# =========================================================================
# Test: Unknown concept
# =========================================================================

class TestGraphUnknownConcept:
    """Test: 'What is the florbatz by region?' — unknown concept."""

    def test_unknown_concept_falls_back(self, executor, mock_dcl_client):
        """Graph doesn't recognize concept → falls back → flat also fails."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value={
            "can_answer": False,
            "reason": "Concept 'florbatz' not recognized in semantic catalog",
            "source": "dcl_graph",
        })

        mock_catalog = MagicMock()
        mock_catalog.metrics = {}
        mock_dcl_client.get_catalog = MagicMock(return_value=mock_catalog)

        parsed = _make_parsed(metric="florbatz", dimension="region")
        result = executor.execute(parsed)

        assert result.success is False
        assert result.error == "UNKNOWN_METRIC"


# =========================================================================
# Test: SOR authority in provenance
# =========================================================================

class TestGraphSORAuthority:
    """Test: 'Show me employees by department' — provenance shows SOR."""

    def test_graph_provenance_shows_authoritative_system(self, executor, mock_dcl_client):
        """Graph returns provenance with authoritative system marked."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.92,
            provenance={
                "primary_system": "workday",
                "authority": "authoritative",
                "systems": ["workday"],
                "edges": ["normalizer", "ontology", "contour_authority"],
            },
            concepts=[{"concept": "headcount", "system": "workday", "value": 1250}],
        ))

        parsed = _make_parsed(metric="headcount", dimension="department")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.metadata["provenance"]["primary_system"] == "workday"
        assert "authoritative" in result.metadata["provenance"]["authority"]


# =========================================================================
# Test: Hierarchy drill-down
# =========================================================================

class TestGraphHierarchyDrilldown:
    """Test: 'Headcount for Engineering cost centers' — hierarchy resolution."""

    def test_graph_resolves_hierarchy(self, executor, mock_dcl_client):
        """Graph resolves 'Engineering' to child cost centers."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.88,
            filters_resolved=[{
                "dimension": "cost_center",
                "value": "Engineering",
                "resolved_to": ["Cloud Engineering", "Platform Engineering"],
            }],
            data=[
                {"cost_center": "Cloud Engineering", "value": 420},
                {"cost_center": "Platform Engineering", "value": 310},
            ],
        ))

        parsed = _make_parsed(metric="headcount", dimension="cost_center", entity="Engineering")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.metadata["filters_resolved"] is not None
        resolved = result.metadata["filters_resolved"][0]
        assert resolved["value"] == "Engineering"
        assert "Cloud Engineering" in resolved["resolved_to"]
        assert "Platform Engineering" in resolved["resolved_to"]


# =========================================================================
# Test: Management overlay resolution
# =========================================================================

class TestGraphManagementOverlay:
    """Test: 'Revenue by board segment' — management overlay used."""

    def test_graph_uses_management_overlay(self, executor, mock_dcl_client):
        """Graph resolves 'board segment' via management overlay to division."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.80,
            concepts=[{"concept": "revenue", "system": "netsuite", "value": None}],
            data=[
                {"division": "Cloud", "value": 80_000_000},
                {"division": "Platform", "value": 45_000_000},
            ],
            provenance={
                "systems": ["netsuite"],
                "edges": ["normalizer", "management_overlay"],
                "management_overlay_used": True,
            },
        ))

        parsed = _make_parsed(metric="revenue", dimension="division")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.metadata["provenance"]["management_overlay_used"] is True


# =========================================================================
# Test: DCL client resolve_via_graph HTTP behavior
# =========================================================================

class TestDCLClientResolveViaGraph:
    """Test the DCLSemanticClient.resolve_via_graph() method directly."""

    def test_local_mode_returns_unavailable(self):
        """Client without DCL URL returns can_answer=False."""
        client = DCLSemanticClient(dcl_base_url=None)
        result = client.resolve_via_graph(concepts=["revenue"])
        assert result["can_answer"] is False
        assert "unavailable" in result["reason"].lower()

    def test_404_returns_unavailable(self, mock_dcl_client):
        """DCL returns 404 → graph endpoint not available."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_dcl_client._http_client.post.return_value = mock_response

        result = mock_dcl_client.resolve_via_graph(concepts=["revenue"])
        assert result["can_answer"] is False
        assert "not available" in result["reason"].lower()

    def test_successful_resolve(self, mock_dcl_client):
        """DCL returns 200 with graph resolution."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "can_answer": True,
            "confidence": 0.92,
            "resolved_concepts": [{"concept": "revenue", "system": "netsuite"}],
        }
        mock_dcl_client._http_client.post.return_value = mock_response

        result = mock_dcl_client.resolve_via_graph(concepts=["revenue"])
        assert result["can_answer"] is True
        assert result["confidence"] == 0.92

    def test_timeout_returns_unavailable(self, mock_dcl_client):
        """DCL times out → graph returns unavailable."""
        import httpx
        mock_dcl_client._http_client.post.side_effect = httpx.TimeoutException("timeout")

        result = mock_dcl_client.resolve_via_graph(concepts=["revenue"])
        assert result["can_answer"] is False
        assert "timed out" in result["reason"].lower()

    def test_connection_error_returns_unavailable(self, mock_dcl_client):
        """DCL connection refused → graph returns unavailable."""
        import httpx
        mock_dcl_client._http_client.post.side_effect = httpx.ConnectError("refused")

        result = mock_dcl_client.resolve_via_graph(concepts=["revenue"])
        assert result["can_answer"] is False
        assert "unreachable" in result["reason"].lower()

    def test_payload_structure(self, mock_dcl_client):
        """Verify the payload sent to POST /api/dcl/resolve."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"can_answer": False, "reason": "test"}
        mock_dcl_client._http_client.post.return_value = mock_response

        mock_dcl_client.resolve_via_graph(
            concepts=["revenue", "headcount"],
            dimensions=["region", "department"],
            filters=[{"dimension": "division", "value": "Cloud"}],
        )

        call_args = mock_dcl_client._http_client.post.call_args
        assert call_args[0][0] == "http://localhost:8001/api/dcl/resolve"
        payload = call_args[1]["json"]
        assert payload["concepts"] == ["revenue", "headcount"]
        assert payload["dimensions"] == ["region", "department"]
        assert payload["filters"] == [{"dimension": "division", "value": "Cloud"}]


# =========================================================================
# Test: Response timing
# =========================================================================

class TestGraphResponseTiming:
    """Verify graph resolution doesn't add excessive latency."""

    def test_graph_resolution_is_fast(self, executor, mock_dcl_client):
        """Graph resolution (mocked) completes in < 100ms."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            concepts=[{"concept": "revenue", "value": 100}],
        ))

        parsed = _make_parsed(metric="revenue")

        start = time.time()
        result = executor.execute(parsed)
        elapsed_ms = (time.time() - start) * 1000

        assert result.success is True
        assert elapsed_ms < 100, f"Graph resolution took {elapsed_ms:.1f}ms (expected < 100ms)"


# =========================================================================
# Test: Multiple concepts
# =========================================================================

class TestGraphMultipleConcepts:
    """Test: 'Compare revenue and headcount by department'."""

    def test_graph_resolves_multiple_concepts(self, executor, mock_dcl_client):
        """Graph resolves two concepts at once."""
        mock_dcl_client.resolve_via_graph = MagicMock(return_value=_graph_response(
            can_answer=True,
            confidence=0.82,
            concepts=[
                {"concept": "revenue", "system": "netsuite", "confidence": 0.95},
                {"concept": "headcount", "system": "workday", "confidence": 0.90},
            ],
            data=[
                {"department": "Engineering", "revenue": 40_000_000, "headcount": 420},
                {"department": "Sales", "revenue": 60_000_000, "headcount": 280},
            ],
        ))

        parsed = _make_parsed(metric="revenue", dimension="department")
        result = executor.execute(parsed)

        assert result.success is True
        assert result.confidence >= 0.5
