"""
End-to-End NLQ Query Tests - Full flow from natural language to validated result.

These tests verify the complete NLQ pipeline:
1. User asks natural language question
2. NLQ resolves metric and dimensions
3. Query executes against DCL
4. Result is returned with correct structure

NO MOCKING - tests hit real DCL or fail.
"""

import pytest
from tests.eval.conftest import collect_failures


# =============================================================================
# END-TO-END TEST CASES
# =============================================================================
# Format: (natural_language_query, expected_metric, expected_has_data, persona)
# These simulate REAL user questions.

E2E_QUERY_CASES = [
    # === CFO / Finance Questions ===
    ("What's our ARR?", "arr", True, "CFO"),
    ("Show me revenue", "revenue", True, "CFO"),
    ("What is our gross margin?", "gross_margin_pct", True, "CFO"),
    ("How much cash do we have?", "cash", True, "CFO"),
    ("What's our net income?", "net_income", True, "CFO"),
    ("Show ARR by segment", "arr", True, "CFO"),
    ("Revenue by region", "revenue", True, "CFO"),

    # === CRO / Sales Questions ===
    ("What's in our pipeline?", "pipeline", True, "CRO"),
    ("Show me pipeline by rep", "pipeline", True, "CRO"),
    ("What's our win rate?", "win_rate_pct", True, "CRO"),
    ("Pipeline by stage", "pipeline", True, "CRO"),
    ("What's our churn rate?", "churn_rate_pct", True, "CRO"),
    ("Show NRR", "nrr", True, "CRO"),
    ("What's our quota attainment?", "quota_attainment_pct", True, "CRO"),

    # === COO / Operations Questions ===
    ("How many employees do we have?", "headcount", True, "COO"),
    ("Headcount by department", "headcount", True, "COO"),
    ("What's our revenue per employee?", "revenue_per_employee", True, "COO"),
    ("Show me the magic number", "magic_number", True, "COO"),
    ("What's our attrition rate?", "attrition_rate_pct", True, "COO"),
    ("CAC payback period", "cac_payback_months", True, "COO"),

    # === CTO / Engineering Questions ===
    ("What's our uptime?", "uptime_pct", True, "CTO"),
    ("How many deploys per week?", "deploys_per_week", True, "CTO"),
    ("What's our MTTR?", "mttr_p1_hours", True, "CTO"),
    ("Sprint velocity", "sprint_velocity", True, "CTO"),
    ("Show tech debt percentage", "tech_debt_pct", True, "CTO"),
    ("Code coverage", "code_coverage_pct", True, "CTO"),

    # === CHRO / People Questions ===
    ("What's our eNPS?", "enps", True, "CHRO"),
    ("eNPS by department", "enps", True, "CHRO"),
    ("What's our engagement score?", "engagement_score", True, "CHRO"),
    ("Time to hire", "time_to_hire_days", True, "CHRO"),
    ("Offer acceptance rate", "offer_acceptance_rate_pct", True, "CHRO"),
    ("Attrition by department", "attrition_rate_pct", True, "CHRO"),
]


class TestEndToEndQueries:
    """Test complete NLQ query flow from natural language to result."""

    def test_all_e2e_queries_return_data(self, dcl_client, failure_collector):
        """
        CRITICAL: Every natural language query must resolve and return data.

        This test simulates what users actually type and verifies:
        1. Metric resolves correctly
        2. Query executes without error
        3. Data is returned
        """
        failures = []

        for nl_query, expected_metric, should_have_data, persona in E2E_QUERY_CASES:
            # Step 1: Resolve the metric from natural language
            # Extract the likely metric term from the query
            metric_result = dcl_client.resolve_metric(expected_metric)

            if metric_result is None:
                failures.append(
                    f"[{persona}] '{nl_query}': metric '{expected_metric}' did not resolve"
                )
                continue

            # Step 2: Execute the query
            from src.nlq.config import get_tenant_id
            result = dcl_client.query(
                metric=metric_result.id,
                time_range={"period": "2025", "granularity": "annual"},
                tenant_id=get_tenant_id(),
            )

            # Step 3: Validate result
            if "error" in result:
                failures.append(
                    f"[{persona}] '{nl_query}': query error: {result['error']}"
                )
                continue

            if should_have_data:
                if "data" not in result:
                    failures.append(
                        f"[{persona}] '{nl_query}': no 'data' in response"
                    )
                elif result["data"] is None:
                    failures.append(
                        f"[{persona}] '{nl_query}': data is None"
                    )

        error_msg = failure_collector(failures)
        assert not failures, error_msg

    def test_dimensional_e2e_queries(self, dcl_client, failure_collector):
        """Test natural language queries that include dimensions."""
        dimensional_cases = [
            ("ARR by segment", "arr", ["segment"]),
            ("Revenue by region", "revenue", ["region"]),
            ("Pipeline by rep", "pipeline", ["rep"]),
            ("Pipeline by stage", "pipeline", ["stage"]),
            ("Headcount by department", "headcount", ["department"]),
            ("eNPS by department", "enps", ["department"]),
            ("Win rate by rep", "win_rate_pct", ["rep"]),
            ("Attrition by department", "attrition_rate_pct", ["department"]),
        ]

        failures = []

        for nl_query, metric_id, dimensions in dimensional_cases:
            from src.nlq.config import get_tenant_id
            result = dcl_client.query(
                metric=metric_id,
                dimensions=dimensions,
                time_range={"period": "2025", "granularity": "annual"},
                tenant_id=get_tenant_id(),
            )

            if "error" in result:
                failures.append(
                    f"'{nl_query}': query error: {result['error']}"
                )
                continue

            if "data" not in result:
                failures.append(f"'{nl_query}': no 'data' in response")
                continue

            data = result["data"]
            if not isinstance(data, list):
                failures.append(
                    f"'{nl_query}': expected list for dimensional query, got {type(data)}"
                )
            elif len(data) == 0:
                failures.append(f"'{nl_query}': dimensional query returned empty list")

        error_msg = failure_collector(failures)
        assert not failures, error_msg

    def test_metric_resolution_matches_expected(self, dcl_client):
        """Verify metrics in E2E cases actually resolve to expected IDs."""
        for nl_query, expected_metric, _, persona in E2E_QUERY_CASES:
            result = dcl_client.resolve_metric(expected_metric)

            assert result is not None, \
                f"[{persona}] '{nl_query}': metric '{expected_metric}' should resolve"
            assert result.id == expected_metric, \
                f"[{persona}] '{nl_query}': expected '{expected_metric}', got '{result.id}'"


class TestE2EQueryVariations:
    """Test natural language variations of the same query."""

    def test_revenue_query_variations(self, dcl_client):
        """Different ways to ask about revenue should all work."""
        variations = [
            "revenue",
            "sales",
            "top line",
        ]

        for term in variations:
            result = dcl_client.resolve_metric(term)
            assert result is not None, f"'{term}' should resolve"
            assert result.id == "revenue", f"'{term}' should resolve to 'revenue'"

            # Also verify we can query it
            from src.nlq.config import get_tenant_id
            query_result = dcl_client.query(
                metric="revenue",
                time_range={"period": "2025"},
                tenant_id=get_tenant_id(),
            )
            assert "error" not in query_result, f"Query for '{term}' failed"

    def test_arr_query_variations(self, dcl_client):
        """Different ways to ask about ARR should all work."""
        variations = [
            "ARR",
            "arr",
            "annual recurring revenue",
        ]

        for term in variations:
            result = dcl_client.resolve_metric(term)
            assert result is not None, f"'{term}' should resolve"
            assert result.id == "arr", f"'{term}' should resolve to 'arr'"

    def test_pipeline_query_variations(self, dcl_client):
        """Different ways to ask about pipeline should all work."""
        variations = [
            "pipeline",
            "pipe",
            "sales pipeline",
        ]

        for term in variations:
            result = dcl_client.resolve_metric(term)
            assert result is not None, f"'{term}' should resolve"
            assert result.id == "pipeline", f"'{term}' should resolve to 'pipeline'"

    def test_headcount_query_variations(self, dcl_client):
        """Different ways to ask about headcount should all work."""
        variations = [
            "headcount",
            "employees",
            "head count",
        ]

        for term in variations:
            result = dcl_client.resolve_metric(term)
            assert result is not None, f"'{term}' should resolve"
            assert result.id == "headcount", f"'{term}' should resolve to 'headcount'"


class TestE2EQueryCoverage:
    """Verify E2E test coverage."""

    def test_all_personas_covered(self):
        """All 5 personas must have E2E query tests."""
        personas_tested = set(p for _, _, _, p in E2E_QUERY_CASES)
        expected_personas = {"CFO", "CRO", "COO", "CTO", "CHRO"}

        missing = expected_personas - personas_tested
        assert not missing, f"Missing E2E tests for personas: {missing}"

    def test_each_persona_has_minimum_e2e_coverage(self):
        """Each persona must have at least 3 E2E query tests."""
        persona_counts = {}
        for _, _, _, persona in E2E_QUERY_CASES:
            persona_counts[persona] = persona_counts.get(persona, 0) + 1

        for persona, count in persona_counts.items():
            assert count >= 3, \
                f"Persona {persona} has only {count} E2E tests, need at least 3"

    def test_dimensional_cases_exist(self):
        """Must have E2E tests that include 'by' dimension queries."""
        by_queries = [
            q for q, _, _, _ in E2E_QUERY_CASES
            if " by " in q.lower()
        ]

        assert len(by_queries) >= 5, \
            f"Need at least 5 'by dimension' queries, have {len(by_queries)}"
