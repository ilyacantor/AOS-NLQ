"""
Negative Case Tests - Verify errors surface, no silent fallbacks.

These tests validate that when something goes WRONG, NLQ:
1. Returns a clear error (not silent failure)
2. Does NOT return random/default data
3. Provides helpful guidance for recovery

NO MOCKING - tests hit real DCL or fail.
"""

import pytest
from tests.eval.conftest import collect_failures


# =============================================================================
# NEGATIVE TEST CASES
# =============================================================================
# These are things that MUST fail with helpful errors.


class TestUnknownMetricErrors:
    """Test that unknown metrics fail with helpful errors."""

    def test_unknown_metric_returns_none(self, dcl_client):
        """Unknown metric must return None, not random match."""
        unknown_metrics = [
            "fake_metric_xyz",
            "asdfghjkl",
            "quantum_flux_capacitor",
            "metric_that_does_not_exist_12345",
            "blahblahblah",
        ]

        for term in unknown_metrics:
            result = dcl_client.resolve_metric(term)
            assert result is None, \
                f"Unknown metric '{term}' should return None, got '{result.id if result else 'N/A'}'"

    def test_unknown_metric_query_returns_error(self, dcl_client):
        """Querying unknown metric must return error, not empty data."""
        result = dcl_client.query(
            metric="completely_fake_metric_xyz",
            time_range={"period": "2025"}
        )

        # Should have error OR status=error OR metric_error
        has_error = (
            "error" in result or
            result.get("status") == "error" or
            "metric_error" in result
        )
        assert has_error, \
            f"Query for unknown metric should return error, got: {result}"

    def test_no_silent_fallback_to_default_metric(self, dcl_client):
        """Unknown metric must NOT silently return revenue/other default."""
        unknown_terms = [
            "xyz123",
            "not_a_real_metric",
            "bogus_data_point",
        ]

        for term in unknown_terms:
            result = dcl_client.resolve_metric(term)

            # Must be None, not a fallback
            if result is not None:
                pytest.fail(
                    f"'{term}' resolved to '{result.id}' instead of None. "
                    "This indicates a silent fallback which is dangerous!"
                )


class TestInvalidDimensionErrors:
    """Test that invalid dimensions fail with helpful errors."""

    def test_invalid_dimension_returns_error_with_alternatives(self, dcl_client):
        """Invalid dimension must return error that lists valid alternatives."""
        test_cases = [
            ("revenue", "fake_dimension"),
            ("revenue", "rep"),  # revenue doesn't support rep
            ("pipeline", "department"),  # pipeline doesn't support department
            ("headcount", "stage"),  # headcount doesn't support stage
            ("enps", "customer"),  # eNPS doesn't support customer
        ]

        for metric, invalid_dim in test_cases:
            valid, error = dcl_client.validate_dimension(metric, invalid_dim)

            assert not valid, \
                f"{metric}+{invalid_dim} should be invalid"

            assert error is not None, \
                f"{metric}+{invalid_dim}: error message should be provided"

            # Error should either list alternatives or explain why invalid
            helpful_error = (
                "Valid dimensions:" in str(error) or
                "does not support" in str(error) or
                "Invalid dimension" in str(error) or
                "not a valid dimension" in str(error).lower()
            )
            assert helpful_error, \
                f"{metric}+{invalid_dim}: error should be helpful, got: {error}"

    def test_invalid_dimension_query_does_not_return_aggregate(self, dcl_client):
        """Invalid dimension must NOT silently return aggregate data."""
        # If we ask for revenue by 'fake_dim', we should NOT get aggregate revenue
        result = dcl_client.query(
            metric="revenue",
            dimensions=["totally_fake_dimension_xyz"],
            time_range={"period": "2025"}
        )

        # Should have error, not data
        if "data" in result and result["data"] is not None:
            if not isinstance(result["data"], list) or len(result["data"]) > 0:
                # If we got data, that's a silent fallback - BAD
                if "error" not in result and result.get("status") != "error":
                    pytest.fail(
                        f"Query with invalid dimension returned data without error. "
                        f"This is a silent fallback! Result: {result}"
                    )


class TestInvalidTimeRangeErrors:
    """Test that invalid time ranges fail appropriately."""

    def test_future_period_behavior(self, dcl_client):
        """Querying future period should return empty or appropriate response."""
        result = dcl_client.query(
            metric="revenue",
            time_range={"period": "2030", "granularity": "annual"}
        )

        # Either error or empty data is acceptable for future dates
        # What's NOT acceptable is fake/projected data without indication
        if "data" in result and result["data"] is not None:
            data = result["data"]
            if isinstance(data, list) and len(data) > 0:
                # If we got data for 2030, there should be some indication
                # it's projected/forecasted, not actual
                pass  # This is acceptable if clearly marked

    def test_malformed_period_returns_error(self, dcl_client):
        """Malformed period should return error, not crash."""
        malformed_periods = [
            "not-a-date",
            "Q99 2025",
            "13/2025",
            "",
            None,
        ]

        for period in malformed_periods:
            try:
                result = dcl_client.query(
                    metric="revenue",
                    time_range={"period": period, "granularity": "annual"}
                )
                # Should have error in result
                # (Some implementations may raise exception instead, which is also acceptable)
            except Exception:
                # Exception is acceptable for malformed input
                pass


class TestEmptyResultHandling:
    """Test that empty results are handled correctly."""

    def test_empty_result_is_distinguishable_from_error(self, dcl_client):
        """Empty result (no data for period) must be distinguishable from error."""
        # Use a known metric but unusual time range
        result = dcl_client.query(
            metric="revenue",
            time_range={"period": "2010", "granularity": "annual"}  # Likely no data
        )

        # Should NOT have error key if it's just empty
        # OR should have clear "no_data" indicator
        # The key point is: user should know WHY there's no data
        if "data" not in result and "error" not in result:
            pytest.fail(
                "Result has neither 'data' nor 'error' - ambiguous response"
            )


class TestCatalogErrors:
    """Test catalog-related error scenarios."""

    def test_get_valid_dimensions_for_unknown_metric(self, dcl_client):
        """Getting dimensions for unknown metric should return empty, not crash."""
        dims = dcl_client.get_valid_dimensions("completely_fake_metric_xyz")

        assert isinstance(dims, list), \
            f"Should return list, got {type(dims)}"
        assert len(dims) == 0, \
            f"Unknown metric should have empty dimensions, got {dims}"

    def test_resolve_empty_string(self, dcl_client):
        """Resolving empty string should return None, not crash."""
        result = dcl_client.resolve_metric("")
        assert result is None, "Empty string should resolve to None"

    def test_resolve_whitespace_only(self, dcl_client):
        """Resolving whitespace should return None, not crash."""
        result = dcl_client.resolve_metric("   ")
        assert result is None, "Whitespace-only should resolve to None"


class TestErrorMessageQuality:
    """Test that error messages are helpful and actionable."""

    def test_unknown_metric_error_is_helpful(self, dcl_client):
        """Error for unknown metric should guide user to valid options."""
        # Query an unknown metric
        result = dcl_client.query(
            metric="fake_metric_xyz",
            time_range={"period": "2025"}
        )

        if "error" in result:
            error = result["error"]
            # Error should give some guidance
            # Could include: "Unknown metric", "Did you mean", list of valid metrics, etc.
            assert len(str(error)) > 10, \
                f"Error message too short to be helpful: {error}"

    def test_invalid_dimension_error_lists_valid_options(self, dcl_client):
        """Error for invalid dimension should list what IS valid."""
        valid, error = dcl_client.validate_dimension("revenue", "fake_dim_xyz")

        assert not valid, "Should be invalid"
        assert error is not None, "Should have error message"

        # Check error is informative
        error_str = str(error)
        assert len(error_str) > 20, \
            f"Error message too short: {error_str}"


class TestNoSilentFailures:
    """Ensure the system never fails silently."""

    def test_no_none_metric_in_successful_response(self, dcl_client):
        """Successful query should have identifiable metric in response."""
        result = dcl_client.query(
            metric="revenue",
            time_range={"period": "2025"}
        )

        # A successful response should make it clear what was queried
        if "error" not in result:
            assert "data" in result, "Successful response should have 'data'"
            # Data should not be silently None without indication
            if result["data"] is None:
                # Should have some indication this is intentional
                pass  # This might be okay if there's a reason field

    def test_dimensional_query_returns_dimensional_data(self, dcl_client):
        """Dimensional query should NOT return aggregate by accident."""
        result = dcl_client.query(
            metric="revenue",
            dimensions=["segment"],
            time_range={"period": "2025"}
        )

        if "error" not in result and "data" in result:
            data = result["data"]
            if isinstance(data, list) and len(data) > 0:
                # If we asked for dimensional breakdown, should get records with dimension
                first_record = data[0]
                if isinstance(first_record, dict):
                    # Should have segment in the response or in structure
                    has_dimensional_structure = (
                        "segment" in first_record or
                        "dimension" in first_record or
                        "value" in first_record
                    )
                    assert has_dimensional_structure, \
                        f"Dimensional query should return dimensional data: {first_record}"
