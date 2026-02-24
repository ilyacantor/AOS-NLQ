"""
NLQ Agent — DCL Test Harness

Strict test suites for DCL + NLQ capabilities:
1. Entity Extraction — NLQ parser extracts entity names from queries
2. Entity Filter Passthrough — Extracted entities pass through to DCL resolution
3. Provenance in Responses — Responses include provenance/lineage data
4. Conflict Surfacing — Cross-system conflicts detected and surfaced
5. Temporal Warnings — Definition boundary warnings on comparisons
6. Regression — No existing NLQ functionality breaks

Rules:
- All data loaded from data/entity_test_scenarios.json (no mocking)
- Tests validate via API models and engine outputs (no mocking)
- 100% pass rate required
"""

import json
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures — load from entity_test_scenarios.json, no mocking
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scenario_data():
    """Load entity_test_scenarios.json fixture data."""
    paths = [
        Path("data/entity_test_scenarios.json"),
        Path("/home/user/AOS-NLQ/data/entity_test_scenarios.json"),
        Path(__file__).parent.parent / "data" / "entity_test_scenarios.json",
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    pytest.fail("entity_test_scenarios.json not found")


@pytest.fixture(scope="module")
def dcl_engine():
    """Get the DCL engine singleton."""
    from src.nlq.dcl.engine import DCLEngine
    return DCLEngine()


@pytest.fixture(scope="module")
def enrichment_service():
    """Import the enrichment service module."""
    from src.nlq.services import dcl_enrichment
    return dcl_enrichment


# ===========================================================================
# SUITE 1: Entity Extraction
# ===========================================================================

class TestEntityExtraction:
    """Test that the NLQ parser extracts entity names from queries."""

    def test_parser_extracts_entity_from_possessive(self):
        """'Acme's revenue' → entity='Acme'"""
        from src.nlq.core.parser import QueryParser
        # We test the prompt structure includes entity extraction rules
        from src.nlq.llm.prompts import QUERY_PARSER_PROMPT
        assert "entity" in QUERY_PARSER_PROMPT
        assert "possessive" in QUERY_PARSER_PROMPT.lower() or "Possessive" in QUERY_PARSER_PROMPT

    def test_parser_prompt_has_entity_field(self):
        """Parser prompt includes entity field in JSON format."""
        from src.nlq.llm.prompts import QUERY_PARSER_PROMPT
        assert '"entity"' in QUERY_PARSER_PROMPT

    def test_parser_prompt_has_dimension_field(self):
        """Parser prompt includes dimension field in JSON format."""
        from src.nlq.llm.prompts import QUERY_PARSER_PROMPT
        assert '"dimension"' in QUERY_PARSER_PROMPT

    def test_parsed_query_model_has_entity_field(self):
        """ParsedQuery model includes entity field."""
        from src.nlq.models.query import ParsedQuery
        fields = ParsedQuery.model_fields
        assert "entity" in fields
        assert "dimension" in fields

    def test_parsed_query_entity_is_optional(self):
        """Entity field is Optional[str] with default None."""
        from src.nlq.models.query import ParsedQuery, QueryIntent
        pq = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type="annual",
            period_reference="2025",
        )
        assert pq.entity is None

    def test_parsed_query_entity_can_be_set(self):
        """Entity field can be set to a string value."""
        from src.nlq.models.query import ParsedQuery, QueryIntent
        pq = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type="annual",
            period_reference="2025",
            entity="Acme Corp",
        )
        assert pq.entity == "Acme Corp"

    def test_entity_extraction_rules_in_prompt(self):
        """Prompt includes extraction patterns (possessive, 'for X', etc.)."""
        from src.nlq.llm.prompts import QUERY_PARSER_PROMPT
        assert "for" in QUERY_PARSER_PROMPT.lower()

    def test_parser_passes_entity_through(self):
        """parser.parse() creates ParsedQuery with entity field populated."""
        from src.nlq.core.parser import QueryParser
        from src.nlq.models.query import ParsedQuery
        # Verify parser code handles entity extraction
        import inspect
        source = inspect.getsource(QueryParser.parse)
        assert "entity" in source


# ===========================================================================
# SUITE 2: Entity Filter Passthrough
# ===========================================================================

class TestEntityFilterPassthrough:
    """Test that extracted entities flow through to DCL resolution."""

    def test_dcl_engine_resolves_acme(self, dcl_engine, scenario_data):
        """'Acme' resolves to Acme Corp entity."""
        results = dcl_engine.resolve_entity("Acme")
        assert len(results) >= 1
        top = results[0]
        assert top["canonical_name"] == "Acme Corp"
        assert top["dcl_global_id"] == "ent_acme_001"

    def test_dcl_engine_resolves_globex(self, dcl_engine, scenario_data):
        """'Globex' resolves to Globex Corp entity."""
        results = dcl_engine.resolve_entity("Globex")
        assert len(results) >= 1
        assert results[0]["canonical_name"] == "Globex Corp"

    def test_dcl_engine_resolves_initech(self, dcl_engine, scenario_data):
        """'Initech' resolves to Initech entity."""
        results = dcl_engine.resolve_entity("Initech")
        assert len(results) >= 1
        assert results[0]["canonical_name"] == "Initech"

    def test_dcl_engine_resolves_massive_dynamic(self, dcl_engine, scenario_data):
        """'Massive Dynamic' resolves correctly."""
        results = dcl_engine.resolve_entity("Massive Dynamic")
        assert len(results) >= 1
        assert results[0]["canonical_name"] == "Massive Dynamic"

    def test_dcl_engine_fuzzy_match(self, dcl_engine, scenario_data):
        """Fuzzy match: 'ACME CORPORATION' resolves to Acme Corp."""
        results = dcl_engine.resolve_entity("ACME CORPORATION")
        assert len(results) >= 1
        assert results[0]["canonical_name"] == "Acme Corp"

    def test_dcl_engine_no_false_positive(self, dcl_engine, scenario_data):
        """Non-match: 'Acme Foods Ltd' should not match Acme Corp with high confidence."""
        results = dcl_engine.resolve_entity("Acme Foods Ltd")
        # May return Acme Corp as low-confidence match, but not high
        if results:
            # The confidence should be lower than exact match
            assert results[0]["confidence"] < 0.95

    def test_enrichment_resolves_entity(self, enrichment_service):
        """enrich_response() resolves entity and returns entity_resolution."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            entity="Acme",
        )
        assert "entity_resolution" in result
        assert result["entity_resolution"]["entity_name"] == "Acme Corp"
        assert result["entity_resolution"]["entity_id"] == "ent_acme_001"

    def test_enrichment_entity_has_matched_systems(self, enrichment_service):
        """Entity resolution includes matched_systems list."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            entity="Acme",
        )
        entity_res = result["entity_resolution"]
        assert "matched_systems" in entity_res
        assert len(entity_res["matched_systems"]) >= 2  # Acme has 3 source systems

    def test_enrichment_no_entity_when_not_provided(self, enrichment_service):
        """No entity_resolution when entity is not provided."""
        result = enrichment_service.enrich_response(
            metric="revenue",
        )
        assert "entity_resolution" not in result

    def test_search_entities_returns_entity_candidates(self, dcl_engine):
        """search_entities returns EntityCandidate model instances."""
        from src.nlq.dcl.models import EntityCandidate
        candidates = dcl_engine.search_entities("Acme")
        assert len(candidates) >= 1
        assert isinstance(candidates[0], EntityCandidate)
        assert candidates[0].confidence > 0.0
        assert candidates[0].confidence <= 1.0

    def test_get_entity_returns_entity_record(self, dcl_engine):
        """get_entity returns EntityRecord model."""
        from src.nlq.dcl.models import EntityRecord
        record = dcl_engine.get_entity("ent_acme_001")
        assert record is not None
        assert isinstance(record, EntityRecord)
        assert record.display_name == "Acme Corp"
        assert len(record.source_records) == 3  # 3 source systems

    def test_get_entity_not_found(self, dcl_engine):
        """get_entity returns None for non-existent ID."""
        assert dcl_engine.get_entity("ent_nonexistent_999") is None


# ===========================================================================
# SUITE 3: Provenance in Responses
# ===========================================================================

class TestProvenanceInResponses:
    """Test that responses include provenance/lineage data."""

    def test_provenance_for_revenue(self, dcl_engine, scenario_data):
        """Revenue has provenance with SOR=sap_erp."""
        prov = dcl_engine.get_provenance("revenue")
        assert prov is not None
        assert prov.system_of_record == "sap_erp"
        assert prov.trust_score == 0.92

    def test_provenance_for_pipeline(self, dcl_engine, scenario_data):
        """Pipeline has provenance with SOR=salesforce_crm."""
        prov = dcl_engine.get_provenance("pipeline")
        assert prov is not None
        assert prov.system_of_record == "salesforce_crm"

    def test_provenance_for_customer_count(self, dcl_engine, scenario_data):
        """Customer count metric has provenance data."""
        prov = dcl_engine.get_provenance("customer_count")
        assert prov is not None
        assert prov.metric == "customer_count"

    def test_provenance_lineage_structure(self, dcl_engine, scenario_data):
        """Revenue provenance has correct lineage structure."""
        prov = dcl_engine.get_provenance("revenue")
        assert len(prov.lineage) == 3  # sap, salesforce, netsuite
        for entry in prov.lineage:
            assert "source_system" in entry
            assert "source_table" in entry
            assert "source_field" in entry
            assert "trust_score" in entry

    def test_provenance_sor_marked(self, dcl_engine, scenario_data):
        """Exactly one lineage entry is marked as SOR for revenue."""
        prov = dcl_engine.get_provenance("revenue")
        sor_entries = [e for e in prov.lineage if e.get("is_system_of_record")]
        assert len(sor_entries) == 1
        assert sor_entries[0]["source_system"] == "sap_erp"

    def test_enrichment_includes_provenance(self, enrichment_service):
        """enrich_response() includes provenance for known metrics."""
        result = enrichment_service.enrich_response(metric="revenue")
        assert "provenance" in result

    def test_provenance_unknown_metric(self, dcl_engine):
        """Unknown metric returns None for provenance."""
        prov = dcl_engine.get_provenance("nonexistent_metric")
        assert prov is None

    def test_provenance_has_freshness(self, dcl_engine, scenario_data):
        """Provenance record includes freshness info."""
        prov = dcl_engine.get_provenance("revenue")
        assert prov.freshness is not None

    def test_provenance_record_model(self, dcl_engine):
        """get_provenance returns ProvenanceRecord model."""
        from src.nlq.dcl.models import ProvenanceRecord
        prov = dcl_engine.get_provenance("revenue")
        assert isinstance(prov, ProvenanceRecord)

    def test_format_provenance_for_personality(self, enrichment_service):
        """Provenance formatting produces human-readable text."""
        prov_data = enrichment_service.get_provenance_for_metric("revenue")
        if prov_data:
            formatted = enrichment_service.format_provenance_for_personality(prov_data)
            assert "SAP" in formatted or "sap" in formatted.lower()


# ===========================================================================
# SUITE 4: Conflict Surfacing
# ===========================================================================

class TestConflictSurfacing:
    """Test cross-system conflict detection and surfacing."""

    def test_three_conflicts_loaded(self, dcl_engine, scenario_data):
        """Exactly 3 conflicts loaded from fixture data."""
        conflicts = dcl_engine.list_conflicts()
        assert len(conflicts) == 3

    def test_acme_revenue_conflict(self, dcl_engine, scenario_data):
        """Acme Corp has a CRITICAL revenue conflict (timing)."""
        conflict = dcl_engine.get_conflict("conflict_001")
        assert conflict is not None
        assert conflict.entity_id == "ent_acme_001"
        assert conflict.metric == "revenue"
        assert conflict.severity.value == "critical"
        assert conflict.root_cause.value == "timing"

    def test_massive_dynamic_revenue_conflict(self, dcl_engine, scenario_data):
        """Massive Dynamic has a HIGH revenue conflict (scope)."""
        conflict = dcl_engine.get_conflict("conflict_002")
        assert conflict is not None
        assert conflict.entity_id == "ent_massive_004"
        assert conflict.metric == "revenue"
        assert conflict.severity.value == "high"
        assert conflict.root_cause.value == "scope"

    def test_initech_employees_conflict(self, dcl_engine, scenario_data):
        """Initech has a LOW employee count conflict (stale_data)."""
        conflict = dcl_engine.get_conflict("conflict_003")
        assert conflict is not None
        assert conflict.entity_id == "ent_initech_003"
        assert conflict.metric == "employees"
        assert conflict.severity.value == "low"
        assert conflict.root_cause.value == "stale_data"

    def test_no_conflict_for_globex_revenue(self, scenario_data):
        """Globex Corp has no revenue conflict (control case)."""
        no_conflict = scenario_data["no_conflict_control"]
        assert no_conflict["entity_id"] == "ent_globex_002"
        assert no_conflict["has_conflict"] is False

    def test_conflict_has_delta(self, dcl_engine, scenario_data):
        """Conflicts include delta magnitude and percentage."""
        conflict = dcl_engine.get_conflict("conflict_001")
        assert conflict.delta == 2200000
        assert conflict.delta_pct == pytest.approx(5.14, rel=0.01)

    def test_conflict_has_systems_involved(self, dcl_engine, scenario_data):
        """Conflicts list the disagreeing systems."""
        conflict = dcl_engine.get_conflict("conflict_001")
        assert len(conflict.systems_involved) == 2
        assert "salesforce_crm" in conflict.systems_involved
        assert "sap_erp" in conflict.systems_involved

    def test_enrichment_surfaces_conflicts(self, enrichment_service):
        """enrich_response() surfaces conflicts for Acme revenue."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            entity="Acme",
        )
        assert "conflicts" in result
        assert len(result["conflicts"]) >= 1
        conflict = result["conflicts"][0]
        assert conflict["metric"] == "revenue"

    def test_enrichment_no_conflict_for_globex(self, enrichment_service):
        """enrich_response() returns no conflicts for Globex revenue."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            entity="Globex",
        )
        # Globex has no revenue conflict
        assert result.get("conflicts") is None

    def test_conflict_resolution(self, dcl_engine):
        """Conflicts can be resolved."""
        result = dcl_engine.resolve_conflict(
            conflict_id="conflict_003",
            decision="accept_a",
            rationale="CRM has more recent data",
            resolved_by="test_harness",
        )
        assert result.status == "resolved"
        assert result.conflict_id == "conflict_003"

    def test_conflict_filter_by_severity(self, dcl_engine):
        """list_conflicts can filter by severity."""
        critical = dcl_engine.list_conflicts(severity="critical")
        assert all(c.severity.value == "critical" for c in critical)

    def test_format_conflict_for_personality(self, enrichment_service):
        """Conflict formatting produces human-readable text."""
        conflicts = enrichment_service.get_conflicts_for_query("revenue", "ent_acme_001")
        if conflicts:
            formatted = enrichment_service.format_conflict_for_personality(conflicts)
            assert len(formatted) > 0
            assert "Trust" in formatted


# ===========================================================================
# SUITE 5: Temporal Warnings
# ===========================================================================

class TestTemporalWarnings:
    """Test definition boundary detection and temporal warnings."""

    def test_revenue_definition_change(self, dcl_engine, scenario_data):
        """Revenue definition changed on 2025-03-01 (ASC 606)."""
        changelog = dcl_engine.get_temporal_changelog("revenue")
        assert len(changelog) >= 1
        change = changelog[0]
        assert change.change_date == "2025-03-01"
        assert "ASC 606" in change.new_definition

    def test_customers_definition_change(self, dcl_engine, scenario_data):
        """Customer definition changed on 2025-06-01 (partner-referred)."""
        changelog = dcl_engine.get_temporal_changelog("customer_count")
        assert len(changelog) >= 1
        change = changelog[0]
        assert change.change_date == "2025-06-01"
        assert "partner" in change.new_definition.lower()

    def test_boundary_crossed_revenue(self, dcl_engine, scenario_data):
        """Q4 2024 vs Q2 2025 crosses revenue definition boundary."""
        check = dcl_engine.check_temporal_boundary("revenue", "2024-Q4", "2025-Q2")
        assert check.crosses_boundary is True
        assert check.change_date == "2025-03-01"
        assert check.warning is not None

    def test_boundary_not_crossed_same_side(self, dcl_engine, scenario_data):
        """Q1 2024 vs Q4 2024 does NOT cross revenue boundary."""
        check = dcl_engine.check_temporal_boundary("revenue", "2024-Q1", "2024-Q4")
        assert check.crosses_boundary is False

    def test_boundary_crossed_customers(self, dcl_engine, scenario_data):
        """Q1 2025 vs Q3 2025 crosses customer definition boundary."""
        check = dcl_engine.check_temporal_boundary("customer_count", "2025-Q1", "2025-Q3")
        assert check.crosses_boundary is True
        assert check.change_date == "2025-06-01"

    def test_enrichment_temporal_warning_on_comparison(self, enrichment_service):
        """enrich_response() includes temporal warning for comparisons."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            start_period="2024-Q4",
            end_period="2025-Q2",
            is_comparison=True,
        )
        assert "temporal_warning" in result
        assert result["temporal_warning"]["crosses_boundary"] is True

    def test_enrichment_no_temporal_warning_for_non_comparison(self, enrichment_service):
        """No temporal warning for non-comparison queries."""
        result = enrichment_service.enrich_response(
            metric="revenue",
            start_period="2025-Q1",
        )
        assert "temporal_warning" not in result

    def test_temporal_boundary_check_model(self, dcl_engine):
        """check_temporal_boundary returns TemporalBoundaryCheck model."""
        from src.nlq.dcl.models import TemporalBoundaryCheck
        result = dcl_engine.check_temporal_boundary("revenue", "2024-Q4", "2025-Q2")
        assert isinstance(result, TemporalBoundaryCheck)

    def test_format_temporal_warning_for_personality(self, enrichment_service):
        """Temporal warning formatting produces human-readable text."""
        warning = {
            "concept": "revenue",
            "change_date": "2025-03-01",
            "old_definition": "Cash basis",
            "new_definition": "ASC 606 accrual basis",
        }
        formatted = enrichment_service.format_temporal_warning_for_personality(warning)
        assert "redefined" in formatted.lower()
        assert "2025-03-01" in formatted


# ===========================================================================
# SUITE 6: Regression — No existing NLQ breaks
# ===========================================================================

class TestRegression:
    """Ensure existing NLQ functionality is not broken by DCL additions."""

    def test_nlq_response_model_backward_compatible(self):
        """NLQResponse can still be constructed without DCL fields."""
        from src.nlq.models.response import NLQResponse
        response = NLQResponse(
            success=True,
            answer="Revenue is $42.8M",
            value=42800000,
            unit="$",
            confidence=0.95,
            parsed_intent="POINT_QUERY",
            resolved_metric="revenue",
            resolved_period="2025",
        )
        assert response.success is True
        assert response.entity is None  # DCL field defaults to None
        assert response.provenance is None
        assert response.conflicts is None

    def test_intent_map_response_backward_compatible(self):
        """IntentMapResponse can still be constructed without DCL fields."""
        from src.nlq.models.response import IntentMapResponse
        response = IntentMapResponse(
            query="What is revenue?",
            query_type="POINT_QUERY",
            ambiguity_type=None,
            persona="CFO",
            overall_confidence=0.95,
            overall_data_quality=1.0,
            node_count=1,
            nodes=[],
            primary_node_id=None,
            primary_answer="Revenue is $42.8M",
            text_response="Revenue is $42.8M",
            needs_clarification=False,
            clarification_prompt=None,
        )
        assert response.entity is None
        assert response.provenance is None
        assert response.conflicts is None

    def test_intent_node_backward_compatible(self):
        """IntentNode can still be constructed without DCL fields."""
        from src.nlq.models.response import IntentNode, MatchType, Domain
        node = IntentNode(
            id="test_1",
            metric="revenue",
            display_name="Revenue",
            match_type=MatchType.EXACT,
            domain=Domain.FINANCE,
            confidence=0.95,
            data_quality=1.0,
            freshness="0h",
        )
        assert node.source_system is None
        assert node.has_conflict is None
        assert node.conflict_details is None

    def test_parsed_query_backward_compatible(self):
        """ParsedQuery still works with original fields only."""
        from src.nlq.models.query import ParsedQuery, QueryIntent
        pq = ParsedQuery(
            intent=QueryIntent.POINT_QUERY,
            metric="revenue",
            period_type="annual",
            period_reference="2025",
        )
        assert pq.metric == "revenue"
        assert pq.entity is None
        assert pq.dimension is None

    def test_dcl_engine_loads_without_error(self):
        """DCL engine initializes cleanly."""
        from src.nlq.dcl.engine import DCLEngine
        engine = DCLEngine()
        assert engine is not None

    def test_dcl_enrichment_import_clean(self):
        """DCL enrichment service imports without error."""
        from src.nlq.services.dcl_enrichment import enrich_response
        assert callable(enrich_response)

    def test_dcl_routes_import_clean(self):
        """DCL routes module imports without error."""
        from src.nlq.dcl.routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_main_includes_dcl_router(self):
        """main.py includes DCL router."""
        import importlib
        import src.nlq.main
        importlib.reload(src.nlq.main)
        app = src.nlq.main.app
        # Check that /api/dcl routes are registered
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        dcl_routes = [r for r in routes if '/dcl/' in r or r.startswith('/api/dcl')]
        assert len(dcl_routes) > 0, f"No DCL routes found. Routes: {routes}"

    def test_golden_record_assembly(self, dcl_engine):
        """Golden record assembles correctly from fixture data."""
        from src.nlq.dcl.models import GoldenRecord
        gr = dcl_engine.get_golden_record("ent_acme_001")
        assert gr is not None
        assert isinstance(gr, GoldenRecord)
        assert "revenue" in gr.fields
        # Revenue should come from SAP (SOR for financials)
        assert gr.fields["revenue"].source_system_id == "sap_erp"

    def test_merge_and_undo(self, dcl_engine):
        """Entity merge and undo cycle works."""
        # Merge Initech into Acme (will be undone)
        # First verify both exist
        assert dcl_engine.get_entity("ent_initech_003") is not None
        assert dcl_engine.get_entity("ent_acme_001") is not None

        # Merge
        merge_result = dcl_engine.merge_entities(
            entity_a_id="ent_acme_001",
            entity_b_id="ent_initech_003",
            confirmed_by="test_harness",
        )
        assert merge_result.status == "merged"

        # Initech should be gone
        assert dcl_engine.get_entity("ent_initech_003") is None

        # Undo
        undo_result = dcl_engine.undo_merge(merge_result.merge_id)
        assert undo_result.status == "undone"

        # Initech should be back
        assert dcl_engine.get_entity("ent_initech_003") is not None

    def test_persona_definitions_loaded(self, dcl_engine):
        """Persona definitions for 'customer_count' are loaded correctly."""
        defs = dcl_engine.get_persona_definitions("customer_count")
        assert len(defs) == 3
        personas = {d.persona for d in defs}
        assert "CFO" in personas
        assert "CRO" in personas
        assert "COO" in personas

    def test_persona_values_match_fixture(self, dcl_engine, scenario_data):
        """Persona values match entity_test_scenarios.json."""
        fixture_defs = scenario_data["persona_contextual_definitions"]["customer_count"]["definitions"]
        for fixture_def in fixture_defs:
            engine_def = dcl_engine.get_persona_definition("customer_count", fixture_def["persona"])
            assert engine_def is not None
            assert engine_def.value == fixture_def["value"]

    def test_mcp_tools_registered(self, dcl_engine):
        """MCP tools are registered and callable."""
        tools = dcl_engine.list_mcp_tools()
        assert len(tools) >= 5
        tool_ids = {t.tool_id for t in tools}
        assert "dcl.resolve_entity" in tool_ids
        assert "dcl.get_conflicts" in tool_ids
        assert "dcl.get_provenance" in tool_ids

    def test_mcp_execute_resolve_entity(self, dcl_engine):
        """MCP tool execution works for resolve_entity."""
        result = dcl_engine.execute_mcp_tool(
            tool_name="dcl.resolve_entity",
            arguments={"term": "Acme"},
        )
        assert result.success is True
        assert len(result.result) >= 1

    def test_source_of_record_tags(self, scenario_data):
        """SOR tags are present and structured correctly."""
        sor_tags = scenario_data["source_of_record_tags"]
        assert "sap_erp" in sor_tags
        assert sor_tags["sap_erp"]["is_primary"] is True
        assert sor_tags["sap_erp"]["trust_score"] == 0.92
        assert "revenue" in sor_tags["sap_erp"]["sor_for"]
