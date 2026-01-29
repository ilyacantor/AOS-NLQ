"""
Claude API client wrapper for AOS-NLQ.

Provides a clean interface to the Anthropic Claude API for:
- Query parsing (extracting intent, metrics, periods)
- Answer formatting
- Query clarification

Uses Claude claude-sonnet-4-20250514 for speed/cost balance.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import anthropic

from src.nlq.llm.prompts import QUERY_PARSER_PROMPT

logger = logging.getLogger(__name__)


class ClaudeClient:
    """
    Claude API client for NLQ query processing.

    Wraps the Anthropic Python SDK with NLQ-specific methods.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Fast and cost-effective
    MAX_TOKENS = 500  # Sufficient for structured JSON responses

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the Claude client.

        Args:
            api_key: Anthropic API key. If not provided, reads from
                    ANTHROPIC_API_KEY environment variable.
            model: Model to use. Defaults to claude-sonnet-4-20250514.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self.model = model or self.DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=self.api_key)

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
            anthropic.APIError: If API call fails
        """
        logger.debug(f"Parsing query: {question}")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            system=QUERY_PARSER_PROMPT,
            messages=[{"role": "user", "content": question}]
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text.strip()  # type: ignore
            content = self._clean_json_response(content)

            components = json.loads(content)
            if isinstance(components, list):
                logger.info(f"LLM breakdown for '{metric}': {components}")
                return components
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}]
            )
            return True
        except Exception as e:
            logger.error(f"Claude API health check failed: {e}")
            return False
