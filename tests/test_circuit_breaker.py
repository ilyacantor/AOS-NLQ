"""
Tests for Claude API client circuit breaker and timeout (H2 fix).

Validates:
1. Circuit breaker transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
2. Timeout is passed to the Anthropic SDK
3. ClaudeAPIUnavailable raised when breaker is OPEN
4. 5xx errors trip the breaker, 4xx do not
5. Recovery after timeout period
"""

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.nlq.llm.client import (
    CircuitBreaker,
    ClaudeAPIUnavailable,
    ClaudeAPITimeout,
    ClaudeClient,
)


class TestCircuitBreaker:
    """Unit tests for the CircuitBreaker state machine."""

    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Reset
        cb.record_failure()
        cb.record_failure()
        # Still only 2 consecutive failures — should be CLOSED
        assert cb.state == CircuitBreaker.CLOSED

    def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN


class TestClaudeClientTimeout:
    """Test that ClaudeClient passes timeout to the SDK."""

    def test_default_timeout_is_30s(self):
        with patch("src.nlq.llm.client.anthropic.Anthropic") as mock_cls:
            client = ClaudeClient(api_key="test-key")
            assert client.timeout == 30.0
            mock_cls.assert_called_once_with(api_key="test-key", timeout=30.0)

    def test_custom_timeout(self):
        with patch("src.nlq.llm.client.anthropic.Anthropic") as mock_cls:
            client = ClaudeClient(api_key="test-key", timeout=15.0)
            assert client.timeout == 15.0
            mock_cls.assert_called_once_with(api_key="test-key", timeout=15.0)


class TestClaudeClientCircuitBreaker:
    """Test circuit breaker integration in ClaudeClient."""

    def _make_client(self):
        """Create client with mocked Anthropic SDK."""
        with patch("src.nlq.llm.client.anthropic.Anthropic"):
            return ClaudeClient(api_key="test-key")

    def test_raises_unavailable_when_breaker_open(self):
        client = self._make_client()
        # Force breaker open
        client._circuit_breaker._state = CircuitBreaker.OPEN
        client._circuit_breaker._last_failure_time = time.time()

        with pytest.raises(ClaudeAPIUnavailable):
            client._call_api(model="test", max_tokens=10, messages=[])

    def test_success_resets_breaker(self):
        client = self._make_client()
        mock_response = MagicMock()
        client.client.messages.create = MagicMock(return_value=mock_response)

        client._call_api(model="test", max_tokens=10, messages=[])
        assert client._circuit_breaker.state == CircuitBreaker.CLOSED

    def test_api_timeout_trips_breaker(self):
        client = self._make_client()
        import anthropic
        client.client.messages.create = MagicMock(
            side_effect=anthropic.APITimeoutError(request=MagicMock())
        )

        with pytest.raises(ClaudeAPITimeout):
            client._call_api(model="test", max_tokens=10, messages=[])

        assert client._circuit_breaker._consecutive_failures == 1

    def test_connection_error_trips_breaker(self):
        client = self._make_client()
        import anthropic
        client.client.messages.create = MagicMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(anthropic.APIConnectionError):
            client._call_api(model="test", max_tokens=10, messages=[])

        assert client._circuit_breaker._consecutive_failures == 1

    def test_5xx_trips_breaker(self):
        client = self._make_client()
        import anthropic
        error = anthropic.InternalServerError(
            message="server error",
            response=MagicMock(status_code=500),
            body=None,
        )
        client.client.messages.create = MagicMock(side_effect=error)

        with pytest.raises(anthropic.InternalServerError):
            client._call_api(model="test", max_tokens=10, messages=[])

        assert client._circuit_breaker._consecutive_failures == 1

    def test_4xx_does_not_trip_breaker(self):
        client = self._make_client()
        import anthropic
        error = anthropic.BadRequestError(
            message="bad request",
            response=MagicMock(status_code=400),
            body=None,
        )
        client.client.messages.create = MagicMock(side_effect=error)

        with pytest.raises(anthropic.BadRequestError):
            client._call_api(model="test", max_tokens=10, messages=[])

        # 400 should NOT increment failure count
        assert client._circuit_breaker._consecutive_failures == 0

    def test_api_key_required(self):
        """Verify that missing API key raises ValueError, not a silent fallback."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("src.nlq.llm.client.anthropic.Anthropic"):
                with pytest.raises(ValueError, match="Anthropic API key required"):
                    ClaudeClient(api_key=None)
