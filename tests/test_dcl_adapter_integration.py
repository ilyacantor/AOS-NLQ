"""
Integration tests for the DCL↔NLQ adapter layer and provenance pipeline.

Tests the full data flow:
  DCL catalog response → _parse_dcl_response → SemanticCatalog
  DCL metric resolution → _resolve_metric_via_dcl → MetricDefinition
  NLQ query request → query() → DCL request transform
  DCL query response → _normalize_dcl_query_response → normalized dict
  Normalized dict → _build_simple_metric_result → SimpleMetricResult
  SimpleMetricResult → simple_metric_to_galaxy_response → IntentMapResponse (with provenance)

All tests use mock DCL payloads — no live HTTP required.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from src.nlq.services.dcl_semantic_client import (
    DCLSemanticClient,
    MetricDefinition,
    SemanticCatalog,
    PACK_TO_DOMAIN,
    GRAIN_TO_DCL,
)
from src.nlq.api.query_helpers import (
    SimpleMetricResult,
    simple_metric_to_galaxy_response,
)
from src.nlq.models.response import (
    Domain,
    MatchType,
    IntentMapResponse,
    IntentNode,
    NLQResponse,
)


# ---------------------------------------------------------------------------
# Fixtures — realistic DCL payloads
# ---------------------------------------------------------------------------

MOCK_DCL_CATALOG = {
    "mode": {
        "data_mode": "Ingest",
        "run_mode": "Live",
        "last_updated": "2026-02-15T10:00:00Z",
    },
    "metrics": [
        {
            "id": "revenue",
            "name": "Revenue",
            "pack": "cfo",
            "aliases": ["sales", "top_line", "total_revenue"],
            "allowed_dims": ["region", "segment", "product"],
            "allowed_grains": ["quarterly", "monthly", "yearly"],
        },
        {
            "id": "pipeline",
            "name": "Sales Pipeline",
            "pack": "cro",
            "aliases": ["pipe", "sales_pipeline"],
            "allowed_dims": ["rep", "stage"],
            "allowed_grains": ["quarterly", "monthly"],
        },
        {
            "id": "headcount",
            "name": "Headcount",
            "pack": "chro",
            "aliases": ["employees", "hc"],
            "allowed_dims": ["department", "location"],
            "allowed_grains": ["quarterly"],
        },
    ],
    "entities": [
        {"id": "region", "allowed_values": ["AMER", "EMEA", "APAC"]},
        {"id": "segment", "allowed_values": ["Enterprise", "SMB", "Mid-Market"]},
        {"id": "department", "allowed_values": ["Engineering", "Sales", "Marketing"]},
    ],
}

MOCK_DCL_QUERY_RESPONSE = {
    "metric": "revenue",
    "metric_name": "Revenue",
    "unit": "USD millions",
    "grain": "quarter",
    "data": [
        {"period": "2025-Q4", "value": 42.0, "dimensions": {}, "rank": None},
    ],
    "metadata": {
        "freshness": "2026-02-15T08:30:00Z",
        "quality_score": 0.95,
        "record_count": 1,
        "run_id": "run_555_sf_revenue",
        "tenant_id": "acme_corp",
        "snapshot_name": "revenue_q4_2025",
        "run_timestamp": "2026-02-15T06:00:00Z",
        "mode": "Live",
    },
    "provenance": [
        {
            "source_system": "Salesforce CRM",
            "freshness": "2h",
            "quality_score": 0.95,
        },
        {
            "source_system": "SAP ERP",
            "freshness": "4h",
            "quality_score": 0.92,
        },
    ],
}

MOCK_DCL_QUERY_RESPONSE_NO_PROVENANCE = {
    "metric": "pipeline",
    "metric_name": "Sales Pipeline",
    "unit": "USD millions",
    "grain": "quarter",
    "data": [
        {"period": "2025-Q4", "value": 120.0, "dimensions": {}, "rank": None},
    ],
    "metadata": {
        "freshness": "2026-02-15T09:00:00Z",
        "quality_score": 0.88,
        "record_count": 1,
    },
    "provenance": [],
}

MOCK_DCL_QUERY_RESPONSE_WITH_ENTITY = {
    "metric": "revenue",
    "metric_name": "Revenue",
    "unit": "USD millions",
    "grain": "quarter",
    "data": [
        {"period": "2025-Q4", "value": 15.3, "dimensions": {"region": "AMER"}, "rank": None},
    ],
    "metadata": {
        "freshness": "2026-02-15T08:00:00Z",
        "quality_score": 0.93,
        "record_count": 1,
        "run_id": "run_556_sf_revenue_amer",
        "tenant_id": "acme_corp",
        "snapshot_name": "revenue_q4_amer",
        "run_timestamp": "2026-02-15T06:30:00Z",
    },
    "provenance": [
        {"source_system": "Salesforce CRM", "freshness": "2h", "quality_score": 0.93},
    ],
    "entity": {
        "id": "ent_acme_001",
        "name": "Acme Corp",
        "source": "salesforce_crm",
    },
}


# ===========================================================================
# SUITE 1: Catalog Adapter (_parse_dcl_response)
# ===========================================================================

class TestCatalogAdapter:
    """Test that _parse_dcl_response correctly maps DCL catalog fields to NLQ format."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url=None)

    def test_parse_metrics_count(self):
        """All metrics from DCL catalog are parsed."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert len(catalog.metrics) == 3

    def test_name_maps_to_display_name(self):
        """DCL 'name' field maps to MetricDefinition.display_name."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog.metrics["revenue"].display_name == "Revenue"
        assert catalog.metrics["pipeline"].display_name == "Sales Pipeline"
        assert catalog.metrics["headcount"].display_name == "Headcount"

    def test_pack_maps_to_domain(self):
        """DCL 'pack' field maps to MetricDefinition.domain via PACK_TO_DOMAIN."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog.metrics["revenue"].domain == "CFO"
        assert catalog.metrics["pipeline"].domain == "CRO"
        assert catalog.metrics["headcount"].domain == "CHRO"

    def test_allowed_dims_maps_to_allowed_dimensions(self):
        """DCL 'allowed_dims' maps to MetricDefinition.allowed_dimensions."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog.metrics["revenue"].allowed_dimensions == ["region", "segment", "product"]
        assert catalog.metrics["pipeline"].allowed_dimensions == ["rep", "stage"]

    def test_allowed_grains_preserved(self):
        """DCL 'allowed_grains' is preserved as-is."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog.metrics["revenue"].allowed_grains == ["quarterly", "monthly", "yearly"]

    def test_aliases_preserved(self):
        """DCL 'aliases' array is preserved."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert "sales" in catalog.metrics["revenue"].aliases
        assert "top_line" in catalog.metrics["revenue"].aliases

    def test_entities_parsed_as_dimensions(self):
        """DCL 'entities[]' array maps to catalog.dimensions dict."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert "region" in catalog.dimensions
        assert catalog.dimensions["region"] == ["AMER", "EMEA", "APAC"]
        assert "segment" in catalog.dimensions
        assert "department" in catalog.dimensions

    def test_alias_index_built(self):
        """Alias index is built for reverse lookup."""
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog.alias_to_metric.get("sales") == "revenue"
        assert catalog.alias_to_metric.get("pipe") == "pipeline"
        assert catalog.alias_to_metric.get("employees") == "headcount"

    def test_mode_info_logged(self):
        """Mode info from DCL response is processed without error."""
        # Should not raise
        catalog = self.client._parse_dcl_response(MOCK_DCL_CATALOG)
        assert catalog is not None

    def test_unknown_pack_falls_back_to_uppercase(self):
        """Unknown pack value falls back to uppercase of the pack name."""
        catalog_data = {
            "metrics": [
                {"id": "custom_metric", "name": "Custom", "pack": "unknown_pack",
                 "aliases": [], "allowed_dims": [], "allowed_grains": []},
            ],
            "entities": [],
        }
        catalog = self.client._parse_dcl_response(catalog_data)
        assert catalog.metrics["custom_metric"].domain == "UNKNOWN_PACK"

    def test_empty_catalog(self):
        """Empty DCL catalog returns empty SemanticCatalog."""
        catalog = self.client._parse_dcl_response({"metrics": [], "entities": []})
        assert len(catalog.metrics) == 0
        assert len(catalog.dimensions) == 0


# ===========================================================================
# SUITE 2: Query Request Transform
# ===========================================================================

class TestQueryRequestTransform:
    """Test that query() transforms NLQ request format to DCL format."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        self.mock_http = MagicMock()
        self.client._http_client = self.mock_http

    def _setup_mock_response(self, json_data, status_code=200):
        """Configure mock HTTP response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = MagicMock()
        self.mock_http.post.return_value = mock_resp

    def test_period_converted_to_start_end(self):
        """time_range.period is converted to {start, end}."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )
        call_args = self.mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["time_range"] == {"start": "2025-Q4", "end": "2025-Q4"}

    def test_granularity_extracted_to_top_level_grain(self):
        """time_range.granularity is extracted to top-level 'grain'."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )
        call_args = self.mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["grain"] == "quarter"

    def test_grain_long_form_to_short_form(self):
        """Long-form grain values are converted to DCL short form."""
        for long_form, short_form in GRAIN_TO_DCL.items():
            self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
            self.client.query(
                metric="revenue",
                time_range={"period": "2025", "granularity": long_form},
            )
            call_args = self.mock_http.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["grain"] == short_form, f"Expected {short_form} for {long_form}"

    def test_start_end_passthrough(self):
        """Pre-formatted start/end pass through unchanged."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(
            metric="revenue",
            time_range={"start": "2025-Q1", "end": "2025-Q4"},
        )
        call_args = self.mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["time_range"] == {"start": "2025-Q1", "end": "2025-Q4"}

    def test_order_by_passed_to_dcl(self):
        """order_by is passed to DCL for ranking queries."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(
            metric="revenue",
            order_by="desc",
            limit=5,
        )
        call_args = self.mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["order_by"] == "desc"
        assert payload["limit"] == 5

    def test_dimensions_and_filters_passed(self):
        """Dimensions and filters are passed through to DCL."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(
            metric="revenue",
            dimensions=["region"],
            filters={"region": "AMER"},
        )
        call_args = self.mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["dimensions"] == ["region"]
        assert payload["filters"] == {"region": "AMER"}

    def test_dcl_endpoint_url(self):
        """Request goes to correct DCL endpoint."""
        self._setup_mock_response(MOCK_DCL_QUERY_RESPONSE)
        self.client.query(metric="revenue")
        call_args = self.mock_http.post.call_args
        url = call_args.args[0] if call_args.args else call_args[0][0]
        assert url == "http://mock-dcl:8000/api/dcl/query"

    def test_404_returns_not_found(self):
        """DCL 404 is translated to not_found status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        self.mock_http.post.return_value = mock_resp
        result = self.client.query(metric="nonexistent_metric")
        assert result["status"] == "not_found"

    def test_400_returns_bad_request(self):
        """DCL 400 is translated to bad_request status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"message": "Invalid grain"}
        self.mock_http.post.return_value = mock_resp
        result = self.client.query(metric="revenue", grain="invalid")
        assert result["status"] == "bad_request"
        assert "Invalid grain" in result["error"]


# ===========================================================================
# SUITE 3: Query Response Normalization
# ===========================================================================

class TestQueryResponseNormalization:
    """Test _normalize_dcl_query_response transforms DCL response to NLQ format."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")

    def test_status_ok_added(self):
        """Normalized response has status='ok' (DCL uses HTTP codes, not wrapper)."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["status"] == "ok"

    def test_source_dcl_tagged(self):
        """Normalized response is tagged with source='dcl'."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["source"] == "dcl"

    def test_unit_at_top_level(self):
        """Unit is carried from DCL top-level (not per-row)."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["unit"] == "USD millions"

    def test_metric_name_preserved(self):
        """metric_name from DCL is preserved."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["metric_name"] == "Revenue"

    def test_data_passthrough(self):
        """Data array passes through unchanged."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert len(result["data"]) == 1
        assert result["data"][0]["period"] == "2025-Q4"
        assert result["data"][0]["value"] == 42.0

    def test_freshness_display_from_provenance(self):
        """Human-friendly freshness comes from provenance[0].freshness, not metadata.freshness."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["metadata"]["freshness_display"] == "2h"

    def test_quality_score_in_metadata(self):
        """quality_score is preserved in metadata."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert result["metadata"]["quality_score"] == 0.95

    def test_run_provenance_extracted(self):
        """run_provenance block is extracted from metadata + provenance."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        rp = result["run_provenance"]
        assert rp["run_id"] == "run_555_sf_revenue"
        assert rp["tenant_id"] == "acme_corp"
        assert rp["snapshot_name"] == "revenue_q4_2025"
        assert rp["run_timestamp"] == "2026-02-15T06:00:00Z"
        assert "Salesforce CRM" in rp["source_systems"]
        assert "SAP ERP" in rp["source_systems"]
        assert rp["freshness"] == "2h"
        assert rp["quality_score"] == 0.95
        assert rp["mode"] == "Live"

    def test_empty_provenance_yields_empty_source_systems(self):
        """Empty provenance array yields empty source_systems list."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE_NO_PROVENANCE)
        rp = result["run_provenance"]
        assert rp["source_systems"] == []
        assert rp["run_id"] is None  # No run_id in metadata
        assert rp["freshness"] == ""

    def test_metadata_sources_fallback(self):
        """When provenance[] is empty, metadata.sources[] is used for source_systems."""
        response = {
            "metric": "revenue",
            "data": [{"period": "2025-Q4", "value": 42.0}],
            "metadata": {
                "mode": "Ingest",
                "run_id": "run_999",
                "freshness": "2026-02-15T10:00:00Z",
                "sources": ["salesforce", "netsuite"],
            },
            "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(response)
        rp = result["run_provenance"]
        assert rp["source_systems"] == ["salesforce", "netsuite"]
        assert rp["mode"] == "Ingest"

    def test_provenance_takes_priority_over_metadata_sources(self):
        """provenance[].source_system takes priority over metadata.sources[]."""
        response = {
            "metric": "revenue",
            "data": [{"period": "2025-Q4", "value": 42.0}],
            "metadata": {
                "sources": ["should_not_appear"],
            },
            "provenance": [
                {"source_system": "Salesforce CRM", "freshness": "1h", "quality_score": 0.95},
            ],
        }
        result = self.client._normalize_dcl_query_response(response)
        rp = result["run_provenance"]
        assert rp["source_systems"] == ["Salesforce CRM"]
        assert "should_not_appear" not in rp["source_systems"]

    def test_entity_passthrough(self):
        """Entity resolution data passes through when present."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE_WITH_ENTITY)
        assert result["entity"]["id"] == "ent_acme_001"
        assert result["entity"]["name"] == "Acme Corp"

    def test_no_entity_when_absent(self):
        """No entity key when DCL response has no entity."""
        result = self.client._normalize_dcl_query_response(MOCK_DCL_QUERY_RESPONSE)
        assert "entity" not in result


# ===========================================================================
# SUITE 4: Provenance Pipeline (SimpleMetricResult → Galaxy Response)
# ===========================================================================

class TestProvenancePipeline:
    """Test that provenance flows from DCL response through to Galaxy IntentMapResponse."""

    def _make_simple_result(self, source="dcl", run_provenance=None):
        """Helper to create a SimpleMetricResult with provenance."""
        return SimpleMetricResult(
            metric="revenue",
            value=42.0,
            formatted_value="$42.0M",
            unit="USD millions",
            display_name="Revenue",
            domain=Domain.FINANCE,
            answer="Revenue for 2025-Q4 is $42.0M",
            period="2025-Q4",
            data_quality=0.95,
            freshness="2h",
            source=source,
            run_provenance=run_provenance,
        )

    def test_provenance_on_intent_map_response(self):
        """IntentMapResponse.provenance is set from SimpleMetricResult.run_provenance."""
        prov = {
            "run_id": "run_555_sf_revenue",
            "tenant_id": "acme_corp",
            "snapshot_name": "revenue_q4_2025",
            "run_timestamp": "2026-02-15T06:00:00Z",
            "source_systems": ["Salesforce CRM", "SAP ERP"],
            "freshness": "2h",
            "quality_score": 0.95,
            "mode": "Live",
        }
        result = self._make_simple_result(run_provenance=prov)
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert galaxy.provenance is not None
        assert galaxy.provenance["run_id"] == "run_555_sf_revenue"
        assert galaxy.provenance["tenant_id"] == "acme_corp"
        assert galaxy.provenance["snapshot_name"] == "revenue_q4_2025"
        assert galaxy.provenance["source_systems"] == ["Salesforce CRM", "SAP ERP"]

    def test_source_system_on_node(self):
        """IntentNode.source_system is derived from run_provenance.source_systems."""
        prov = {
            "source_systems": ["Salesforce CRM", "SAP ERP"],
        }
        result = self._make_simple_result(run_provenance=prov)
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert len(galaxy.nodes) == 1
        assert galaxy.nodes[0].source_system == "Salesforce CRM, SAP ERP"

    def test_no_source_system_when_no_provenance(self):
        """IntentNode.source_system is None when no run_provenance."""
        result = self._make_simple_result(run_provenance=None)
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert galaxy.nodes[0].source_system is None

    def test_no_provenance_when_local(self):
        """IntentMapResponse.provenance is None when source is local."""
        result = self._make_simple_result(source="local", run_provenance=None)
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert galaxy.provenance is None

    def test_data_quality_flows_to_node(self):
        """data_quality from DCL metadata flows to IntentNode.data_quality."""
        result = self._make_simple_result()
        result.data_quality = 0.88
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert galaxy.nodes[0].data_quality == 0.88
        assert galaxy.overall_data_quality == 0.88

    def test_freshness_flows_to_node(self):
        """freshness from DCL provenance flows to IntentNode.freshness."""
        result = self._make_simple_result()
        result.freshness = "4h"
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")

        assert galaxy.nodes[0].freshness == "4h"


# ===========================================================================
# SUITE 5: SimpleMetricResult Defaults
# ===========================================================================

class TestSimpleMetricResultDefaults:
    """Test that SimpleMetricResult has correct defaults for local fallback mode."""

    def test_default_source_is_local(self):
        """Default source is 'local'."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="$", display_name="Revenue", domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        assert result.source == "local"

    def test_default_data_quality(self):
        """Default data_quality is 1.0."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="$", display_name="Revenue", domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        assert result.data_quality == 1.0

    def test_default_freshness(self):
        """Default freshness is '0h'."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="$", display_name="Revenue", domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        assert result.freshness == "0h"

    def test_default_run_provenance_is_none(self):
        """Default run_provenance is None."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="$", display_name="Revenue", domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        assert result.run_provenance is None


# ===========================================================================
# SUITE 6: Mapping Constants
# ===========================================================================

class TestMappingConstants:
    """Validate the mapping constants are correct and complete."""

    def test_pack_to_domain_covers_five_personas(self):
        """PACK_TO_DOMAIN covers all 5 AOS persona packs."""
        assert len(PACK_TO_DOMAIN) == 5
        assert PACK_TO_DOMAIN["cfo"] == "CFO"
        assert PACK_TO_DOMAIN["cro"] == "CRO"
        assert PACK_TO_DOMAIN["coo"] == "COO"
        assert PACK_TO_DOMAIN["cto"] == "CTO"
        assert PACK_TO_DOMAIN["chro"] == "CHRO"

    def test_grain_to_dcl_covers_all_forms(self):
        """GRAIN_TO_DCL covers quarterly, monthly, yearly, annual."""
        assert GRAIN_TO_DCL["quarterly"] == "quarter"
        assert GRAIN_TO_DCL["monthly"] == "month"
        assert GRAIN_TO_DCL["yearly"] == "year"
        assert GRAIN_TO_DCL["annual"] == "year"  # alias


# ===========================================================================
# SUITE 7: Backward Compatibility
# ===========================================================================

class TestBackwardCompatibility:
    """Ensure DCL adapter changes don't break existing NLQ models."""

    def test_intent_node_without_source_system(self):
        """IntentNode works without source_system (pre-DCL)."""
        node = IntentNode(
            id="test_1", metric="revenue", display_name="Revenue",
            match_type=MatchType.EXACT, domain=Domain.FINANCE,
            confidence=0.95, data_quality=1.0, freshness="0h",
        )
        assert node.source_system is None

    def test_intent_map_response_without_provenance(self):
        """IntentMapResponse works without provenance (pre-DCL)."""
        resp = IntentMapResponse(
            query="What is revenue?", query_type="POINT_QUERY",
            overall_confidence=0.95, overall_data_quality=1.0,
            node_count=0, nodes=[], text_response="Revenue is $42M",
            needs_clarification=False,
        )
        assert resp.provenance is None

    def test_simple_metric_result_backward_compat(self):
        """SimpleMetricResult works with only required fields."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="$", display_name="Revenue", domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        # All DCL-added fields should have safe defaults
        assert result.data_quality == 1.0
        assert result.freshness == "0h"
        assert result.source == "local"
        assert result.run_provenance is None

    def test_galaxy_response_without_provenance(self):
        """Galaxy response works without provenance data."""
        result = SimpleMetricResult(
            metric="revenue", value=42.0, formatted_value="$42.0M",
            unit="USD millions", display_name="Revenue",
            domain=Domain.FINANCE, answer="Revenue is $42.0M",
        )
        galaxy = simple_metric_to_galaxy_response(result, "What is revenue?")
        assert galaxy.provenance is None
        assert galaxy.nodes[0].source_system is None
        assert galaxy.nodes[0].data_quality == 1.0
        assert galaxy.nodes[0].freshness == "0h"


# ===========================================================================
# SUITE 8: End-to-End DCL Mode Query
# ===========================================================================

class TestEndToEndDCLQuery:
    """Test the full query path with mocked HTTP, verifying the complete adapter pipeline."""

    def test_full_pipeline_dcl_mode(self):
        """Full pipeline: NLQ query → DCL request → DCL response → normalized → SimpleMetricResult."""
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")

        # Mock the HTTP client
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_DCL_QUERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        # Execute query
        result = client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )

        # Verify the normalized result
        assert result["status"] == "ok"
        assert result["source"] == "dcl"
        assert result["metric"] == "revenue"
        assert result["unit"] == "USD millions"
        assert result["data"][0]["value"] == 42.0

        # Verify provenance extraction
        rp = result["run_provenance"]
        assert rp["run_id"] == "run_555_sf_revenue"
        assert rp["tenant_id"] == "acme_corp"
        assert rp["snapshot_name"] == "revenue_q4_2025"
        assert len(rp["source_systems"]) == 2
        assert rp["freshness"] == "2h"
        assert rp["quality_score"] == 0.95
        assert rp["mode"] == "Live"

        # Verify the DCL request was correctly formatted
        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["time_range"] == {"start": "2025-Q4", "end": "2025-Q4"}
        assert payload["grain"] == "quarter"
        assert payload["metric"] == "revenue"

    def test_full_pipeline_local_fallback(self):
        """Local fallback mode: no DCL_API_URL → uses fact_base.json."""
        client = DCLSemanticClient(dcl_base_url=None)

        result = client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )

        # Local fallback should still return data
        assert result.get("status") == "ok"
        assert result.get("source") == "local_fallback"
        # Should have data from fact_base.json
        data = result.get("data", [])
        assert len(data) > 0 or result.get("error") is None

    def test_full_pipeline_to_galaxy_response(self):
        """Full pipeline end-to-end: DCL query → normalized → SimpleMetricResult → Galaxy IntentMapResponse."""
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")

        # Mock HTTP
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_DCL_QUERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        # Step 1: Query DCL
        dcl_result = client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )

        # Step 2: Build SimpleMetricResult (simulating _build_simple_metric_result)
        metadata = dcl_result.get("metadata", {})
        smr = SimpleMetricResult(
            metric="revenue",
            value=dcl_result["data"][0]["value"],
            formatted_value="$42.0M",
            unit=dcl_result.get("unit", "USD millions"),
            display_name="Revenue",
            domain=Domain.FINANCE,
            answer="Revenue for 2025-Q4 is $42.0M",
            period="2025-Q4",
            data_quality=metadata.get("quality_score", 1.0),
            freshness=metadata.get("freshness_display", "") or "0h",
            source=dcl_result.get("source", "local"),
            run_provenance=dcl_result.get("run_provenance"),
        )

        # Step 3: Convert to Galaxy response
        galaxy = simple_metric_to_galaxy_response(smr, "What is revenue?")

        # Verify the Galaxy response carries all provenance data
        assert isinstance(galaxy, IntentMapResponse)
        assert galaxy.query == "What is revenue?"
        assert galaxy.query_type == "POINT_QUERY"
        assert galaxy.overall_data_quality == 0.95
        assert galaxy.provenance is not None
        assert galaxy.provenance["run_id"] == "run_555_sf_revenue"
        assert galaxy.provenance["tenant_id"] == "acme_corp"
        assert galaxy.provenance["snapshot_name"] == "revenue_q4_2025"
        assert galaxy.provenance["source_systems"] == ["Salesforce CRM", "SAP ERP"]

        # Verify node carries source info
        assert len(galaxy.nodes) == 1
        node = galaxy.nodes[0]
        assert node.source_system == "Salesforce CRM, SAP ERP"
        assert node.data_quality == 0.95
        assert node.freshness == "2h"
        assert node.value == 42.0
        assert node.formatted_value == "$42.0M"


# ===========================================================================
# SUITE 9: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases in the adapter layer."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")

    def test_normalize_empty_data(self):
        """Normalize handles response with empty data array."""
        response = {
            "metric": "revenue",
            "data": [],
            "metadata": {},
            "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(response)
        assert result["status"] == "ok"
        assert result["data"] == []
        assert result["run_provenance"]["source_systems"] == []

    def test_normalize_missing_metadata(self):
        """Normalize handles response without metadata key."""
        response = {
            "metric": "revenue",
            "data": [{"period": "2025-Q4", "value": 42.0}],
        }
        result = self.client._normalize_dcl_query_response(response)
        assert result["status"] == "ok"
        assert result["run_provenance"]["run_id"] is None

    def test_normalize_partial_provenance(self):
        """Normalize handles provenance with some fields missing."""
        response = {
            "metric": "revenue",
            "data": [{"period": "2025-Q4", "value": 42.0}],
            "metadata": {"quality_score": 0.9},
            "provenance": [{"source_system": "SAP ERP"}],
        }
        result = self.client._normalize_dcl_query_response(response)
        assert result["run_provenance"]["source_systems"] == ["SAP ERP"]
        assert result["metadata"]["freshness_display"] == ""

    def test_query_no_time_range(self):
        """Query with no time_range sends empty time_range to DCL."""
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_DCL_QUERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        self.client._http_client = mock_http

        self.client.query(metric="revenue")
        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["time_range"] == {}

    def test_conflicts_and_temporal_warning_passthrough(self):
        """conflicts and temporal_warning pass through when present."""
        response = {
            "metric": "revenue",
            "data": [],
            "metadata": {},
            "provenance": [],
            "conflicts": [{"system_a": "SAP", "system_b": "SF", "delta": 2.2}],
            "temporal_warning": {"crosses_boundary": True, "change_date": "2025-03-01"},
        }
        result = self.client._normalize_dcl_query_response(response)
        assert result["conflicts"][0]["delta"] == 2.2
        assert result["temporal_warning"]["crosses_boundary"] is True

    def test_catalog_with_missing_optional_fields(self):
        """Catalog parsing handles metrics with missing optional fields."""
        catalog_data = {
            "metrics": [
                {"id": "revenue"},  # Minimal — no name, pack, aliases, etc.
            ],
            "entities": [],
        }
        catalog = self.client._parse_dcl_response(catalog_data)
        metric = catalog.metrics["revenue"]
        assert metric.display_name == "revenue"  # Falls back to ID
        assert metric.aliases == []
        assert metric.allowed_dimensions == []
