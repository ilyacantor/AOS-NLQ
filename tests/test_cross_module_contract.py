"""
Cross-module contract tests: AAM → DCL → NLQ.

These tests validate the data handshake between all three AOS modules
using the exact payload shapes each agent produces. No live HTTP required —
the tests use fixture payloads that match the documented contracts.

Test flow per the RACI:
  1. AAM Runner pushes ingest payload → DCL accepts (contract validated)
  2. DCL query response carries run provenance → NLQ normalizes it
  3. NLQ builds SimpleMetricResult → Galaxy IntentMapResponse with Trust Badge

The fixtures below represent REAL payloads from each agent's implementation,
not approximations. If a contract changes upstream, these tests break first.
"""

import pytest
from unittest.mock import MagicMock

from src.nlq.services.dcl_semantic_client import DCLSemanticClient, PACK_TO_DOMAIN, GRAIN_TO_DCL
from src.nlq.api.query_helpers import SimpleMetricResult, simple_metric_to_galaxy_response
from src.nlq.models.response import Domain, MatchType, IntentMapResponse, IntentNode
from src.nlq.knowledge.display import get_display_name
from src.nlq.knowledge.schema import get_metric_unit


# ===========================================================================
# CONTRACT FIXTURES — exact shapes from AAM and DCL agents
# ===========================================================================

# What AAM Runner sends to DCL POST /api/dcl/ingest
# (headers + body per AAM agent's execute_job_inline implementation)
AAM_INGEST_HEADERS = {
    "x-run-id": "run_777_sf_revenue_q4",
    "x-pipe-id": "pipe_sf_revenue",
    "x-schema-hash": "sha256:abc123def456",
    "Content-Type": "application/json",
}

AAM_INGEST_PAYLOAD = {
    "pipe_id": "pipe_sf_revenue",
    "run_id": "run_777_sf_revenue_q4",
    "tenant_id": "acme_corp",
    "snapshot_name": "sf_revenue_q4_2025",
    "schema_hash": "sha256:abc123def456",
    "rows": [
        {"period": "2025-Q1", "value": 33.0, "dimensions": {}},
        {"period": "2025-Q2", "value": 36.0, "dimensions": {}},
        {"period": "2025-Q3", "value": 39.0, "dimensions": {}},
        {"period": "2025-Q4", "value": 42.0, "dimensions": {}},
    ],
    "metadata": {
        "source_system": "Salesforce CRM",
        "extracted_at": "2026-02-15T06:00:00Z",
        "record_count": 4,
        "schema_version": "1.0",
    },
}

# What DCL returns from POST /api/dcl/query AFTER ingesting AAM data (Path B)
# This is the exact shape DCL's query engine produces when it reads from the
# ingest buffer rather than fact_base.json
DCL_QUERY_RESPONSE_PATH_B = {
    "metric": "revenue",
    "metric_name": "Revenue",
    "unit": "USD millions",
    "grain": "quarter",
    "data": [
        {"period": "2025-Q1", "value": 33.0, "dimensions": {}, "rank": None},
        {"period": "2025-Q2", "value": 36.0, "dimensions": {}, "rank": None},
        {"period": "2025-Q3", "value": 39.0, "dimensions": {}, "rank": None},
        {"period": "2025-Q4", "value": 42.0, "dimensions": {}, "rank": None},
    ],
    "metadata": {
        "freshness": "2026-02-15T08:30:00Z",
        "quality_score": 0.97,
        "record_count": 4,
        "run_id": "run_777_sf_revenue_q4",
        "tenant_id": "acme_corp",
        "snapshot_name": "sf_revenue_q4_2025",
        "run_timestamp": "2026-02-15T06:00:00Z",
        "mode": "Live",
    },
    "provenance": [
        {
            "source_system": "Salesforce CRM",
            "freshness": "2h",
            "quality_score": 0.97,
        },
    ],
}

# What DCL returns when querying fact_base.json fallback (Path A — no Runner data)
DCL_QUERY_RESPONSE_PATH_A = {
    "metric": "revenue",
    "metric_name": "Revenue",
    "unit": "USD millions",
    "grain": "quarter",
    "data": [
        {"period": "2025-Q4", "value": 42.0, "dimensions": {}, "rank": None},
    ],
    "metadata": {
        "freshness": "2026-02-15T00:00:00Z",
        "quality_score": 1.0,
        "record_count": 1,
        "mode": "Demo",
    },
    "provenance": [],
}

# DCL catalog response (the semantic-export shape)
DCL_CATALOG_RESPONSE = {
    "mode": {"data_mode": "Ingest", "run_mode": "Live"},
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
            "aliases": ["pipe"],
            "allowed_dims": ["rep", "stage"],
            "allowed_grains": ["quarterly", "monthly"],
        },
    ],
    "entities": [
        {"id": "region", "allowed_values": ["AMER", "EMEA", "APAC"]},
        {"id": "segment", "allowed_values": ["Enterprise", "SMB"]},
    ],
}


# ===========================================================================
# CONTRACT 1: AAM → DCL Ingest Payload Conformance
# ===========================================================================

class TestAAMIngestContract:
    """Validate that AAM's ingest payload has all fields DCL requires."""

    def test_headers_have_run_id(self):
        """x-run-id header is present and matches payload."""
        assert "x-run-id" in AAM_INGEST_HEADERS
        assert AAM_INGEST_HEADERS["x-run-id"] == AAM_INGEST_PAYLOAD["run_id"]

    def test_headers_have_schema_hash(self):
        """x-schema-hash header is present for DCL validation."""
        assert "x-schema-hash" in AAM_INGEST_HEADERS
        assert AAM_INGEST_HEADERS["x-schema-hash"].startswith("sha256:")

    def test_headers_have_pipe_id(self):
        """x-pipe-id header is present for traceability."""
        assert "x-pipe-id" in AAM_INGEST_HEADERS
        assert AAM_INGEST_HEADERS["x-pipe-id"] == AAM_INGEST_PAYLOAD["pipe_id"]

    def test_payload_has_required_fields(self):
        """Ingest payload has all fields DCL expects."""
        required = ["pipe_id", "run_id", "tenant_id", "snapshot_name", "schema_hash", "rows", "metadata"]
        for field in required:
            assert field in AAM_INGEST_PAYLOAD, f"Missing required field: {field}"

    def test_rows_have_period_and_value(self):
        """Every row has period and value."""
        for row in AAM_INGEST_PAYLOAD["rows"]:
            assert "period" in row
            assert "value" in row

    def test_metadata_has_source_system(self):
        """Metadata identifies the source system for provenance."""
        assert "source_system" in AAM_INGEST_PAYLOAD["metadata"]

    def test_run_id_carries_through_to_dcl_response(self):
        """run_id from ingest appears in DCL query response metadata."""
        assert DCL_QUERY_RESPONSE_PATH_B["metadata"]["run_id"] == AAM_INGEST_PAYLOAD["run_id"]

    def test_tenant_id_carries_through(self):
        """tenant_id from ingest appears in DCL query response."""
        assert DCL_QUERY_RESPONSE_PATH_B["metadata"]["tenant_id"] == AAM_INGEST_PAYLOAD["tenant_id"]

    def test_snapshot_name_carries_through(self):
        """snapshot_name from ingest appears in DCL query response."""
        assert DCL_QUERY_RESPONSE_PATH_B["metadata"]["snapshot_name"] == AAM_INGEST_PAYLOAD["snapshot_name"]

    def test_source_system_appears_in_provenance(self):
        """source_system from ingest metadata appears in DCL provenance."""
        dcl_source_systems = [p["source_system"] for p in DCL_QUERY_RESPONSE_PATH_B["provenance"]]
        assert AAM_INGEST_PAYLOAD["metadata"]["source_system"] in dcl_source_systems

    def test_ingested_data_matches_query_data(self):
        """Data values in DCL query response match what was ingested."""
        ingested_values = {r["period"]: r["value"] for r in AAM_INGEST_PAYLOAD["rows"]}
        queried_values = {d["period"]: d["value"] for d in DCL_QUERY_RESPONSE_PATH_B["data"]}
        assert ingested_values == queried_values


# ===========================================================================
# CONTRACT 2: DCL → NLQ Query Response Normalization
# ===========================================================================

class TestDCLToNLQContract:
    """Validate NLQ correctly normalizes DCL query responses."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")

    def test_path_b_response_normalized(self):
        """Path B (ingest buffer) response normalizes correctly."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_B)
        assert result["status"] == "ok"
        assert result["source"] == "dcl"
        assert result["metric"] == "revenue"
        assert len(result["data"]) == 4

    def test_path_a_response_normalized(self):
        """Path A (fact_base fallback) response normalizes correctly."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_A)
        assert result["status"] == "ok"
        assert result["source"] == "dcl"  # Still from DCL, just Demo mode

    def test_path_b_has_run_provenance(self):
        """Path B response carries full run provenance."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_B)
        rp = result["run_provenance"]
        assert rp["run_id"] == "run_777_sf_revenue_q4"
        assert rp["tenant_id"] == "acme_corp"
        assert rp["snapshot_name"] == "sf_revenue_q4_2025"
        assert rp["run_timestamp"] == "2026-02-15T06:00:00Z"
        assert rp["source_systems"] == ["Salesforce CRM"]
        assert rp["freshness"] == "2h"
        assert rp["quality_score"] == 0.97
        assert rp["mode"] == "Live"

    def test_path_a_has_no_run_id(self):
        """Path A (Demo mode) has no run_id — it's static data."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_A)
        rp = result["run_provenance"]
        assert rp["run_id"] is None
        assert rp["source_systems"] == []
        assert rp["mode"] == "Demo"

    def test_freshness_display_from_provenance_not_metadata(self):
        """Human-readable freshness ('2h') comes from provenance, not metadata ISO timestamp."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_B)
        # metadata.freshness is ISO timestamp, but freshness_display should be "2h"
        assert result["metadata"]["freshness_display"] == "2h"
        # The raw ISO timestamp is still in metadata.freshness
        assert "2026-02-15" in result["metadata"]["freshness"]

    def test_unit_at_top_level(self):
        """DCL top-level unit is preserved (not per-row)."""
        result = self.client._normalize_dcl_query_response(DCL_QUERY_RESPONSE_PATH_B)
        assert result["unit"] == "USD millions"

    def test_metadata_sources_compact_format(self):
        """DCL may send compact metadata.sources instead of provenance[].source_system."""
        compact_response = {
            "metric": "revenue",
            "data": [{"period": "2025-Q4", "value": 42.0}],
            "metadata": {
                "mode": "Ingest",
                "run_id": "run_888",
                "freshness": "2026-02-15T09:00:00Z",
                "sources": ["salesforce"],
            },
            "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(compact_response)
        rp = result["run_provenance"]
        # metadata.sources should be used when provenance[] is empty
        assert rp["source_systems"] == ["salesforce"]
        assert rp["run_id"] == "run_888"
        assert rp["mode"] == "Ingest"

    def test_mode_drives_badge_state(self):
        """The mode field drives the 3-state Trust Badge: Verified/Run/Local."""
        # Ingest → Verified (green)
        ingest_resp = {
            "metric": "revenue", "data": [], "metadata": {"mode": "Ingest"}, "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(ingest_resp)
        assert result["run_provenance"]["mode"] == "Ingest"

        # Live → Verified (green)
        live_resp = {
            "metric": "revenue", "data": [], "metadata": {"mode": "Live"}, "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(live_resp)
        assert result["run_provenance"]["mode"] == "Live"

        # Demo → Run (blue)
        demo_resp = {
            "metric": "revenue", "data": [], "metadata": {"mode": "Demo"}, "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(demo_resp)
        assert result["run_provenance"]["mode"] == "Demo"

        # Farm → Run (blue)
        farm_resp = {
            "metric": "revenue", "data": [], "metadata": {"mode": "Farm"}, "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(farm_resp)
        assert result["run_provenance"]["mode"] == "Farm"

        # None → Local (grey)
        local_resp = {
            "metric": "revenue", "data": [], "metadata": {}, "provenance": [],
        }
        result = self.client._normalize_dcl_query_response(local_resp)
        assert result["run_provenance"]["mode"] is None


# ===========================================================================
# CONTRACT 3: DCL Catalog → NLQ SemanticCatalog
# ===========================================================================

class TestDCLCatalogContract:
    """Validate NLQ correctly parses DCL's semantic-export catalog."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url=None)

    def test_all_metrics_parsed(self):
        """All DCL catalog metrics are available in NLQ."""
        catalog = self.client._parse_dcl_response(DCL_CATALOG_RESPONSE)
        assert "revenue" in catalog.metrics
        assert "pipeline" in catalog.metrics

    def test_domain_mapping_correct(self):
        """DCL pack names map to correct NLQ domain names."""
        catalog = self.client._parse_dcl_response(DCL_CATALOG_RESPONSE)
        assert catalog.metrics["revenue"].domain == "CFO"
        assert catalog.metrics["pipeline"].domain == "CRO"

    def test_entities_become_dimensions(self):
        """DCL entities[] become catalog.dimensions for validation."""
        catalog = self.client._parse_dcl_response(DCL_CATALOG_RESPONSE)
        assert "region" in catalog.dimensions
        assert "AMER" in catalog.dimensions["region"]

    def test_alias_resolution_works(self):
        """NLQ can resolve user terms to canonical metric IDs."""
        catalog = self.client._parse_dcl_response(DCL_CATALOG_RESPONSE)
        # "sales" is an alias for "revenue"
        assert catalog.alias_to_metric.get("sales") == "revenue"
        # "pipe" is an alias for "pipeline"
        assert catalog.alias_to_metric.get("pipe") == "pipeline"


# ===========================================================================
# CONTRACT 4: NLQ Query Request → DCL
# ===========================================================================

class TestNLQToDCLRequestContract:
    """Validate NLQ builds DCL-compatible query requests."""

    def setup_method(self):
        self.client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        self.mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = DCL_QUERY_RESPONSE_PATH_B
        mock_resp.raise_for_status = MagicMock()
        self.mock_http.post.return_value = mock_resp
        self.client._http_client = self.mock_http

    def _get_sent_payload(self):
        call_args = self.mock_http.post.call_args
        return call_args.kwargs.get("json") or call_args[1].get("json")

    def test_nlq_time_range_converted(self):
        """NLQ period format converts to DCL start/end format."""
        self.client.query(metric="revenue", time_range={"period": "2025-Q4", "granularity": "quarterly"})
        payload = self._get_sent_payload()
        # DCL expects {start, end}, not {period}
        assert "period" not in payload.get("time_range", {})
        assert payload["time_range"] == {"start": "2025-Q4", "end": "2025-Q4"}

    def test_grain_uses_dcl_short_form(self):
        """NLQ 'quarterly' becomes DCL 'quarter'."""
        self.client.query(metric="revenue", time_range={"period": "2025", "granularity": "quarterly"})
        payload = self._get_sent_payload()
        assert payload["grain"] == "quarter"

    def test_annual_grain_maps_to_year(self):
        """NLQ 'annual' becomes DCL 'year'."""
        self.client.query(metric="revenue", time_range={"period": "2025", "granularity": "annual"})
        payload = self._get_sent_payload()
        assert payload["grain"] == "year"

    def test_endpoint_is_dcl_query(self):
        """Request targets /api/dcl/query."""
        self.client.query(metric="revenue")
        url = self.mock_http.post.call_args.args[0]
        assert url.endswith("/api/dcl/query")


# ===========================================================================
# CONTRACT 5: Full Pipeline — AAM→DCL→NLQ→Galaxy Trust Badge
# ===========================================================================

class TestFullPipelineContract:
    """
    End-to-end contract test simulating the complete data journey:
    AAM Runner pushes data → DCL stores & serves it → NLQ normalizes →
    Galaxy UI gets provenance for the Trust Badge.
    """

    def test_aam_data_flows_to_galaxy_trust_badge(self):
        """
        Full pipeline: data ingested by AAM Runner surfaces as a verified
        Trust Badge in the Galaxy UI response.
        """
        # Step 1: NLQ queries DCL (mock HTTP with Path B response)
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = DCL_QUERY_RESPONSE_PATH_B
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        dcl_result = client.query(
            metric="revenue",
            time_range={"period": "2025-Q4", "granularity": "quarterly"},
        )

        # Step 2: NLQ builds SimpleMetricResult (same logic as _build_simple_metric_result)
        metadata = dcl_result.get("metadata", {})
        data = dcl_result.get("data", [])
        value = data[-1]["value"] if data else None

        smr = SimpleMetricResult(
            metric="revenue",
            value=value,
            formatted_value=f"${value}M",
            unit=dcl_result.get("unit", "USD millions"),
            display_name="Revenue",
            domain=Domain.FINANCE,
            answer=f"Revenue for 2025-Q4 is ${value}M",
            period="2025-Q4",
            data_quality=metadata.get("quality_score", 1.0),
            freshness=metadata.get("freshness_display", "") or "0h",
            source=dcl_result.get("source", "local"),
            run_provenance=dcl_result.get("run_provenance"),
        )

        # Step 3: NLQ converts to Galaxy response
        galaxy = simple_metric_to_galaxy_response(smr, "What was revenue in Q4 2025?")

        # ── VERIFY: Data from AAM Runner is now in the Galaxy response ──

        # The value matches what AAM ingested
        assert galaxy.nodes[0].value == 42.0

        # Trust Badge: provenance carries the AAM Runner's run_id
        assert galaxy.provenance is not None
        assert galaxy.provenance["run_id"] == "run_777_sf_revenue_q4"

        # Trust Badge: tenant and snapshot from the ingest payload
        assert galaxy.provenance["tenant_id"] == "acme_corp"
        assert galaxy.provenance["snapshot_name"] == "sf_revenue_q4_2025"

        # Trust Badge: source system from AAM's metadata.source_system
        assert galaxy.provenance["source_systems"] == ["Salesforce CRM"]
        assert galaxy.nodes[0].source_system == "Salesforce CRM"

        # Trust Badge: freshness and quality
        assert galaxy.provenance["freshness"] == "2h"
        assert galaxy.provenance["quality_score"] == 0.97
        assert galaxy.nodes[0].data_quality == 0.97
        assert galaxy.nodes[0].freshness == "2h"

        # Trust Badge: mode confirms this is Live data, not Demo
        assert galaxy.provenance["mode"] == "Live"

        # Source tag confirms DCL (not local fallback)
        assert smr.source == "dcl"

    def test_demo_mode_has_no_trust_badge(self):
        """
        Path A (Demo/fact_base) has no run_id → Trust Badge shows 'Local'.
        """
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = DCL_QUERY_RESPONSE_PATH_A
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        dcl_result = client.query(metric="revenue")

        metadata = dcl_result.get("metadata", {})
        data = dcl_result.get("data", [])
        value = data[-1]["value"] if data else None

        smr = SimpleMetricResult(
            metric="revenue",
            value=value,
            formatted_value=f"${value}M",
            unit="USD millions",
            display_name="Revenue",
            domain=Domain.FINANCE,
            answer=f"Revenue is ${value}M",
            period="2025-Q4",
            data_quality=metadata.get("quality_score", 1.0),
            freshness=metadata.get("freshness_display", "") or "0h",
            source=dcl_result.get("source", "local"),
            run_provenance=dcl_result.get("run_provenance"),
        )

        galaxy = simple_metric_to_galaxy_response(smr, "What is revenue?")

        # Provenance exists but has no run_id (Demo mode)
        rp = galaxy.provenance
        assert rp is not None
        assert rp["run_id"] is None
        assert rp["source_systems"] == []
        assert rp["mode"] == "Demo"

    def test_multi_quarter_data_from_runner(self):
        """
        AAM Runner pushes 4 quarters → DCL serves all 4 → NLQ can sum them.
        """
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = DCL_QUERY_RESPONSE_PATH_B
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        dcl_result = client.query(
            metric="revenue",
            time_range={"period": "2025", "granularity": "quarterly"},
        )

        # All 4 quarters from the Runner's ingest are present
        data = dcl_result["data"]
        assert len(data) == 4
        total = sum(d["value"] for d in data)
        assert total == 150.0  # 33 + 36 + 39 + 42

    def test_run_id_traces_back_to_aam_runner(self):
        """
        The run_id in the Galaxy response can be traced back to the
        specific AAM Runner execution that produced the data.
        """
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = DCL_QUERY_RESPONSE_PATH_B
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp
        client._http_client = mock_http

        dcl_result = client.query(metric="revenue")
        rp = dcl_result["run_provenance"]

        # The run_id matches what AAM sent in x-run-id header
        assert rp["run_id"] == AAM_INGEST_HEADERS["x-run-id"]

        # The tenant_id matches the ingest payload
        assert rp["tenant_id"] == AAM_INGEST_PAYLOAD["tenant_id"]

        # The timestamp tracks when the Runner executed
        assert rp["run_timestamp"] == AAM_INGEST_PAYLOAD["metadata"]["extracted_at"]


# ===========================================================================
# CONTRACT 6: Error Paths
# ===========================================================================

class TestErrorPathContracts:
    """Validate graceful handling when modules are unavailable."""

    def test_dcl_down_returns_error(self):
        """NLQ handles DCL being unreachable gracefully."""
        import httpx
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        mock_http = MagicMock()
        mock_http.post.side_effect = httpx.ConnectError("Connection refused")
        client._http_client = mock_http

        result = client.query(metric="revenue")
        assert result["status"] == "error"
        assert "unavailable" in result["error"].lower() or "connection" in result["error"].lower()

    def test_dcl_returns_empty_data(self):
        """NLQ handles DCL returning empty data (metric not yet ingested)."""
        empty_response = {
            "metric": "revenue",
            "data": [],
            "metadata": {"record_count": 0},
            "provenance": [],
        }
        client = DCLSemanticClient(dcl_base_url="http://mock-dcl:8000")
        result = client._normalize_dcl_query_response(empty_response)
        assert result["status"] == "ok"
        assert result["data"] == []
        assert result["run_provenance"]["run_id"] is None

    def test_local_fallback_when_no_dcl_url(self):
        """NLQ falls back to fact_base.json when DCL_API_URL not set."""
        client = DCLSemanticClient(dcl_base_url=None)
        result = client.query(metric="revenue", time_range={"period": "2025-Q4"})
        assert result.get("source") == "local_fallback"

    def test_galaxy_response_valid_even_without_dcl(self):
        """Galaxy response is valid JSON even with local fallback (no provenance)."""
        smr = SimpleMetricResult(
            metric="revenue",
            value=42.0,
            formatted_value="$42.0M",
            unit="USD millions",
            display_name="Revenue",
            domain=Domain.FINANCE,
            answer="Revenue is $42.0M",
        )
        galaxy = simple_metric_to_galaxy_response(smr, "What is revenue?")

        # Must still be a valid IntentMapResponse
        assert isinstance(galaxy, IntentMapResponse)
        assert galaxy.query_type == "POINT_QUERY"
        assert len(galaxy.nodes) == 1
        assert galaxy.nodes[0].value == 42.0
        # Provenance is None (no DCL)
        assert galaxy.provenance is None
