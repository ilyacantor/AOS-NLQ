"""
Claude API client wrapper for AOS-NLQ.

Provides a clean interface to the Anthropic Claude API for:
- Query parsing (extracting intent, metrics, periods)
- Answer formatting
- Query clarification

Includes timeout enforcement and a circuit breaker to prevent
cascading failures when the Claude API is down or slow.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import anthropic

from src.nlq.llm.prompts import QUERY_PARSER_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker — prevents hammering a failing API
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Simple circuit breaker for external API calls.

    States:
        CLOSED  — normal operation, calls go through
        OPEN    — API assumed down, calls rejected immediately
        HALF_OPEN — one probe call allowed to test recovery

    Transitions:
        CLOSED  → OPEN      after `failure_threshold` consecutive failures
        OPEN    → HALF_OPEN after `recovery_timeout` seconds
        HALF_OPEN → CLOSED  on first success
        HALF_OPEN → OPEN    on first failure
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        name: str = "claude_api",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> str:
        """Current state, auto-transitioning OPEN -> HALF_OPEN on timeout."""
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                logger.info(f"Circuit breaker [{self.name}]: OPEN -> HALF_OPEN (recovery window)")
        return self._state

    def allow_request(self) -> bool:
        """Return True if a request is allowed through."""
        return self.state != self.OPEN

    def record_success(self):
        """Record a successful call — resets the breaker to CLOSED."""
        if self._state != self.CLOSED:
            logger.info(f"Circuit breaker [{self.name}]: {self._state} -> CLOSED")
        self._state = self.CLOSED
        self._consecutive_failures = 0

    def record_failure(self):
        """Record a failed call — may trip the breaker to OPEN."""
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == self.HALF_OPEN:
            self._state = self.OPEN
            logger.warning(f"Circuit breaker [{self.name}]: HALF_OPEN -> OPEN (probe failed)")
        elif self._consecutive_failures >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning(
                f"Circuit breaker [{self.name}]: CLOSED -> OPEN "
                f"({self._consecutive_failures} consecutive failures)"
            )


class ClaudeAPIUnavailable(Exception):
    """Raised when the Claude API circuit breaker is open."""
    pass


class ClaudeAPITimeout(Exception):
    """Raised when a Claude API call exceeds the configured timeout."""
    pass


class ClaudeClient:
    """
    Claude API client for NLQ query processing.

    Wraps the Anthropic Python SDK with NLQ-specific methods,
    timeout enforcement, and circuit-breaker protection.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Fast and cost-effective
    MAX_TOKENS = 500  # Sufficient for structured JSON responses
    DEFAULT_TIMEOUT = 30.0  # seconds — hard cap on any single API call

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize the Claude client.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
            model: Model to use. Defaults to claude-sonnet-4-20250514.
            timeout: Request timeout in seconds. Defaults to 30.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Create client with explicit timeout so the SDK enforces it too
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            timeout=self.timeout,
        )

        # Shared circuit breaker across all methods on this instance
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,
            name="claude_api",
        )

    def _call_api(self, **kwargs) -> anthropic.types.Message:
        """
        Central API call wrapper with circuit breaker and timeout.

        Raises:
            ClaudeAPIUnavailable: if circuit breaker is OPEN
            ClaudeAPITimeout: if the request exceeds timeout
            anthropic.APIError: on other API errors
        """
        if not self._circuit_breaker.allow_request():
            raise ClaudeAPIUnavailable(
                f"Claude API circuit breaker is OPEN — "
                f"will retry after {self._circuit_breaker.recovery_timeout}s"
            )

        try:
            response = self.client.messages.create(**kwargs)
            self._circuit_breaker.record_success()
            return response
        except anthropic.APITimeoutError as e:
            self._circuit_breaker.record_failure()
            raise ClaudeAPITimeout(f"Claude API timed out after {self.timeout}s") from e
        except anthropic.APIConnectionError:
            self._circuit_breaker.record_failure()
            raise  # Let caller handle — but breaker is now closer to tripping
        except anthropic.APIStatusError as e:
            # 5xx = service issue -> count as failure; 4xx = client issue -> don't trip breaker
            if e.status_code >= 500:
                self._circuit_breaker.record_failure()
            raise

    def parse_query(self, question: str) -> Dict[str, Any]:
        """
        Use Claude to parse a natural language query.

        Args:
            question: Natural language question about financial data

        Returns:
            Dict with parsed components:
            - intent: Query type
            - metric: Canonical metric name
            - period_type: Type of period
            - period_reference: Period reference
            - is_relative: Whether period is relative

        Raises:
            ValueError: If response cannot be parsed as JSON
            ClaudeAPIUnavailable: If circuit breaker is open
            ClaudeAPITimeout: If API call exceeds timeout
            anthropic.APIError: If API call fails
        """
        logger.debug(f"Parsing query: {question}")

        response = self._call_api(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            system=QUERY_PARSER_PROMPT,
            messages=[{"role": "user", "content": question}],
        )

        # Extract text content
        content = response.content[0].text.strip()
        logger.debug(f"Raw LLM response: {content}")

        # Clean up response - handle markdown code fences
        content = self._clean_json_response(content)

        try:
            parsed = json.loads(content)
            logger.debug(f"Parsed result: {parsed}")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {content}")
            raise ValueError(f"Invalid JSON from Claude: {e}")

    def _clean_json_response(self, content: str) -> str:
        """
        Clean potential markdown formatting from JSON response.

        Handles cases where Claude wraps JSON in code fences despite
        being instructed not to.
        """
        content = content.strip()

        # Remove markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        return content.strip()

    def get_breakdown_components(self, metric: str) -> list[str]:
        """
        Ask Claude what metrics drive/compose a given metric.

        This is used as a fallback when BREAKDOWN_MAPPINGS doesn't have
        a predefined mapping for a metric.

        Args:
            metric: The metric to get breakdown components for

        Returns:
            List of component metric names that drive the given metric
        """
        prompt = f"""Given the financial/business metric "{metric}", what are the key component metrics or drivers that would explain changes in this metric?

Return a JSON array of 3-5 canonical metric names (snake_case) that are commonly used to break down or explain this metric.

Example for "revenue": ["new_logo_revenue", "expansion_revenue", "renewal_revenue", "churn_revenue"]
Example for "accounts_receivable": ["ar_current", "ar_30_days", "ar_60_days", "ar_90_plus_days"]
Example for "customer_acquisition_cost": ["marketing_spend", "sales_spend", "new_customers"]

Return ONLY the JSON array, no explanation."""

        try:
            response = self._call_api(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()  # type: ignore
            content = self._clean_json_response(content)

            components = json.loads(content)
            if isinstance(components, list):
                logger.info(f"LLM breakdown for '{metric}': {components}")
                return components
            return []
        except (ClaudeAPIUnavailable, ClaudeAPITimeout) as e:
            logger.warning(f"Claude API unavailable for breakdown '{metric}': {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to get LLM breakdown for '{metric}': {e}")
            return []

    def health_check(self) -> bool:
        """
        Check if the Claude API is accessible.

        Returns:
            True if API is reachable and authenticated
        """
        try:
            self._call_api(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}],
            )
            return True
        except Exception as e:
            logger.error(f"Claude API health check failed: {e}")
            return False
