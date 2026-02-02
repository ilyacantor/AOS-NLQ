"""
Superlative Query Tests
Tests ranking queries: largest, highest, best, top, worst, lowest, bottom

Ground Truth Source: fact_base.json (v4 - differentiated)
"""

import pytest
from tests.eval.conftest import collect_failures

from src.nlq.core.superlative_intent import (
    is_superlative_query,
    detect_superlative_intent,
    SuperlativeType,
    get_sort_order,
)
from src.nlq.services.dcl_semantic_client import get_semantic_client


# =============================================================================
# GROUND TRUTH (from fact_base.json 2026-Q4)
# =============================================================================

GROUND_TRUTH = {
    # Rep rankings - quota attainment (quota_by_rep.attainment_pct)
    "top_rep_quota": "Sarah Williams",
    "top_rep_quota_value": 115.0,
    "second_rep_quota": "Michael Brown",
    "second_rep_quota_value": 114.1,
    "worst_rep_quota": "Thomas Anderson",
    "worst_rep_quota_value": 83.0,

    # Rep rankings - win rate (win_rate_by_rep)
    "top_rep_win_rate": "Sarah Williams",
    "top_rep_win_rate_value": 52.0,
    "worst_rep_win_rate": "Thomas Anderson",
    "worst_rep_win_rate_value": 32.0,

    # Rep rankings - pipeline (pipeline_by_rep.pipeline)
    "top_rep_pipeline": "Sarah Williams",
    "top_rep_pipeline_value": 11.57,
    "worst_rep_pipeline": "Min-ji Park",
    "worst_rep_pipeline_value": 2.14,

    # Regional rankings
    "largest_region_revenue": "AMER",
    "largest_region_revenue_value": 25.0,
    "smallest_region_revenue": "APAC",
    "smallest_region_revenue_value": 10.0,
    "largest_region_pipeline": "AMER",
    "largest_region_pipeline_value": 71.88,

    # Segment rankings
    "largest_segment": "Enterprise",
    "largest_segment_revenue": 27.5,
    "smallest_segment": "SMB",
    "smallest_segment_revenue": 7.5,

    # Department rankings
    "largest_department": "Engineering",
    "largest_department_headcount": 145,
    "smallest_departments": ["People", "Finance"],  # Tied at 22
    "smallest_department_headcount": 22,

    # Service rankings (SLO)
    "best_services_slo": ["Payment Service", "Auth Service"],  # Tied at 99.9%
    "best_service_slo_pct": 99.9,
    "worst_service_slo": "Data Pipeline",
    "worst_service_slo_pct": 96.2,

    # Deal rankings (2026 full year)
    "largest_deal_company": "Titan Corp",
    "largest_deal_value": 5.5,
    "largest_deal_rep": "Michael Brown",

    # Pipeline stage rankings
    "largest_pipeline_stage": "Qualified",
    "largest_pipeline_stage_value": 43.12,
    "smallest_pipeline_stage": "Closed-Won",
    "smallest_pipeline_stage_value": 14.38,

    # Top 5 reps by quota attainment
    "top_5_reps_quota": [
        "Sarah Williams",
        "Michael Brown",
        "Emily Davis",
        "Anna Schmidt",
        "Wei Zhang"
    ],

    # Bottom 5 reps by quota attainment
    "bottom_5_reps_quota": [
        "Thomas Anderson",
        "Robert Kim",
        "James O'Brien",
        "Sophie Martin",
        "Marco Rossi"
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def query_ranking(dcl_client, metric, dimension, order_by="desc", limit=1, period="2026-Q4"):
    """Execute a ranking query using the DCL client."""
    return dcl_client.query_ranking(
        metric=metric,
        dimension=dimension,
        order_by=order_by,
        limit=limit,
        time_range={"period": period}
    )


def extract_top_name(result, dimension="rep"):
    """Extract the name of the #1 ranked item."""
    data = result.get("data", [])
    if data and len(data) > 0:
        return data[0].get(dimension) or data[0].get("name") or data[0].get("company")
    return None


def extract_top_value(result):
    """Extract the value of the #1 ranked item."""
    data = result.get("data", [])
    if data and len(data) > 0:
        item = data[0]
        # Try common value fields
        for key in ("value", "attainment_pct", "pipeline", "slo_attainment", "revenue", "headcount"):
            if key in item:
                return item[key]
    return None


def extract_names_list(result, dimension="rep"):
    """Extract list of names from ranked results."""
    data = result.get("data", [])
    return [
        item.get(dimension) or item.get("name") or item.get("company")
        for item in data
    ]


# =============================================================================
# SECTION 1: SUPERLATIVE INTENT DETECTION TESTS
# =============================================================================

class TestSuperlativeIntentDetection:
    """Test that superlative patterns are correctly detected."""

    def test_top_rep_detected(self):
        assert is_superlative_query("Who is our top rep?")

    def test_best_rep_detected(self):
        assert is_superlative_query("Who is our best rep?")

    def test_worst_rep_detected(self):
        assert is_superlative_query("Who is our worst rep?")

    def test_highest_detected(self):
        assert is_superlative_query("Who has the highest quota attainment?")

    def test_lowest_detected(self):
        assert is_superlative_query("Who has the lowest win rate?")

    def test_largest_detected(self):
        assert is_superlative_query("What's our largest deal?")

    def test_top_n_detected(self):
        assert is_superlative_query("Who are the top 5 reps?")

    def test_bottom_n_detected(self):
        assert is_superlative_query("Who are the bottom 5 reps?")

    def test_mvp_detected(self):
        assert is_superlative_query("Who's our MVP?")

    def test_crushing_it_detected(self):
        assert is_superlative_query("Who's crushing it?")

    def test_non_superlative_not_detected(self):
        assert not is_superlative_query("What is our revenue?")

    def test_simple_metric_not_detected(self):
        assert not is_superlative_query("Show me ARR")


class TestRankingIntentExtraction:
    """Test that ranking intent is correctly extracted."""

    def test_top_rep_extracts_max(self):
        intent = detect_superlative_intent("Who is our top rep?")
        assert intent is not None
        assert intent.ranking_type == SuperlativeType.MAX
        assert intent.dimension == "rep"
        assert intent.limit == 1

    def test_worst_rep_extracts_min(self):
        intent = detect_superlative_intent("Who is our worst rep?")
        assert intent is not None
        assert intent.ranking_type == SuperlativeType.MIN
        assert intent.dimension == "rep"

    def test_top_5_extracts_count(self):
        intent = detect_superlative_intent("Who are the top 5 reps?")
        assert intent is not None
        assert intent.ranking_type == SuperlativeType.TOP_N
        assert intent.limit == 5

    def test_bottom_3_extracts_count(self):
        intent = detect_superlative_intent("Who are the bottom 3 services?")
        assert intent is not None
        assert intent.ranking_type == SuperlativeType.BOTTOM_N
        assert intent.limit == 3

    def test_largest_deal_extracts_deal_dimension(self):
        intent = detect_superlative_intent("What was our largest deal?")
        assert intent is not None
        assert intent.dimension == "deal"

    def test_mvp_defaults_to_quota_attainment(self):
        intent = detect_superlative_intent("Who's our MVP?")
        assert intent is not None
        assert intent.metric == "quota_attainment"
        assert intent.dimension == "rep"


# =============================================================================
# SECTION 2: TOP REP QUERIES (Sarah Williams = #1)
# =============================================================================

class TestTopRepQueries:
    """Test 'top rep' queries - Sarah Williams should always be #1."""

    def test_top_rep_by_quota(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "desc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["top_rep_quota"]

    def test_top_rep_quota_value(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["top_rep_quota_value"]

    def test_top_rep_by_win_rate(self, dcl_client):
        result = query_ranking(dcl_client, "win_rate", "rep", "desc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["top_rep_win_rate"]

    def test_top_rep_win_rate_value(self, dcl_client):
        result = query_ranking(dcl_client, "win_rate", "rep", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["top_rep_win_rate_value"]

    def test_top_rep_by_pipeline(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "rep", "desc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["top_rep_pipeline"]

    def test_top_rep_pipeline_value(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "rep", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["top_rep_pipeline_value"]


# =============================================================================
# SECTION 3: WORST REP QUERIES (Thomas Anderson = worst quota/win rate)
# =============================================================================

class TestWorstRepQueries:
    """Test 'worst rep' queries."""

    def test_worst_rep_by_quota(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "asc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["worst_rep_quota"]

    def test_worst_rep_quota_value(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "asc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["worst_rep_quota_value"]

    def test_worst_rep_by_win_rate(self, dcl_client):
        result = query_ranking(dcl_client, "win_rate", "rep", "asc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["worst_rep_win_rate"]

    def test_worst_rep_by_pipeline(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "rep", "asc", 1)
        assert extract_top_name(result, "rep") == GROUND_TRUTH["worst_rep_pipeline"]


# =============================================================================
# SECTION 4: TOP N QUERIES
# =============================================================================

class TestTopNQueries:
    """Test 'top 5', 'top 10' queries."""

    def test_top_5_reps_quota(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "desc", 5)
        names = extract_names_list(result, "rep")
        assert len(names) == 5
        assert names == GROUND_TRUTH["top_5_reps_quota"]

    def test_top_3_reps_quota(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "desc", 3)
        names = extract_names_list(result, "rep")
        assert len(names) == 3
        assert names[0] == "Sarah Williams"
        assert names[1] == "Michael Brown"
        assert names[2] == "Emily Davis"

    def test_top_3_regions(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "region", "desc", 3)
        names = extract_names_list(result, "region")
        assert names == ["AMER", "EMEA", "APAC"]


class TestBottomNQueries:
    """Test 'bottom 5', 'bottom 10' queries."""

    def test_bottom_5_reps_quota(self, dcl_client):
        result = query_ranking(dcl_client, "quota_attainment", "rep", "asc", 5)
        names = extract_names_list(result, "rep")
        assert len(names) == 5
        # Bottom 5 should include Thomas Anderson as first (worst)
        assert "Thomas Anderson" in names
        assert names[0] == "Thomas Anderson"


# =============================================================================
# SECTION 5: REGIONAL RANKINGS
# =============================================================================

class TestRegionalRankings:
    """Test regional superlative queries."""

    def test_largest_region_revenue(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "region", "desc", 1)
        assert extract_top_name(result, "region") == GROUND_TRUTH["largest_region_revenue"]

    def test_largest_region_revenue_value(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "region", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["largest_region_revenue_value"]

    def test_smallest_region_revenue(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "region", "asc", 1)
        assert extract_top_name(result, "region") == GROUND_TRUTH["smallest_region_revenue"]

    def test_largest_region_pipeline(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "region", "desc", 1)
        assert extract_top_name(result, "region") == GROUND_TRUTH["largest_region_pipeline"]


# =============================================================================
# SECTION 6: SEGMENT RANKINGS
# =============================================================================

class TestSegmentRankings:
    """Test segment superlative queries."""

    def test_largest_segment(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "segment", "desc", 1)
        assert extract_top_name(result, "segment") == GROUND_TRUTH["largest_segment"]

    def test_largest_segment_value(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "segment", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["largest_segment_revenue"]

    def test_smallest_segment(self, dcl_client):
        result = query_ranking(dcl_client, "revenue", "segment", "asc", 1)
        assert extract_top_name(result, "segment") == GROUND_TRUTH["smallest_segment"]


# =============================================================================
# SECTION 7: DEPARTMENT RANKINGS
# =============================================================================

class TestDepartmentRankings:
    """Test department superlative queries."""

    def test_largest_department(self, dcl_client):
        result = query_ranking(dcl_client, "headcount", "department", "desc", 1)
        assert extract_top_name(result, "department") == GROUND_TRUTH["largest_department"]

    def test_largest_department_value(self, dcl_client):
        result = query_ranking(dcl_client, "headcount", "department", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["largest_department_headcount"]

    def test_smallest_department(self, dcl_client):
        result = query_ranking(dcl_client, "headcount", "department", "asc", 1)
        name = extract_top_name(result, "department")
        # Accept either People or Finance (tied at 22)
        assert name in GROUND_TRUTH["smallest_departments"]


# =============================================================================
# SECTION 8: SERVICE SLO RANKINGS
# =============================================================================

class TestServiceRankings:
    """Test service SLO superlative queries."""

    def test_best_service_slo(self, dcl_client):
        result = query_ranking(dcl_client, "slo_attainment", "service", "desc", 1)
        name = extract_top_name(result, "service")
        # Accept either - they're tied at 99.9%
        assert name in GROUND_TRUTH["best_services_slo"]

    def test_best_service_slo_value(self, dcl_client):
        result = query_ranking(dcl_client, "slo_attainment", "service", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["best_service_slo_pct"]

    def test_worst_service_slo(self, dcl_client):
        result = query_ranking(dcl_client, "slo_attainment", "service", "asc", 1)
        assert extract_top_name(result, "service") == GROUND_TRUTH["worst_service_slo"]

    def test_worst_service_slo_value(self, dcl_client):
        result = query_ranking(dcl_client, "slo_attainment", "service", "asc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["worst_service_slo_pct"]


# =============================================================================
# SECTION 9: DEAL RANKINGS
# =============================================================================

class TestDealRankings:
    """Test deal superlative queries."""

    def test_largest_deal(self, dcl_client):
        result = query_ranking(dcl_client, "deal_value", "deal", "desc", 1, "2026")
        name = extract_top_name(result, "deal")
        assert name == GROUND_TRUTH["largest_deal_company"]

    def test_largest_deal_value(self, dcl_client):
        result = query_ranking(dcl_client, "deal_value", "deal", "desc", 1, "2026")
        assert extract_top_value(result) == GROUND_TRUTH["largest_deal_value"]

    def test_top_5_deals(self, dcl_client):
        result = query_ranking(dcl_client, "deal_value", "deal", "desc", 5, "2026")
        names = extract_names_list(result, "deal")
        assert len(names) == 5
        assert names[0] == "Titan Corp"
        assert names[1] == "OmniTech"


# =============================================================================
# SECTION 10: PIPELINE STAGE RANKINGS
# =============================================================================

class TestPipelineStageRankings:
    """Test pipeline stage superlative queries."""

    def test_largest_pipeline_stage(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "stage", "desc", 1)
        assert extract_top_name(result, "stage") == GROUND_TRUTH["largest_pipeline_stage"]

    def test_largest_pipeline_stage_value(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "stage", "desc", 1)
        assert extract_top_value(result) == GROUND_TRUTH["largest_pipeline_stage_value"]

    def test_smallest_pipeline_stage(self, dcl_client):
        result = query_ranking(dcl_client, "pipeline", "stage", "asc", 1)
        assert extract_top_name(result, "stage") == GROUND_TRUTH["smallest_pipeline_stage"]


# =============================================================================
# SECTION 11: SORT ORDER TESTS
# =============================================================================

class TestSortOrder:
    """Test sort order helper function."""

    def test_max_is_desc(self):
        assert get_sort_order(SuperlativeType.MAX) == "desc"

    def test_min_is_asc(self):
        assert get_sort_order(SuperlativeType.MIN) == "asc"

    def test_top_n_is_desc(self):
        assert get_sort_order(SuperlativeType.TOP_N) == "desc"

    def test_bottom_n_is_asc(self):
        assert get_sort_order(SuperlativeType.BOTTOM_N) == "asc"


# =============================================================================
# TEST COUNT SUMMARY
# =============================================================================
"""
Section 1: Superlative Detection      - 12 tests
Section 2: Ranking Intent Extraction  - 6 tests
Section 3: Top Rep Queries            - 6 tests
Section 4: Worst Rep Queries          - 4 tests
Section 5: Top N Queries              - 3 tests
Section 6: Bottom N Queries           - 1 test
Section 7: Regional Rankings          - 4 tests
Section 8: Segment Rankings           - 3 tests
Section 9: Department Rankings        - 3 tests
Section 10: Service SLO Rankings      - 4 tests
Section 11: Deal Rankings             - 3 tests
Section 12: Pipeline Stage Rankings   - 3 tests
Section 13: Sort Order Tests          - 4 tests
----------------------------------------
TOTAL                                 - 56 tests
"""
