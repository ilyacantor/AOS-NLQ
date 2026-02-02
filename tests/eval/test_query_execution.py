"""
Query Execution Tests - Verify all personas can query their metrics with data returned.

These tests verify that when we execute queries through DCL,
we get actual data back - not empty results, not errors.

For each persona (CFO, CRO, COO, CTO, CHRO), we test their core metrics.

NO MOCKING - tests hit real DCL or fail.
"""

import pytest
from tests.eval.conftest import collect_failures


# =============================================================================
# QUERY EXECUTION TEST CASES
# =============================================================================
# Format: (metric, dimensions, min_expected_records, persona)
# These define what queries MUST return data for each persona.

QUERY_EXECUTION_CASES = [
    # === CFO / Finance Metrics ===
    ("revenue", [], 1, "CFO"),
    ("revenue", ["segment"], 1, "CFO"),
    ("revenue", ["region"], 1, "CFO"),
    ("arr", [], 1, "CFO"),
    ("arr", ["segment"], 1, "CFO"),
    ("gross_margin_pct", [], 1, "CFO"),
    ("net_income", [], 1, "CFO"),
    ("cash", [], 1, "CFO"),

    # === CRO / Sales Metrics ===
    ("pipeline", [], 1, "CRO"),
    ("pipeline", ["rep"], 1, "CRO"),
    ("pipeline", ["stage"], 1, "CRO"),
    ("win_rate", [], 1, "CRO"),
    ("win_rate", ["rep"], 1, "CRO"),
    ("gross_churn_pct", [], 1, "CRO"),
    ("nrr", [], 1, "CRO"),
    ("sales_cycle_days", [], 1, "CRO"),
    ("quota_attainment", [], 1, "CRO"),

    # === COO / Operations Metrics ===
    ("headcount", [], 1, "COO"),
    ("headcount", ["department"], 1, "COO"),
    ("revenue_per_employee", [], 1, "COO"),
    ("magic_number", [], 1, "COO"),
    ("cac_payback_months", [], 1, "COO"),
    ("ltv_cac", [], 1, "COO"),
    ("attrition_rate", [], 1, "COO"),

    # === CTO / Engineering Metrics ===
    ("uptime_pct", [], 1, "CTO"),
    ("deploys_per_week", [], 1, "CTO"),
    ("mttr_p1_hours", [], 1, "CTO"),
    ("sprint_velocity", [], 1, "CTO"),
    ("tech_debt_pct", [], 1, "CTO"),
    ("code_coverage_pct", [], 1, "CTO"),
    ("features_shipped", [], 1, "CTO"),

    # === CHRO / People Metrics ===
    ("headcount", ["department"], 1, "CHRO"),
    ("attrition_rate", ["department"], 1, "CHRO"),
    ("enps", [], 1, "CHRO"),
    ("enps", ["department"], 1, "CHRO"),
    ("engagement_score", [], 1, "CHRO"),
    ("time_to_hire_days", [], 1, "CHRO"),
    ("offer_acceptance_rate", [], 1, "CHRO"),
    ("diversity_pct", [], 1, "CHRO"),
]


class TestQueryExecution:
    """Test that all core queries return actual data."""

    def test_all_queries_return_data(self, dcl_client, failure_collector):
        """
        CRITICAL: Every query must return actual data.

        This test executes ALL core queries and verifies:
        1. Response contains "data" key
        2. Data has at least min_expected_records
        3. No "error" in response

        If ANY query fails to return data, the test fails.
        """
        failures = []

        for metric, dimensions, min_records, persona in QUERY_EXECUTION_CASES:
            result = dcl_client.query(
                metric=metric,
                dimensions=dimensions,
                time_range={"period": "2025", "granularity": "annual"}
            )

            query_desc = f"{metric}" + (f" by {dimensions}" if dimensions else "")

            # Check for errors
            if "error" in result:
                failures.append(
                    f"[{persona}] {query_desc}: got error: {result['error']}"
                )
                continue

            # Check data exists
            if "data" not in result:
                failures.append(
                    f"[{persona}] {query_desc}: no 'data' in response"
                )
                continue

            # Check we got enough records
            data = result["data"]
            if not isinstance(data, list):
                # Handle scalar or single-value responses
                if data is None:
                    failures.append(
                        f"[{persona}] {query_desc}: data is None"
                    )
            elif len(data) < min_records:
                failures.append(
                    f"[{persona}] {query_desc}: expected >= {min_records} records, got {len(data)}"
                )

        error_msg = failure_collector(failures)
        assert not failures, error_msg

    def test_response_has_required_structure(self, dcl_client):
        """Query responses must have expected structure."""
        result = dcl_client.query(
            metric="revenue",
            time_range={"period": "2025"}
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result, "Response must have 'data' key"

        # Data should be a list or scalar
        data = result["data"]
        assert data is not None, "Data should not be None"

    def test_dimensional_query_returns_breakdown(self, dcl_client):
        """Queries with dimensions should return dimensional breakdown."""
        result = dcl_client.query(
            metric="revenue",
            dimensions=["segment"],
            time_range={"period": "2025"}
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result, "Response must have 'data' key"

        data = result["data"]
        # Dimensional query should return list of records with dimension values
        if isinstance(data, list) and len(data) > 0:
            # Check that records have the dimension
            first_record = data[0]
            if isinstance(first_record, dict):
                # Either the dimension name or a value field should be present
                assert "segment" in first_record or "value" in first_record, \
                    f"Record should have dimension or value: {first_record}"


class TestQueryByPersona:
    """Test queries grouped by persona."""

    def test_cfo_queries(self, dcl_client, failure_collector):
        """All CFO queries must return data."""
        cfo_cases = [c for c in QUERY_EXECUTION_CASES if c[3] == "CFO"]
        self._run_persona_tests(dcl_client, cfo_cases, "CFO", failure_collector)

    def test_cro_queries(self, dcl_client, failure_collector):
        """All CRO queries must return data."""
        cro_cases = [c for c in QUERY_EXECUTION_CASES if c[3] == "CRO"]
        self._run_persona_tests(dcl_client, cro_cases, "CRO", failure_collector)

    def test_coo_queries(self, dcl_client, failure_collector):
        """All COO queries must return data."""
        coo_cases = [c for c in QUERY_EXECUTION_CASES if c[3] == "COO"]
        self._run_persona_tests(dcl_client, coo_cases, "COO", failure_collector)

    def test_cto_queries(self, dcl_client, failure_collector):
        """All CTO queries must return data."""
        cto_cases = [c for c in QUERY_EXECUTION_CASES if c[3] == "CTO"]
        self._run_persona_tests(dcl_client, cto_cases, "CTO", failure_collector)

    def test_chro_queries(self, dcl_client, failure_collector):
        """All CHRO queries must return data."""
        chro_cases = [c for c in QUERY_EXECUTION_CASES if c[3] == "CHRO"]
        self._run_persona_tests(dcl_client, chro_cases, "CHRO", failure_collector)

    def _run_persona_tests(self, dcl_client, cases, persona, failure_collector):
        """Run all tests for a persona."""
        failures = []

        for metric, dimensions, min_records, _ in cases:
            result = dcl_client.query(
                metric=metric,
                dimensions=dimensions,
                time_range={"period": "2025", "granularity": "annual"}
            )

            query_desc = f"{metric}" + (f" by {dimensions}" if dimensions else "")

            if "error" in result:
                failures.append(f"{query_desc}: {result['error']}")
            elif "data" not in result:
                failures.append(f"{query_desc}: no data")
            elif result["data"] is None:
                failures.append(f"{query_desc}: data is None")

        error_msg = failure_collector(failures)
        assert not failures, f"{persona} query failures:{error_msg}"


class TestQueryCoverage:
    """Verify query test coverage."""

    def test_all_personas_have_tests(self):
        """All 5 personas must have query tests."""
        personas_tested = set(p for _, _, _, p in QUERY_EXECUTION_CASES)
        expected_personas = {"CFO", "CRO", "COO", "CTO", "CHRO"}

        missing = expected_personas - personas_tested
        assert not missing, f"Missing query tests for personas: {missing}"

    def test_each_persona_has_minimum_coverage(self):
        """Each persona must have at least 3 query tests."""
        persona_counts = {}
        for _, _, _, persona in QUERY_EXECUTION_CASES:
            persona_counts[persona] = persona_counts.get(persona, 0) + 1

        for persona, count in persona_counts.items():
            assert count >= 3, \
                f"Persona {persona} has only {count} tests, need at least 3"

    def test_dimensional_queries_exist(self):
        """Must have tests for queries with dimensions."""
        dimensional_tests = [
            c for c in QUERY_EXECUTION_CASES
            if c[1]  # dimensions list is not empty
        ]

        assert len(dimensional_tests) >= 5, \
            f"Need at least 5 dimensional query tests, have {len(dimensional_tests)}"
