"""
Unit tests for confidence scoring.

CRITICAL: ALL confidence scores MUST be bounded [0.0, 1.0].
These tests verify the bounded_confidence function and ConfidenceCalculator
handle all edge cases correctly.
"""

import math
import pytest

from src.nlq.core.confidence import bounded_confidence, ConfidenceCalculator


class TestBoundedConfidence:
    """Tests for the bounded_confidence function."""

    def test_normal_values_unchanged(self):
        """Test that values in [0, 1] are unchanged."""
        assert bounded_confidence(0.0) == 0.0
        assert bounded_confidence(0.5) == 0.5
        assert bounded_confidence(1.0) == 1.0
        assert bounded_confidence(0.95) == 0.95
        assert bounded_confidence(0.001) == 0.001

    def test_values_above_one_clamped(self):
        """Test that values > 1.0 are clamped to 1.0."""
        assert bounded_confidence(1.1) == 1.0
        assert bounded_confidence(2.0) == 1.0
        assert bounded_confidence(100.0) == 1.0
        assert bounded_confidence(1.0001) == 1.0

    def test_negative_values_clamped(self):
        """Test that negative values are clamped to 0.0."""
        assert bounded_confidence(-0.1) == 0.0
        assert bounded_confidence(-1.0) == 0.0
        assert bounded_confidence(-100.0) == 0.0
        assert bounded_confidence(-0.0001) == 0.0

    def test_nan_returns_zero(self):
        """Test that NaN returns 0.0."""
        assert bounded_confidence(float('nan')) == 0.0

    def test_infinity_returns_boundary(self):
        """Test that infinity values are handled."""
        assert bounded_confidence(float('inf')) == 0.0
        assert bounded_confidence(float('-inf')) == 0.0


class TestConfidenceCalculator:
    """Tests for the ConfidenceCalculator class."""

    def test_perfect_scores(self, confidence_calculator):
        """Test calculation with perfect component scores."""
        result = confidence_calculator.calculate(
            intent_score=1.0,
            entity_score=1.0,
            data_score=1.0
        )

        assert result == 1.0

    def test_zero_scores(self, confidence_calculator):
        """Test calculation with zero component scores."""
        result = confidence_calculator.calculate(
            intent_score=0.0,
            entity_score=0.0,
            data_score=0.0
        )

        assert result == 0.0

    def test_weighted_average(self, confidence_calculator):
        """Test that weights are applied correctly."""
        # Default weights: intent=0.4, entity=0.4, data=0.2
        result = confidence_calculator.calculate(
            intent_score=1.0,  # 0.4 * 1.0 = 0.4
            entity_score=0.5,  # 0.4 * 0.5 = 0.2
            data_score=0.0     # 0.2 * 0.0 = 0.0
        )

        expected = 0.4 + 0.2 + 0.0  # = 0.6
        assert abs(result - expected) < 0.001

    def test_output_is_always_bounded(self, confidence_calculator):
        """Test that output is bounded even with extreme inputs."""
        # Even with inputs > 1, output should be bounded
        result = confidence_calculator.calculate(
            intent_score=2.0,
            entity_score=2.0,
            data_score=2.0
        )

        assert result <= 1.0
        assert result >= 0.0

        # With negative inputs
        result = confidence_calculator.calculate(
            intent_score=-1.0,
            entity_score=-1.0,
            data_score=-1.0
        )

        assert result >= 0.0
        assert result <= 1.0

    def test_custom_weights(self):
        """Test calculator with custom weights."""
        calculator = ConfidenceCalculator(weights={
            "intent": 0.5,
            "entity": 0.3,
            "data": 0.2
        })

        result = calculator.calculate(
            intent_score=1.0,
            entity_score=0.0,
            data_score=0.0
        )

        assert abs(result - 0.5) < 0.001

    def test_calculate_from_booleans(self, confidence_calculator):
        """Test the boolean-based calculation method."""
        # All positive
        result = confidence_calculator.calculate_from_parse_result(
            metric_found=True,
            period_found=True,
            intent_detected=True,
            data_exists=True
        )

        assert result > 0.5
        assert result <= 1.0

        # All negative
        result = confidence_calculator.calculate_from_parse_result(
            metric_found=False,
            period_found=False,
            intent_detected=False,
            data_exists=False
        )

        assert result >= 0.0
        assert result < 0.5

    def test_ambiguous_flag_reduces_confidence(self, confidence_calculator):
        """Test that ambiguity flag reduces confidence."""
        confident = confidence_calculator.calculate_from_parse_result(
            metric_found=True,
            period_found=True,
            intent_detected=True,
            data_exists=True,
            is_ambiguous=False
        )

        ambiguous = confidence_calculator.calculate_from_parse_result(
            metric_found=True,
            period_found=True,
            intent_detected=True,
            data_exists=True,
            is_ambiguous=True
        )

        assert ambiguous < confident

    def test_confidence_never_exceeds_one_with_extreme_inputs(self, confidence_calculator):
        """
        CRITICAL: Prove confidence NEVER exceeds 1.0 even with extreme inputs.

        Per spec: inputs like (1.5, 2.0, 1.8) must still return bounded result.
        """
        result = confidence_calculator.calculate(
            intent_score=1.5,
            entity_score=2.0,
            data_score=1.8
        )

        assert result <= 1.0, f"Confidence {result} exceeded 1.0!"
        assert result >= 0.0, f"Confidence {result} went below 0.0!"
        # With all inputs clamped to 1.0, weighted average should be 1.0
        assert result == 1.0

    def test_confidence_never_goes_negative_with_extreme_inputs(self, confidence_calculator):
        """
        CRITICAL: Prove confidence NEVER goes below 0.0 even with extreme negative inputs.
        """
        result = confidence_calculator.calculate(
            intent_score=-5.0,
            entity_score=-10.0,
            data_score=-100.0
        )

        assert result >= 0.0, f"Confidence {result} went below 0.0!"
        assert result <= 1.0, f"Confidence {result} exceeded 1.0!"
        # With all inputs clamped to 0.0, weighted average should be 0.0
        assert result == 0.0
