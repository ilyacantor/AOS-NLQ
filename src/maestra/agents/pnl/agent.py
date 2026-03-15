"""
Maestra P&L Agent — Phase 2.

Orchestrates LLM-based income statement generation with deterministic validation.
Reads the constitution prompt template, constructs a user message from entity data,
calls the Anthropic API, validates the output, and reprompts on failure.

No silent fallbacks. If the LLM call fails, the error propagates.
All monetary values use Decimal.
"""

import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import anthropic
from pydantic import BaseModel

from src.maestra.validation.reprompt import reprompt_loop
from src.maestra.validation.schema import (
    FinancialOutput,
    Flag,
    ValidationResult,
)
from src.maestra.validation.seed_coa import CoALookup

from .extract import extract_net_income

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompt_template.md"

_LAYER_3_PREAMBLE = (
    "The following accounting policy document was provided by the entity. "
    "Apply these policies when classifying accounts and recognizing "
    "revenue/expenses. Where the policy is silent, use the axioms above."
)


class PnLResult(BaseModel):
    """Result of a P&L agent run.

    Attributes:
        output: The validated FinancialOutput, or None if the agent halted.
        net_income: Extracted net income as signed Decimal, or None if halted.
        halted: True if validation failed after all attempts.
        halt_reasons: List of human-readable reasons for halting.
        validation_attempts: All ValidationResult objects from each attempt.
        flags: All flags from the final output, or accumulated halt flags.
    """

    output: FinancialOutput | None
    net_income: Decimal | None
    halted: bool
    halt_reasons: list[str]
    validation_attempts: list[ValidationResult]
    flags: list[Flag]


def _read_system_prompt() -> str:
    """Read the prompt template from disk. Fails loudly if file is missing."""
    if not _PROMPT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"P&L agent prompt template not found at {_PROMPT_TEMPLATE_PATH}. "
            f"The prompt_template.md file must exist alongside agent.py."
        )
    return _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _build_user_message(
    entity_data: dict,
    entity_id: str,
    period_start: date,
    period_end: date,
    policy_doc: str | None,
    industry_profile: str | None,
) -> str:
    """Construct the user message for the LLM.

    Includes entity data as JSON, optional policy document with Layer 3
    preamble, optional industry profile, and instruction to produce an
    income statement.
    """
    parts: list[str] = []

    # Entity data
    parts.append("## Entity Financial Data")
    parts.append(f"Entity ID: {entity_id}")
    parts.append(f"Period: {period_start.isoformat()} to {period_end.isoformat()}")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(entity_data, indent=2, default=str))
    parts.append("```")

    # Policy document (Layer 3)
    if policy_doc is not None:
        parts.append("")
        parts.append("## Entity Accounting Policy (Layer 3)")
        parts.append(_LAYER_3_PREAMBLE)
        parts.append("")
        parts.append(policy_doc)

    # Industry profile
    if industry_profile is not None:
        parts.append("")
        parts.append("## Industry Profile")
        parts.append(industry_profile)

    # Instruction
    parts.append("")
    parts.append("## Instruction")
    parts.append(
        "Produce a complete income statement for this entity and period. "
        "Return the output as a single JSON object conforming to the "
        "FinancialOutput schema with statement_type='income_statement'. "
        "Include all required fields: entity_id, period_start, period_end, "
        "currency, line_items, journal_entries, and flags. "
        "Use exact decimal values for all monetary amounts — no floating point. "
        "Return ONLY the JSON object, no surrounding text or markdown."
    )

    return "\n".join(parts)


def _parse_llm_response(response_text: str) -> FinancialOutput:
    """Parse the LLM's JSON response into a FinancialOutput.

    Strips markdown code fences if present. Raises on parse failure —
    no silent fallbacks.
    """
    text = response_text.strip()

    # Strip markdown code fences if the LLM wrapped the JSON
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"P&L agent LLM response is not valid JSON. "
            f"Response starts with: {response_text[:200]!r}. "
            f"JSON parse error: {e}"
        ) from e

    try:
        return FinancialOutput.model_validate(data)
    except Exception as e:
        raise ValueError(
            f"P&L agent LLM response JSON does not conform to FinancialOutput schema. "
            f"Validation error: {e}"
        ) from e


async def run_pnl_agent(
    entity_data: dict,
    entity_id: str,
    period_start: date,
    period_end: date,
    policy_doc: str | None,
    industry_profile: str | None,
    model: str = "claude-sonnet-4-20250514",
) -> PnLResult:
    """Run the P&L agent to produce an income statement.

    Calls the Anthropic API with the constitution prompt and entity data,
    validates the output, and reprompts up to 3 times on validation failure.

    Args:
        entity_data: Financial data for the entity (accounts, transactions).
        entity_id: Unique identifier for the entity.
        period_start: Start of the reporting period.
        period_end: End of the reporting period.
        policy_doc: Optional accounting policy document (Layer 3).
        industry_profile: Optional industry profile for context.
        model: Anthropic model to use. Defaults to claude-sonnet-4-20250514.

    Returns:
        PnLResult with the validated output or halt information.

    Raises:
        anthropic.APIError: If the Anthropic API call fails.
        FileNotFoundError: If the prompt template file is missing.
    """
    system_prompt = _read_system_prompt()

    user_message = _build_user_message(
        entity_data=entity_data,
        entity_id=entity_id,
        period_start=period_start,
        period_end=period_end,
        policy_doc=policy_doc,
        industry_profile=industry_profile,
    )

    client = anthropic.Anthropic()

    async def agent_fn(prompt: str) -> FinancialOutput:
        """Call the Anthropic API and parse the response.

        This function is passed to reprompt_loop. It must raise on any
        failure — no silent fallbacks.
        """
        logger.info(
            "Calling Anthropic API for P&L agent — model=%s, entity=%s",
            model, entity_id,
        )

        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content from the response
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        if not response_text:
            raise ValueError(
                f"P&L agent received empty response from Anthropic API. "
                f"Model: {model}, entity: {entity_id}, "
                f"stop_reason: {response.stop_reason}"
            )

        return _parse_llm_response(response_text)

    # Build CoA lookup if entity_data contains chart_of_accounts
    coa: CoALookup | None = None
    if "chart_of_accounts" in entity_data:
        coa = CoALookup()
        coa.seed_from_records(entity_id, entity_data["chart_of_accounts"])

    # Run the reprompt loop
    validated_output, validation_attempts = await reprompt_loop(
        agent_fn=agent_fn,
        initial_prompt=user_message,
        max_attempts=3,
        coa=coa,
    )

    # Collect flags
    flags: list[Flag] = []

    # Add flags about missing policy document
    if policy_doc is None:
        flags.append(Flag(
            severity="warning",
            code="MISSING_POLICY",
            message="No accounting policy document provided for this entity. "
                    "Classifications rely solely on constitution axioms and "
                    "industry defaults.",
            affected_accounts=[],
        ))

    if validated_output is not None:
        # Merge flags from the output
        flags.extend(validated_output.flags)

        # Extract net income
        net_income = extract_net_income(validated_output)

        return PnLResult(
            output=validated_output,
            net_income=net_income,
            halted=False,
            halt_reasons=[],
            validation_attempts=validation_attempts,
            flags=flags,
        )
    else:
        # All attempts failed — collect halt reasons from last validation
        halt_reasons: list[str] = []
        if validation_attempts:
            last_result = validation_attempts[-1]
            for error in last_result.errors:
                if error.severity == "halt":
                    halt_reasons.append(
                        f"[{error.rule_code}] {error.message}"
                    )

        return PnLResult(
            output=None,
            net_income=None,
            halted=True,
            halt_reasons=halt_reasons,
            validation_attempts=validation_attempts,
            flags=flags,
        )
