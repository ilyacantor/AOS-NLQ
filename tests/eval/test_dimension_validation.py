"""
Dimension Validation Tests - Verify correct dimensions pass, invalid ones fail helpfully.

Each metric only supports certain dimensions (e.g., ARR supports segment but not rep).
These tests verify:
1. Valid metric+dimension combinations pass
2. Invalid combinations fail with HELPFUL errors listing valid alternatives
3. No silent fallbacks - invalid dimensions must error, not return default view

NO MOCKING - tests hit real DCL or fail.
"""

import pytest
from tests.eval.conftest import collect_failures


# =============================================================================
# DIMENSION VALIDATION TEST CASES
# =============================================================================
# Format: (metric_id, dimension, should_pass, description)
# These define the CONTRACT between NLQ and DCL.

DIMENSION_VALIDATION_CASES = [
    # === CFO / Finance Metrics ===
    ("revenue", "segment", True, "revenue by segment should work"),
    ("revenue", "region", True, "revenue by region should work"),
    ("revenue", "customer", True, "revenue by customer should work"),
    ("revenue", "rep", False, "revenue does not support rep dimension"),
    ("revenue", "department", False, "revenue does not support department dimension"),

    ("arr", "segment", True, "ARR by segment should work"),
    ("arr", "customer", True, "ARR by customer should work"),
    ("arr", "rep", False, "ARR does not support rep dimension"),

    ("gross_margin_pct", "segment", True, "margin by segment should work"),
    ("gross_margin_pct", "rep", False, "margin does not support rep dimension"),

    # === CRO / Sales Metrics ===
    ("pipeline", "rep", True, "pipeline by rep should work"),
    ("pipeline", "stage", True, "pipeline by stage should work"),
    ("pipeline", "segment", True, "pipeline by segment should work"),
    ("pipeline", "department", False, "pipeline does not support department dimension"),

    ("win_rate_pct", "rep", True, "win_rate by rep should work"),
    ("win_rate_pct", "region", True, "win_rate by region should work"),
    ("win_rate_pct", "department", False, "win_rate does not support department dimension"),

    ("sales_cycle_days", "segment", True, "sales cycle by segment should work"),
    ("sales_cycle_days", "rep", True, "sales cycle by rep should work"),

    # === COO / Operations Metrics ===
    ("headcount", "department", True, "headcount by department should work"),
    ("headcount", "team", True, "headcount by team should work"),
    ("headcount", "rep", False, "headcount does not support rep dimension"),
    ("headcount", "stage", False, "headcount does not support stage dimension"),

    ("attrition_rate_pct", "department", True, "attrition by department should work"),
    ("attrition_rate_pct", "team", True, "attrition by team should work"),
    ("attrition_rate_pct", "rep", False, "attrition does not support rep dimension"),

    # === CTO / Engineering Metrics ===
    ("uptime_pct", "service", True, "uptime by service should work"),
    ("uptime_pct", "rep", False, "uptime does not support rep dimension"),

    ("deploys_per_week", "team", True, "deploys by team should work"),
    ("deploys_per_week", "service", True, "deploys by service should work"),
    ("deploys_per_week", "customer", False, "deploys does not support customer dimension"),

    ("sprint_velocity", "team", True, "velocity by team should work"),
    ("sprint_velocity", "rep", False, "velocity does not support rep dimension"),

    # === CHRO / People Metrics ===
    ("enps", "department", True, "eNPS by department should work"),
    ("enps", "team", True, "eNPS by team should work"),
    ("enps", "rep", False, "eNPS does not support rep dimension"),
    ("enps", "stage", False, "eNPS does not support stage dimension"),

    ("engagement_score", "department", True, "engagement by department should work"),
    ("engagement_score", "customer", False, "engagement does not support customer dimension"),

    ("time_to_hire_days", "department", True, "time to hire by department should work"),
    ("time_to_hire_days", "rep", False, "time to hire does not support rep dimension"),
]


class TestDimensionValidation:
    """Test that dimension validation works correctly for all metric+dimension combos."""

    def test_all_dimension_validations(self, dcl_client, failure_collector):
        """
        CRITICAL: Validate all metric+dimension combinations.

        Valid combinations must pass.
        Invalid combinations must fail WITH HELPFUL ERROR listing alternatives.
        """
        failures = []

        for metric, dimension, should_pass, description in DIMENSION_VALIDATION_CASES:
            valid, error = dcl_client.validate_dimension(metric, dimension)

            if should_pass and not valid:
                failures.append(
                    f"{metric}+{dimension}: SHOULD PASS but got error: {error}"
                    f"\n    ({description})"
                )
            elif not should_pass and valid:
                failures.append(
                    f"{metric}+{dimension}: SHOULD FAIL but passed"
                    f"\n    ({description})"
                )
            elif not should_pass and valid is False:
                # Check that error message includes valid alternatives
                if "Valid dimensions:" not in str(error) and "does not support" not in str(error):
                    failures.append(
                        f"{metric}+{dimension}: error missing helpful alternatives: {error}"
                    )

        error_msg = failure_collector(failures)
        assert not failures, error_msg

    def test_invalid_dimension_lists_alternatives(self, dcl_client):
        """When dimension is invalid, error must list valid alternatives."""
        # These metrics definitely have valid dimensions, so error should list them
        test_cases = [
            ("revenue", "fake_dimension"),
            ("pipeline", "xyz"),
            ("headcount", "blah"),
        ]

        for metric, invalid_dim in test_cases:
            valid, error = dcl_client.validate_dimension(metric, invalid_dim)

            assert not valid, f"{metric}+{invalid_dim} should be invalid"
            assert error is not None, f"Error message should be provided"
            assert "Valid dimensions:" in error or "does not support" in error, \
                f"Error should list alternatives or explain unsupported: {error}"

    def test_case_insensitive_dimension_matching(self, dcl_client):
        """Dimension validation should be case-insensitive."""
        cases = [
            ("revenue", "SEGMENT", True),
            ("revenue", "Segment", True),
            ("revenue", "segment", True),
            ("pipeline", "REP", True),
            ("pipeline", "Rep", True),
            ("headcount", "DEPARTMENT", True),
        ]

        for metric, dimension, expected_valid in cases:
            valid, error = dcl_client.validate_dimension(metric, dimension)
            assert valid == expected_valid, \
                f"{metric}+{dimension}: expected valid={expected_valid}, got {valid}. Error: {error}"

    def test_unknown_metric_returns_helpful_error(self, dcl_client):
        """Validating dimension for unknown metric should error helpfully."""
        valid, error = dcl_client.validate_dimension("fake_metric_xyz", "segment")

        assert not valid, "Unknown metric should fail validation"
        assert error is not None, "Error message should be provided"
        assert "Unknown metric" in error or "not found" in error.lower(), \
            f"Error should indicate metric is unknown: {error}"

    def test_get_valid_dimensions_returns_list(self, dcl_client):
        """get_valid_dimensions should return list of valid dimensions."""
        # Test a few metrics known to have dimensions
        for metric in ["revenue", "pipeline", "headcount"]:
            dims = dcl_client.get_valid_dimensions(metric)

            assert isinstance(dims, list), f"{metric}: should return list, got {type(dims)}"
            assert len(dims) > 0, f"{metric}: should have at least one valid dimension"

    def test_unknown_metric_returns_empty_dimensions(self, dcl_client):
        """Unknown metric should return empty list for valid dimensions."""
        dims = dcl_client.get_valid_dimensions("fake_metric_xyz")
        assert dims == [], f"Unknown metric should return empty list, got {dims}"


class TestDimensionValidationCoverage:
    """Verify we have test coverage for all metric+dimension combinations."""

    def test_all_metrics_have_dimension_tests(self, dcl_catalog):
        """
        Every metric in catalog should have at least one dimension validation test.

        This ensures we don't add metrics to DCL without testing their dimensions.
        """
        tested_metrics = {metric for metric, _, _, _ in DIMENSION_VALIDATION_CASES}
        catalog_metrics = set(dcl_catalog.metrics.keys())

        untested = catalog_metrics - tested_metrics

        # Allow some metrics that genuinely don't support dimensions
        allowed_untested = {
            # Add metrics that don't support any dimensions
        }
        truly_untested = untested - allowed_untested

        if truly_untested:
            pytest.fail(
                f"Metrics without dimension validation tests:\n"
                + "\n".join(f"  - {m}" for m in sorted(truly_untested))
                + "\n\nAdd test cases to DIMENSION_VALIDATION_CASES"
            )

    def test_negative_cases_exist_for_all_tested_metrics(self, dcl_client):
        """
        Every metric with dimension tests should have at least one INVALID dimension test.

        This ensures we're actually testing the rejection path, not just the happy path.
        """
        # Group test cases by metric
        metric_cases = {}
        for metric, dimension, should_pass, _ in DIMENSION_VALIDATION_CASES:
            if metric not in metric_cases:
                metric_cases[metric] = {"valid": [], "invalid": []}
            if should_pass:
                metric_cases[metric]["valid"].append(dimension)
            else:
                metric_cases[metric]["invalid"].append(dimension)

        # Check each metric has at least one invalid test
        missing_negative = []
        for metric, cases in metric_cases.items():
            if len(cases["invalid"]) == 0:
                missing_negative.append(metric)

        if missing_negative:
            pytest.fail(
                f"Metrics missing INVALID dimension tests:\n"
                + "\n".join(f"  - {m}" for m in sorted(missing_negative))
                + "\n\nAdd invalid dimension test cases to ensure rejection works"
            )
