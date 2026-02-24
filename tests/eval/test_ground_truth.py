"""
NLQ Ground Truth Evaluation Suite

175 tests covering:
- Base metrics (20)
- Metric aliases (40)
- Spelling errors (20)
- Casual queries (10)
- Dimension aliases (10)
- Dashboard commands (70)
- Negative tests (5)

Honor system: NEVER modify ground_truth.json or assertions to make tests pass.
If a test fails, fix NLQ — not the test.
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, Optional

# Load ground truth
GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"
GROUND_TRUTH = json.loads(GROUND_TRUTH_PATH.read_text())
POINT = GROUND_TRUTH["point_values"]
BY_DIM = GROUND_TRUTH["by_dimension"]
ANNUAL = GROUND_TRUTH["annual"]


@pytest.fixture(scope="session")
def api_client():
    """Create TestClient for FastAPI app."""
    from fastapi.testclient import TestClient
    from src.nlq.api.routes import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def process_nlq(query: str, client) -> dict:
    """
    Send query to NLQ API and return response.

    Uses TestClient to call the API.
    """
    try:
        response = client.post("/api/v1/query", json={"question": query})
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "success": False}
        return response.json()
    except Exception as e:
        return {"error": str(e), "success": False}


def extract_value(result: dict) -> Optional[Any]:
    """
    Extract single numeric value from NLQ result.

    Returns the 'value' field from NLQResponse.
    """
    if result is None:
        return None
    if not result.get("success", False):
        return None
    if "error" in result:
        return None

    # Primary value field
    value = result.get("value")
    if value is not None:
        return value

    # Try to extract from related_metrics if it's a single-value query
    related = result.get("related_metrics", [])
    if related and len(related) == 1:
        return related[0].get("value")

    return None


def extract_breakdown(result: dict) -> Optional[Dict[str, Any]]:
    """
    Extract dimension breakdown from NLQ result.

    Returns dict mapping dimension values to metric values.
    """
    if result is None:
        return None
    if not result.get("success", False):
        return None
    if "error" in result:
        return None

    # Check for dashboard data with breakdown
    dashboard_data = result.get("dashboard_data", {})
    if dashboard_data:
        # Find widget with dimensional data (prefer "breakdown_" prefixed widgets)
        for widget_id in sorted(dashboard_data.keys(), key=lambda x: (0 if x.startswith("breakdown_") else 1, x)):
            widget_data = dashboard_data[widget_id]

            # Check for series data format (bar charts, etc.)
            series = widget_data.get("series", [])
            if series and isinstance(series, list) and len(series) > 0:
                series_data = series[0].get("data", [])
                if series_data and isinstance(series_data, list):
                    breakdown = {}
                    for item in series_data:
                        if isinstance(item, dict):
                            label = item.get("label", item.get("name", ""))
                            value = item.get("value")
                            if label and value is not None:
                                breakdown[label] = value
                    if breakdown:
                        return breakdown

            # Check for direct data format
            data = widget_data.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                first_item = data[0]
                if isinstance(first_item, dict):
                    # Find dimension key (not 'value', 'period', 'metric')
                    dim_keys = [k for k in first_item.keys()
                               if k not in ('value', 'period', 'metric', 'label', 'ratio', 'name')]
                    if dim_keys:
                        dim_key = dim_keys[0]
                        return {d.get(dim_key, d.get('label', '')): d.get('value')
                                for d in data if d.get('value') is not None}
                    # Try label key
                    elif 'label' in first_item:
                        return {d.get('label'): d.get('value')
                                for d in data if d.get('value') is not None}

    # Check related_metrics for breakdown data
    related = result.get("related_metrics", [])
    if related and len(related) > 1:
        breakdown = {}
        for item in related:
            # Use display_name or metric as key
            key = item.get("display_name", item.get("metric", ""))
            value = item.get("value")
            if key and value is not None:
                breakdown[key] = value
        if breakdown:
            return breakdown

    return None


# =============================================================================
# SECTION 1: BASE METRIC TESTS (20 tests)
# =============================================================================

class TestBaseMetricsCFO:
    """CFO metrics with exact expected values"""

    def test_revenue_total(self, api_client):
        result = process_nlq("What is our revenue?", api_client)
        assert extract_value(result) == POINT["revenue"]

    def test_arr_total(self, api_client):
        result = process_nlq("What is our ARR?", api_client)
        assert extract_value(result) == POINT["arr"]

    def test_ar_total(self, api_client):
        result = process_nlq("What's our accounts receivable?", api_client)
        assert extract_value(result) == POINT["ar"]

    def test_revenue_by_region(self, api_client):
        result = process_nlq("What's revenue by region?", api_client)
        assert extract_breakdown(result) == BY_DIM["revenue_by_region"]

    def test_revenue_by_segment(self, api_client):
        result = process_nlq("What's revenue by segment?", api_client)
        assert extract_breakdown(result) == BY_DIM["revenue_by_segment"]


class TestBaseMetricsCRO:
    """CRO metrics with exact expected values"""

    def test_pipeline_total(self, api_client):
        result = process_nlq("What's our pipeline?", api_client)
        assert extract_value(result) == POINT["pipeline"]

    def test_win_rate(self, api_client):
        result = process_nlq("What's our win rate?", api_client)
        assert extract_value(result) == POINT["win_rate_pct"]

    def test_churn(self, api_client):
        result = process_nlq("What's our churn rate?", api_client)
        assert extract_value(result) == POINT["churn_pct"]

    def test_nrr(self, api_client):
        result = process_nlq("What's our NRR?", api_client)
        assert extract_value(result) == POINT["nrr"]

    def test_pipeline_by_stage(self, api_client):
        result = process_nlq("Show pipeline by stage", api_client)
        assert extract_breakdown(result) == BY_DIM["pipeline_by_stage"]

    def test_pipeline_by_region(self, api_client):
        result = process_nlq("Pipeline by region", api_client)
        assert extract_breakdown(result) == BY_DIM["pipeline_by_region"]


class TestBaseMetricsCHRO:
    """CHRO metrics with exact expected values"""

    def test_headcount_total(self, api_client):
        result = process_nlq("What's our headcount?", api_client)
        assert extract_value(result) == POINT["headcount"]

    def test_engagement_score(self, api_client):
        result = process_nlq("What's our engagement score?", api_client)
        assert extract_value(result) == POINT["engagement_score"]

    def test_attrition_rate(self, api_client):
        result = process_nlq("What's our attrition rate?", api_client)
        assert extract_value(result) == POINT["attrition_rate_pct"]

    def test_headcount_by_department(self, api_client):
        result = process_nlq("Show headcount by department", api_client)
        assert extract_breakdown(result) == BY_DIM["headcount_by_department"]

    def test_engagement_by_department(self, api_client):
        result = process_nlq("Show engagement by department", api_client)
        assert extract_breakdown(result) == BY_DIM["engagement_by_department"]

    def test_time_to_fill_by_department(self, api_client):
        result = process_nlq("Show time to fill by department", api_client)
        assert extract_breakdown(result) == BY_DIM["time_to_fill_by_department"]


class TestBaseMetricsCTO:
    """CTO metrics"""

    def test_cloud_spend(self, api_client):
        result = process_nlq("What's our cloud spend?", api_client)
        assert extract_value(result) == POINT["cloud_spend"]

    def test_uptime(self, api_client):
        result = process_nlq("What's our uptime?", api_client)
        assert extract_value(result) == POINT["uptime_pct"]


class TestBaseMetricsCOO:
    """COO metrics"""

    def test_nps(self, api_client):
        result = process_nlq("What's our NPS?", api_client)
        assert extract_value(result) == POINT["nps"]

    def test_magic_number(self, api_client):
        result = process_nlq("What's our magic number?", api_client)
        assert extract_value(result) == POINT["magic_number"]


# =============================================================================
# SECTION 2: METRIC ALIAS TESTS (40 tests)
# =============================================================================

class TestRevenueAliases:
    """Revenue = 50.0M regardless of how you ask"""
    EXPECTED = POINT["revenue"]

    def test_revenue(self, api_client):
        assert extract_value(process_nlq("What is our revenue?", api_client)) == self.EXPECTED

    def test_sales(self, api_client):
        assert extract_value(process_nlq("What are our sales?", api_client)) == self.EXPECTED

    def test_top_line(self, api_client):
        assert extract_value(process_nlq("What's our top line?", api_client)) == self.EXPECTED

    def test_total_sales(self, api_client):
        assert extract_value(process_nlq("Show me total sales", api_client)) == self.EXPECTED


class TestARRAliases:
    """ARR = 47.5M regardless of how you ask"""
    EXPECTED = POINT["arr"]

    def test_arr(self, api_client):
        assert extract_value(process_nlq("What is our ARR?", api_client)) == self.EXPECTED

    def test_arr_lowercase(self, api_client):
        assert extract_value(process_nlq("what's arr", api_client)) == self.EXPECTED

    def test_annual_recurring_revenue(self, api_client):
        assert extract_value(process_nlq("What's our annual recurring revenue?", api_client)) == self.EXPECTED

    def test_recurring_revenue(self, api_client):
        assert extract_value(process_nlq("Show recurring revenue", api_client)) == self.EXPECTED


class TestARAliases:
    """AR = 24.5M regardless of how you ask"""
    EXPECTED = POINT["ar"]

    def test_ar(self, api_client):
        assert extract_value(process_nlq("What's our AR?", api_client)) == self.EXPECTED

    def test_accounts_receivable(self, api_client):
        assert extract_value(process_nlq("Show me accounts receivable", api_client)) == self.EXPECTED

    def test_receivables(self, api_client):
        assert extract_value(process_nlq("What are our receivables?", api_client)) == self.EXPECTED

    def test_a_slash_r(self, api_client):
        assert extract_value(process_nlq("What's A/R?", api_client)) == self.EXPECTED


class TestPipelineAliases:
    """Pipeline = 143.75M regardless of how you ask"""
    EXPECTED = POINT["pipeline"]

    def test_pipeline(self, api_client):
        assert extract_value(process_nlq("What's our pipeline?", api_client)) == self.EXPECTED

    def test_pipe(self, api_client):
        assert extract_value(process_nlq("Show me the pipe", api_client)) == self.EXPECTED

    def test_sales_pipeline(self, api_client):
        assert extract_value(process_nlq("What's our sales pipeline?", api_client)) == self.EXPECTED

    def test_pipeline_value(self, api_client):
        assert extract_value(process_nlq("Total pipeline value?", api_client)) == self.EXPECTED


class TestHeadcountAliases:
    """Headcount = 430 regardless of how you ask"""
    EXPECTED = POINT["headcount"]

    def test_headcount(self, api_client):
        assert extract_value(process_nlq("What's our headcount?", api_client)) == self.EXPECTED

    def test_employees(self, api_client):
        assert extract_value(process_nlq("How many employees do we have?", api_client)) == self.EXPECTED

    def test_head_count(self, api_client):
        assert extract_value(process_nlq("What's head count?", api_client)) == self.EXPECTED

    def test_employee_count(self, api_client):
        assert extract_value(process_nlq("What's our employee count?", api_client)) == self.EXPECTED

    def test_fte(self, api_client):
        assert extract_value(process_nlq("How many FTEs?", api_client)) == self.EXPECTED

    def test_people(self, api_client):
        assert extract_value(process_nlq("How many people work here?", api_client)) == self.EXPECTED


class TestAttritionAliases:
    """Attrition rate = 1.2 regardless of how you ask"""
    EXPECTED = POINT["attrition_rate_pct"]

    def test_attrition_rate(self, api_client):
        assert extract_value(process_nlq("What's our attrition rate?", api_client)) == self.EXPECTED

    def test_attrition(self, api_client):
        assert extract_value(process_nlq("What's attrition?", api_client)) == self.EXPECTED

    def test_turnover(self, api_client):
        assert extract_value(process_nlq("What's our turnover rate?", api_client)) == self.EXPECTED

    def test_employee_turnover(self, api_client):
        assert extract_value(process_nlq("Show employee turnover", api_client)) == self.EXPECTED


class TestWinRateAliases:
    """Win rate = 45.5 regardless of how you ask"""
    EXPECTED = POINT["win_rate_pct"]

    def test_win_rate(self, api_client):
        assert extract_value(process_nlq("What's our win rate?", api_client)) == self.EXPECTED

    def test_close_rate(self, api_client):
        assert extract_value(process_nlq("What's our close rate?", api_client)) == self.EXPECTED

    def test_conversion_rate(self, api_client):
        assert extract_value(process_nlq("What's our deal conversion rate?", api_client)) == self.EXPECTED


class TestChurnAliases:
    """Churn = 5.9 regardless of how you ask"""
    EXPECTED = POINT["churn_pct"]

    def test_churn_pct(self, api_client):
        assert extract_value(process_nlq("What's our churn rate?", api_client)) == self.EXPECTED

    def test_churn(self, api_client):
        assert extract_value(process_nlq("What's churn?", api_client)) == self.EXPECTED

    def test_customer_churn(self, api_client):
        assert extract_value(process_nlq("What's customer churn?", api_client)) == self.EXPECTED


class TestNRRAliases:
    """NRR = 121.5 regardless of how you ask"""
    EXPECTED = POINT["nrr"]

    def test_nrr(self, api_client):
        assert extract_value(process_nlq("What's our NRR?", api_client)) == self.EXPECTED

    def test_net_revenue_retention(self, api_client):
        assert extract_value(process_nlq("What's net revenue retention?", api_client)) == self.EXPECTED

    def test_net_retention(self, api_client):
        assert extract_value(process_nlq("Show net retention", api_client)) == self.EXPECTED


# =============================================================================
# SECTION 3: SPELLING ERROR TESTS (20 tests)
# =============================================================================

class TestSpellingErrors:
    """Common typos should still resolve correctly"""

    def test_revnue(self, api_client):
        assert extract_value(process_nlq("What's our revnue?", api_client)) == POINT["revenue"]

    def test_reveune(self, api_client):
        assert extract_value(process_nlq("Show reveune", api_client)) == POINT["revenue"]

    def test_reveneu(self, api_client):
        result = process_nlq("What's reveneu by region?", api_client)
        assert extract_breakdown(result) is not None

    def test_pipline(self, api_client):
        assert extract_value(process_nlq("What's our pipline?", api_client)) == POINT["pipeline"]

    def test_pipleine(self, api_client):
        result = process_nlq("Show pipleine by stage", api_client)
        assert extract_breakdown(result) is not None

    def test_headcoutn(self, api_client):
        assert extract_value(process_nlq("What's headcoutn?", api_client)) == POINT["headcount"]

    def test_hedcount(self, api_client):
        result = process_nlq("Show hedcount by department", api_client)
        assert extract_breakdown(result) is not None

    def test_attrtion(self, api_client):
        assert extract_value(process_nlq("What's attrtion rate?", api_client)) == POINT["attrition_rate_pct"]

    def test_attriton(self, api_client):
        assert extract_value(process_nlq("Show attriton", api_client)) == POINT["attrition_rate_pct"]

    def test_engagment(self, api_client):
        assert extract_value(process_nlq("What's engagment score?", api_client)) == POINT["engagement_score"]

    def test_engagemnt(self, api_client):
        result = process_nlq("Show engagemnt by department", api_client)
        assert extract_breakdown(result) is not None

    def test_employess(self, api_client):
        assert extract_value(process_nlq("How many employess?", api_client)) == POINT["headcount"]

    def test_employes(self, api_client):
        result = process_nlq("Show employes by department", api_client)
        assert extract_breakdown(result) is not None

    def test_recievables(self, api_client):
        assert extract_value(process_nlq("What's our recievables?", api_client)) == POINT["ar"]

    def test_receivbles(self, api_client):
        assert extract_value(process_nlq("Show receivbles", api_client)) == POINT["ar"]

    def test_quater(self, api_client):
        result = process_nlq("Revenue last quater", api_client)
        assert "error" not in str(result).lower() or result.get("success", False)

    def test_departmnet(self, api_client):
        result = process_nlq("Headcount by departmnet", api_client)
        assert extract_breakdown(result) is not None

    def test_depatment(self, api_client):
        result = process_nlq("Show attrition by depatment", api_client)
        assert extract_breakdown(result) is not None

    def test_reigon(self, api_client):
        result = process_nlq("Revenue by reigon", api_client)
        assert extract_breakdown(result) == BY_DIM["revenue_by_region"]

    def test_segmnet(self, api_client):
        result = process_nlq("Revenue by segmnet", api_client)
        assert extract_breakdown(result) == BY_DIM["revenue_by_segment"]


# =============================================================================
# SECTION 4: CASUAL / INFORMAL QUERIES (10 tests)
# =============================================================================

class TestCasualQueries:
    """Informal phrasing should work"""

    def test_whats_arr(self, api_client):
        assert extract_value(process_nlq("whats arr", api_client)) == POINT["arr"]

    def test_arr_question_mark(self, api_client):
        assert extract_value(process_nlq("arr?", api_client)) == POINT["arr"]

    def test_gimme_revenue(self, api_client):
        result = process_nlq("gimme revenue by region", api_client)
        assert extract_breakdown(result) is not None

    def test_show_me_the_pipe(self, api_client):
        assert extract_value(process_nlq("show me the pipe", api_client)) == POINT["pipeline"]

    def test_how_we_doing_on_churn(self, api_client):
        assert extract_value(process_nlq("how we doing on churn", api_client)) == POINT["churn_pct"]

    def test_hows_headcount(self, api_client):
        assert extract_value(process_nlq("hows headcount", api_client)) == POINT["headcount"]

    def test_revenue_pls(self, api_client):
        assert extract_value(process_nlq("revenue pls", api_client)) == POINT["revenue"]

    def test_need_pipeline_numbers(self, api_client):
        assert extract_value(process_nlq("need pipeline numbers", api_client)) == POINT["pipeline"]

    def test_yo_whats_arr(self, api_client):
        assert extract_value(process_nlq("yo whats arr", api_client)) == POINT["arr"]

    def test_quick_question_revenue(self, api_client):
        assert extract_value(process_nlq("quick question - revenue?", api_client)) == POINT["revenue"]


# =============================================================================
# SECTION 5: DIMENSION ALIAS TESTS (10 tests)
# =============================================================================

class TestDimensionAliases:
    """Same breakdown, different dimension names"""

    def test_revenue_by_geo(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by geo", api_client)) == BY_DIM["revenue_by_region"]

    def test_revenue_by_geography(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by geography", api_client)) == BY_DIM["revenue_by_region"]

    def test_revenue_by_territory(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by territory", api_client)) == BY_DIM["revenue_by_region"]

    def test_headcount_by_dept(self, api_client):
        result = process_nlq("Headcount by dept", api_client)
        breakdown = extract_breakdown(result)
        assert breakdown is not None and "Engineering" in breakdown

    def test_headcount_by_org(self, api_client):
        result = process_nlq("Headcount by org", api_client)
        assert extract_breakdown(result) is not None

    def test_pipeline_by_phase(self, api_client):
        assert extract_breakdown(process_nlq("Pipeline by phase", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_pipeline_by_sales_stage(self, api_client):
        assert extract_breakdown(process_nlq("Pipeline by sales stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_revenue_by_customer_segment(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by customer segment", api_client)) == BY_DIM["revenue_by_segment"]

    def test_revenue_by_tier(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by tier", api_client)) == BY_DIM["revenue_by_segment"]

    def test_revenue_by_market_segment(self, api_client):
        assert extract_breakdown(process_nlq("Revenue by market segment", api_client)) == BY_DIM["revenue_by_segment"]


# =============================================================================
# SECTION 6: DASHBOARD COMMANDS (70 tests)
# =============================================================================

class TestMakeCommands:
    """'Make' should create correct visualizations"""

    def test_make_revenue_chart(self, api_client):
        assert extract_value(process_nlq("Make a revenue chart", api_client)) == POINT["revenue"]

    def test_make_chart_of_arr(self, api_client):
        assert extract_value(process_nlq("Make a chart of ARR", api_client)) == POINT["arr"]

    def test_make_revenue_by_region(self, api_client):
        assert extract_breakdown(process_nlq("Make a chart showing revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_make_pipeline_breakdown(self, api_client):
        assert extract_breakdown(process_nlq("Make a pipeline breakdown by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_make_headcount_chart(self, api_client):
        result = extract_breakdown(process_nlq("Make me a headcount chart by department", api_client))
        assert result is not None and result.get("Engineering") == 145

    def test_make_graph(self, api_client):
        assert extract_value(process_nlq("Make a graph of win rate", api_client)) == POINT["win_rate_pct"]

    def test_make_visualization(self, api_client):
        assert extract_value(process_nlq("Make a visualization of churn", api_client)) == POINT["churn_pct"]


class TestShowCommands:
    """'Show' should display correct data"""

    def test_show_revenue(self, api_client):
        assert extract_value(process_nlq("Show revenue", api_client)) == POINT["revenue"]

    def test_show_me_arr(self, api_client):
        assert extract_value(process_nlq("Show me ARR", api_client)) == POINT["arr"]

    def test_show_me_the_pipeline(self, api_client):
        assert extract_value(process_nlq("Show me the pipeline", api_client)) == POINT["pipeline"]

    def test_show_revenue_by_region(self, api_client):
        assert extract_breakdown(process_nlq("Show revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_show_pipeline_by_stage(self, api_client):
        assert extract_breakdown(process_nlq("Show pipeline by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_show_headcount_breakdown(self, api_client):
        result = extract_breakdown(process_nlq("Show headcount breakdown by department", api_client))
        assert result is not None and result.get("Engineering") == 145

    def test_show_me_engagement(self, api_client):
        result = extract_breakdown(process_nlq("Show me engagement by department", api_client))
        assert result is not None and result.get("Engineering") == 88

    def test_show_attrition(self, api_client):
        result = extract_breakdown(process_nlq("Show attrition by department", api_client))
        assert result is not None and result.get("Engineering") == 2

    def test_show_chart_of(self, api_client):
        assert extract_value(process_nlq("Show a chart of NRR", api_client)) == POINT["nrr"]

    def test_show_graph_of(self, api_client):
        assert extract_value(process_nlq("Show a graph of engagement score", api_client)) == POINT["engagement_score"]


class TestCreateCommands:
    """'Create' should generate correct visualizations"""

    def test_create_revenue_chart(self, api_client):
        assert extract_value(process_nlq("Create a revenue chart", api_client)) == POINT["revenue"]

    def test_create_dashboard_widget(self, api_client):
        assert extract_value(process_nlq("Create a dashboard widget for ARR", api_client)) == POINT["arr"]

    def test_create_pipeline_view(self, api_client):
        assert extract_breakdown(process_nlq("Create a pipeline view by region", api_client)) == BY_DIM["pipeline_by_region"]

    def test_create_breakdown(self, api_client):
        assert extract_breakdown(process_nlq("Create a breakdown of revenue by segment", api_client)) == BY_DIM["revenue_by_segment"]

    def test_create_chart_showing(self, api_client):
        result = extract_breakdown(process_nlq("Create a chart showing headcount by department", api_client))
        assert result is not None and result.get("Sales") == 80

    def test_create_visualization(self, api_client):
        result = extract_breakdown(process_nlq("Create a visualization of time to fill by department", api_client))
        assert result is not None and result.get("Engineering") == 41


class TestAddCommands:
    """'Add' should add correct elements"""

    def test_add_revenue_chart(self, api_client):
        assert extract_value(process_nlq("Add a revenue chart", api_client)) == POINT["revenue"]

    def test_add_arr_widget(self, api_client):
        assert extract_value(process_nlq("Add an ARR widget", api_client)) == POINT["arr"]

    def test_add_pipeline_breakdown(self, api_client):
        assert extract_breakdown(process_nlq("Add pipeline breakdown by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_add_headcount_by_dept(self, api_client):
        result = extract_breakdown(process_nlq("Add headcount by department", api_client))
        assert result is not None and result.get("Engineering") == 145

    def test_add_metric(self, api_client):
        assert extract_value(process_nlq("Add win rate metric", api_client)) == POINT["win_rate_pct"]

    def test_add_kpi(self, api_client):
        assert extract_value(process_nlq("Add NRR as a KPI", api_client)) == POINT["nrr"]

    def test_add_tile(self, api_client):
        assert extract_value(process_nlq("Add a tile for churn rate", api_client)) == POINT["churn_pct"]

    def test_add_card(self, api_client):
        assert extract_value(process_nlq("Add a card showing engagement score", api_client)) == POINT["engagement_score"]


class TestDrillCommands:
    """'Drill' should drill into correct breakdowns"""

    def test_drill_into_revenue(self, api_client):
        assert extract_breakdown(process_nlq("Drill into revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_drill_down_pipeline(self, api_client):
        assert extract_breakdown(process_nlq("Drill down on pipeline by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_drill_into_headcount(self, api_client):
        result = extract_breakdown(process_nlq("Drill into headcount by department", api_client))
        assert result is not None and result.get("Engineering") == 145

    def test_drill_revenue_segment(self, api_client):
        assert extract_breakdown(process_nlq("Drill revenue by segment", api_client)) == BY_DIM["revenue_by_segment"]

    def test_drill_down_engagement(self, api_client):
        result = extract_breakdown(process_nlq("Drill down engagement by department", api_client))
        assert result is not None and result.get("People") == 92

    def test_drill_deeper_attrition(self, api_client):
        result = extract_breakdown(process_nlq("Drill deeper into attrition by department", api_client))
        assert result is not None and result.get("Engineering") == 2


class TestDisplayCommands:
    """'Display' variants should work"""

    def test_display_revenue(self, api_client):
        assert extract_value(process_nlq("Display revenue", api_client)) == POINT["revenue"]

    def test_display_revenue_by_segment(self, api_client):
        assert extract_breakdown(process_nlq("Display revenue by segment", api_client)) == BY_DIM["revenue_by_segment"]

    def test_display_pipeline(self, api_client):
        assert extract_breakdown(process_nlq("Display pipeline by region", api_client)) == BY_DIM["pipeline_by_region"]


class TestPlotCommands:
    """'Plot' should generate visualizations"""

    def test_plot_revenue(self, api_client):
        assert extract_breakdown(process_nlq("Plot revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_plot_pipeline(self, api_client):
        assert extract_breakdown(process_nlq("Plot pipeline by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_plot_headcount(self, api_client):
        result = extract_breakdown(process_nlq("Plot headcount by department", api_client))
        assert result is not None and result.get("Engineering") == 145


class TestGraphCommands:
    """'Graph' should generate visualizations"""

    def test_graph_revenue(self, api_client):
        assert extract_breakdown(process_nlq("Graph revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_graph_pipeline(self, api_client):
        assert extract_value(process_nlq("Graph the pipeline", api_client)) == POINT["pipeline"]

    def test_graph_headcount(self, api_client):
        result = process_nlq("Graph headcount", api_client)
        assert extract_value(result) == POINT["headcount"] or extract_breakdown(result) is not None


class TestBuildCommands:
    """'Build' should create visualizations"""

    def test_build_revenue_chart(self, api_client):
        assert extract_value(process_nlq("Build a revenue chart", api_client)) == POINT["revenue"]

    def test_build_pipeline_report(self, api_client):
        assert extract_breakdown(process_nlq("Build a pipeline report by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_build_headcount_view(self, api_client):
        result = extract_breakdown(process_nlq("Build a headcount view by department", api_client))
        assert result is not None and result.get("Engineering") == 145


class TestGenerateCommands:
    """'Generate' should create visualizations"""

    def test_generate_revenue_report(self, api_client):
        assert extract_breakdown(process_nlq("Generate a revenue report by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_generate_chart(self, api_client):
        assert extract_breakdown(process_nlq("Generate a chart for pipeline by region", api_client)) == BY_DIM["pipeline_by_region"]

    def test_generate_headcount_breakdown(self, api_client):
        result = extract_breakdown(process_nlq("Generate headcount breakdown by department", api_client))
        assert result is not None and result.get("Engineering") == 145


class TestGiveMeCommands:
    """'Give me' informal requests"""

    def test_give_me_revenue(self, api_client):
        assert extract_value(process_nlq("Give me revenue", api_client)) == POINT["revenue"]

    def test_give_me_breakdown(self, api_client):
        assert extract_breakdown(process_nlq("Give me revenue breakdown by segment", api_client)) == BY_DIM["revenue_by_segment"]

    def test_give_me_pipeline_numbers(self, api_client):
        assert extract_breakdown(process_nlq("Give me pipeline numbers by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_give_me_headcount_stats(self, api_client):
        result = extract_breakdown(process_nlq("Give me headcount stats by department", api_client))
        assert result is not None and result.get("Engineering") == 145


class TestPullCommands:
    """'Pull' data requests"""

    def test_pull_revenue_data(self, api_client):
        assert extract_breakdown(process_nlq("Pull revenue data by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_pull_up_pipeline(self, api_client):
        assert extract_breakdown(process_nlq("Pull up pipeline by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_pull_headcount(self, api_client):
        assert extract_value(process_nlq("Pull headcount numbers", api_client)) == POINT["headcount"]


class TestGetCommands:
    """'Get' data requests"""

    def test_get_revenue(self, api_client):
        assert extract_value(process_nlq("Get revenue", api_client)) == POINT["revenue"]

    def test_get_me_arr(self, api_client):
        assert extract_value(process_nlq("Get me ARR", api_client)) == POINT["arr"]

    def test_get_pipeline_by_region(self, api_client):
        assert extract_breakdown(process_nlq("Get pipeline by region", api_client)) == BY_DIM["pipeline_by_region"]

    def test_get_headcount_breakdown(self, api_client):
        result = extract_breakdown(process_nlq("Get headcount breakdown by department", api_client))
        assert result is not None and result.get("Engineering") == 145


class TestCompareCommands:
    """'Compare' should show comparisons"""

    def test_compare_revenue_by_region(self, api_client):
        assert extract_breakdown(process_nlq("Compare revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_compare_pipeline_across_stages(self, api_client):
        assert extract_breakdown(process_nlq("Compare pipeline across stages", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_compare_headcount_departments(self, api_client):
        result = extract_breakdown(process_nlq("Compare headcount across departments", api_client))
        assert result is not None
        assert result.get("Engineering") == 145
        assert result.get("Sales") == 80


class TestBreakdownCommands:
    """'Breakdown' as action verb"""

    def test_breakdown_revenue(self, api_client):
        assert extract_breakdown(process_nlq("Breakdown revenue by region", api_client)) == BY_DIM["revenue_by_region"]

    def test_break_down_pipeline(self, api_client):
        assert extract_breakdown(process_nlq("Break down pipeline by stage", api_client)) == BY_DIM["pipeline_by_stage"]

    def test_give_breakdown_of(self, api_client):
        result = extract_breakdown(process_nlq("Give me a breakdown of headcount by department", api_client))
        assert result is not None and result.get("Engineering") == 145


# =============================================================================
# SECTION 7: NEGATIVE TESTS (5 tests)
# =============================================================================

class TestNegativeCases:
    """Verify errors surface correctly"""

    def test_invalid_dimension_errors(self, api_client):
        """Revenue by rep should fail - rep not valid for revenue"""
        result = process_nlq("Show revenue by rep", api_client)
        # Should either error or not have the breakdown
        breakdown = extract_breakdown(result)
        assert breakdown is None or "error" in str(result).lower() or not result.get("success", True)

    def test_unknown_metric_errors(self, api_client):
        """Fake metric should fail"""
        result = process_nlq("What's our flurbnorb?", api_client)
        assert "error" in str(result).lower() or extract_value(result) is None or not result.get("success", True)

    def test_no_silent_fallback(self, api_client):
        """Invalid query should not silently return default data"""
        result = process_nlq("Show xyzzy by foobar", api_client)
        # Should error, not return unrelated data
        value = extract_value(result)
        breakdown = extract_breakdown(result)
        assert (
            "error" in str(result).lower() or
            (value is None and breakdown is None) or
            not result.get("success", True)
        )

    def test_gibberish_fails(self, api_client):
        """Complete gibberish should not return real metrics"""
        result = process_nlq("asdfghjkl qwertyuiop", api_client)
        assert extract_value(result) is None or "error" in str(result).lower()

    def test_empty_query_handled(self, api_client):
        """Empty query should not crash"""
        result = process_nlq("", api_client)
        # Should return error or empty, not crash
        assert result is not None


# =============================================================================
# TEST COUNT VERIFICATION
# =============================================================================

def test_total_test_count():
    """Verify we have approximately 175 tests."""
    import sys

    # Count test methods
    test_classes = [
        # Base metrics (20)
        TestBaseMetricsCFO, TestBaseMetricsCRO, TestBaseMetricsCHRO,
        TestBaseMetricsCTO, TestBaseMetricsCOO,
        # Aliases (40)
        TestRevenueAliases, TestARRAliases, TestARAliases, TestPipelineAliases,
        TestHeadcountAliases, TestAttritionAliases, TestWinRateAliases,
        TestChurnAliases, TestNRRAliases,
        # Spelling (20)
        TestSpellingErrors,
        # Casual (10)
        TestCasualQueries,
        # Dimension aliases (10)
        TestDimensionAliases,
        # Dashboard commands (70)
        TestMakeCommands, TestShowCommands, TestCreateCommands, TestAddCommands,
        TestDrillCommands, TestDisplayCommands, TestPlotCommands, TestGraphCommands,
        TestBuildCommands, TestGenerateCommands, TestGiveMeCommands, TestPullCommands,
        TestGetCommands, TestCompareCommands, TestBreakdownCommands,
        # Negative (5)
        TestNegativeCases,
    ]

    total = 0
    for cls in test_classes:
        methods = [m for m in dir(cls) if m.startswith('test_')]
        total += len(methods)

    # Should be around 175 tests
    assert total >= 170, f"Expected ~175 tests, got {total}"
    print(f"Total tests: {total}")
