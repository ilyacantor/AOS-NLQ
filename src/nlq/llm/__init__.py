"""
LLM integration for AOS-NLQ.

This module provides:
- ClaudeClient: Wrapper for Anthropic Claude API
- prompts: System prompts for query parsing

Uses Claude API (Anthropic) for natural language understanding.
The LLM is used for query parsing, not for generating answers.
"""

from src.nlq.llm.client import ClaudeClient
from src.nlq.llm.prompts import QUERY_PARSER_PROMPT

__all__ = ["ClaudeClient", "QUERY_PARSER_PROMPT"]
