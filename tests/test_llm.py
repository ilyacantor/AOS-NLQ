"""
Tests for LLM integration (prompts and client).

Uses mocking to avoid actual API calls in unit tests.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.nlq.llm.prompts import (
    QUERY_PARSER_PROMPT,
    ANSWER_FORMATTER_PROMPT,
    QUERY_CLARIFICATION_PROMPT,
)
from src.nlq.llm.client import ClaudeClient


class TestQueryParserPrompt:
    """Tests for the query parser prompt."""

    def test_prompt_contains_all_intent_types(self):
        """Verify all intent types are documented in prompt."""
        intents = [
            "POINT_QUERY",
            "COMPARISON_QUERY",
            "TREND_QUERY",
            "AGGREGATION_QUERY",
            "BREAKDOWN_QUERY",
        ]
        for intent in intents:
            assert intent in QUERY_PARSER_PROMPT, f"Missing intent: {intent}"

    def test_prompt_contains_canonical_metrics(self):
        """Verify canonical metrics are listed."""
        metrics = [
            "revenue",
            "bookings",
            "cogs",
            "gross_profit",
            "gross_margin_pct",
            "operating_profit",
            "net_income",
            "cash",
            "ar",
            "ap",
        ]
        for metric in metrics:
            assert metric in QUERY_PARSER_PROMPT, f"Missing metric: {metric}"

    def test_prompt_contains_period_types(self):
        """Verify period types are listed."""
        period_types = ["annual", "quarterly", "half_year"]
        for pt in period_types:
            assert pt in QUERY_PARSER_PROMPT, f"Missing period type: {pt}"

    def test_prompt_contains_relative_period_keywords(self):
        """Verify relative period keywords are mapped."""
        keywords = ["last_year", "this_year", "last_quarter", "this_quarter"]
        for kw in keywords:
            assert kw in QUERY_PARSER_PROMPT, f"Missing keyword: {kw}"

    def test_prompt_requests_json_only(self):
        """Verify prompt explicitly requests JSON without markdown."""
        assert "JSON" in QUERY_PARSER_PROMPT
        assert "no markdown" in QUERY_PARSER_PROMPT.lower()

    def test_prompt_shows_expected_response_structure(self):
        """Verify prompt shows the expected JSON structure."""
        assert '"intent"' in QUERY_PARSER_PROMPT
        assert '"metric"' in QUERY_PARSER_PROMPT
        assert '"period_type"' in QUERY_PARSER_PROMPT
        assert '"period_reference"' in QUERY_PARSER_PROMPT
        assert '"is_relative"' in QUERY_PARSER_PROMPT


class TestClaudeClientInit:
    """Tests for ClaudeClient initialization."""

    def test_raises_without_api_key(self):
        """Should raise ValueError if no API key available."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if present
            with patch.object(ClaudeClient, "__init__", lambda self, **kwargs: None):
                pass  # Skip actual init

            with pytest.raises(ValueError, match="API key required"):
                ClaudeClient()

    def test_uses_environment_variable(self):
        """Should read API key from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key-123"}):
            with patch("anthropic.Anthropic"):
                client = ClaudeClient()
                assert client.api_key == "test-key-123"

    def test_prefers_explicit_api_key(self):
        """Explicit api_key parameter takes precedence."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("anthropic.Anthropic"):
                client = ClaudeClient(api_key="explicit-key")
                assert client.api_key == "explicit-key"

    def test_default_model(self):
        """Should use claude-sonnet-4-20250514 by default."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                client = ClaudeClient()
                assert client.model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        """Should allow custom model override."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                client = ClaudeClient(model="claude-opus-4-20250514")
                assert client.model == "claude-opus-4-20250514"


class TestClaudeClientParseQuery:
    """Tests for parse_query method."""

    @pytest.fixture
    def mock_client(self):
        """Create a ClaudeClient with mocked Anthropic client."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                client = ClaudeClient()
                client.client = MagicMock()
                return client

    def test_parse_query_returns_dict(self, mock_client):
        """parse_query should return parsed dictionary."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"intent": "POINT_QUERY", "metric": "revenue", "period_type": "annual", "period_reference": "2024", "is_relative": false}')]
        mock_client.client.messages.create.return_value = mock_response

        result = mock_client.parse_query("What was revenue in 2024?")

        assert isinstance(result, dict)
        assert result["intent"] == "POINT_QUERY"
        assert result["metric"] == "revenue"
        assert result["period_type"] == "annual"
        assert result["period_reference"] == "2024"
        assert result["is_relative"] is False

    def test_parse_query_uses_system_prompt(self, mock_client):
        """parse_query should pass system prompt to Claude."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"intent": "POINT_QUERY", "metric": "revenue", "period_type": "annual", "period_reference": "2024", "is_relative": false}')]
        mock_client.client.messages.create.return_value = mock_response

        mock_client.parse_query("What was revenue?")

        call_kwargs = mock_client.client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == QUERY_PARSER_PROMPT

    def test_parse_query_passes_question_as_user_message(self, mock_client):
        """parse_query should pass question as user message."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"intent": "POINT_QUERY", "metric": "revenue", "period_type": "annual", "period_reference": "2024", "is_relative": false}')]
        mock_client.client.messages.create.return_value = mock_response

        question = "What was revenue in Q4 2025?"
        mock_client.parse_query(question)

        call_kwargs = mock_client.client.messages.create.call_args.kwargs
        assert call_kwargs["messages"] == [{"role": "user", "content": question}]


class TestClaudeClientCleanJsonResponse:
    """Tests for JSON response cleaning."""

    @pytest.fixture
    def client(self):
        """Create a ClaudeClient for testing."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                return ClaudeClient()

    def test_clean_plain_json(self, client):
        """Plain JSON should pass through unchanged."""
        json_str = '{"key": "value"}'
        result = client._clean_json_response(json_str)
        assert result == json_str

    def test_clean_json_with_code_fence(self, client):
        """Should remove markdown code fences."""
        content = '```json\n{"key": "value"}\n```'
        result = client._clean_json_response(content)
        assert result == '{"key": "value"}'

    def test_clean_json_with_plain_code_fence(self, client):
        """Should handle code fence without language specifier."""
        content = '```\n{"key": "value"}\n```'
        result = client._clean_json_response(content)
        assert result == '{"key": "value"}'

    def test_clean_preserves_multiline_json(self, client):
        """Should preserve multiline JSON within code fences."""
        content = '''```json
{
  "intent": "POINT_QUERY",
  "metric": "revenue"
}
```'''
        result = client._clean_json_response(content)
        parsed = json.loads(result)
        assert parsed["intent"] == "POINT_QUERY"
        assert parsed["metric"] == "revenue"

    def test_clean_strips_whitespace(self, client):
        """Should strip leading/trailing whitespace."""
        content = '  \n{"key": "value"}\n  '
        result = client._clean_json_response(content)
        assert result == '{"key": "value"}'


class TestOtherPrompts:
    """Tests for additional prompts."""

    def test_answer_formatter_prompt_exists(self):
        """ANSWER_FORMATTER_PROMPT should be defined."""
        assert ANSWER_FORMATTER_PROMPT is not None
        assert len(ANSWER_FORMATTER_PROMPT) > 0

    def test_answer_formatter_includes_formatting_guidance(self):
        """Answer formatter should provide formatting guidance."""
        assert "currency" in ANSWER_FORMATTER_PROMPT.lower() or "$" in ANSWER_FORMATTER_PROMPT
        assert "%" in ANSWER_FORMATTER_PROMPT

    def test_clarification_prompt_exists(self):
        """QUERY_CLARIFICATION_PROMPT should be defined."""
        assert QUERY_CLARIFICATION_PROMPT is not None
        assert len(QUERY_CLARIFICATION_PROMPT) > 0

    def test_clarification_prompt_handles_ambiguity(self):
        """Clarification prompt should address ambiguous queries."""
        assert "ambiguous" in QUERY_CLARIFICATION_PROMPT.lower()
