"""
Maestra BS Agent — Phase 3.

Orchestrates LLM-based balance sheet generation with deterministic validation.
Consumes net income from the P&L agent as an immutable fact. Validates via
the shared Layer 0 validation rules plus equity roll-forward checks.

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

from .rollforward import (
    EquityRollforward,
    validate_equity_rollforward_with_supplementary,
)

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompt_template.md"

_LAYER_3_PREAMBLE = (
    "The following accounting policy document was provided by the entity. "
    "Apply these policies when classifying accounts. "
    "Where the policy is silent, use the axioms above."
)


class BSResult(BaseModel):
    """Result of a BS agent run.

    Attributes:
        output: The validated FinancialOutput, or None if the agent halted.
        halted: True if validation failed after all attempts.
        halt_reasons: List of human-readable reasons for halting.
        validation_attempts: All ValidationResult objects from each attempt.
        flags: All flags from the final output, or accumulated halt flags.
        equity_rollforward: Equity roll-forward validation result, or None if halted.
    """

    output: FinancialOutput | None
    halted: bool
    halt_reasons: list[str]
    validation_attempts: list[ValidationResult]
    flags: list[Flag]
    equity_rollforward: EquityRollforward | None


def _read_system_prompt() -> str:
    """Read the prompt template from disk. Fails loudly if file is missing."""
    if not _PROMPT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"BS agent prompt template not found at {_PROMPT_TEMPLATE_PATH}. "
            f"The prompt_template.md file must exist alongside agent.py."
        )
    return _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _build_user_message(
    entity_data: dict,
    entity_id: str,
    period_end: date,
    net_income: Decimal,
    ppa_schedule: dict | None,
    policy_doc: str | None,
    industry_profile: str | None,
) -> str:
    """Construct the user message for the LLM.

    Includes entity data as JSON, net income injection as literal text,
    optional PPA schedule, optional policy document with Layer 3 preamble,
    optional industry profile, and instruction to produce a balance sheet.
    """
    parts: list[str] = []

    # Entity data
    parts.append("## Entity Financial Data")
    parts.append(f"Entity ID: {entity_id}")
    parts.append(f"As of: {period_end.isoformat()}")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(entity_data, indent=2, default=str))
    parts.append("```")

    # Net income injection — LITERAL TEXT as required by spec
    parts.append("")
    parts.append("## Net Income (Immutable Fact from P&L Agent)")
    parts.append(
        f"Net income for the period ending {period_end.isoformat()} is "
        f"${net_income}. This is a validated fact produced by the P&L agent. "
        f"Do not recalculate. Do not verify. Consume this value directly "
        f"into retained earnings."
    )

    # PPA schedule (Convergence engagements)
    if ppa_schedule is not None:
        parts.append("")
        parts.append("## Purchase Price Allocation (PPA) Schedule")
        parts.append(
            "Apply the following fair value adjustments. Each adjustment "
            "must be reflected as an adjustment line item in the output."
        )
        parts.append("")
        parts.append("```json")
        parts.append(json.dumps(ppa_schedule, indent=2, default=str))
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
        f"Produce a complete balance sheet for entity {entity_id} as of "
        f"{period_end.isoformat()}. Output as JSON conforming to the "
        f"FinancialOutput schema. statement_type must be 'balance_sheet'. "
        f"period_start must be null. "
        f"Include all required fields: entity_id, period_end, "
        f"currency, line_items, journal_entries, and flags. "
        f"Use exact decimal values for all monetary amounts — no floating point. "
        f"Return ONLY the JSON object, no surrounding text or markdown."
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
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"BS agent LLM response is not valid JSON. "
            f"Response starts with: {response_text[:200]!r}. "
            f"JSON parse error: {e}"
        ) from e

    try:
        return FinancialOutput.model_validate(data)
    except Exception as e:
        raise ValueError(
            f"BS agent LLM response JSON does not conform to FinancialOutput schema. "
            f"Validation error: {e}"
        ) from e


async def run_bs_agent(
    entity_data: dict,
    entity_id: str,
    period_end: date,
    net_income: Decimal,
    ppa_schedule: dict | None,
    policy_doc: str | None,
    industry_profile: str | None,
    model: str = "claude-sonnet-4-20250514",
) -> BSResult:
    """Run the BS agent to produce a balance sheet.

    Calls the Anthropic API with the constitution prompt and entity data,
    injects net income as immutable fact, validates the output, runs
    equity roll-forward, and reprompts up to 3 times on validation failure.

    Args:
        entity_data: Financial data for the entity (accounts, balances).
        entity_id: Unique identifier for the entity.
        period_end: Balance sheet date (point-in-time).
        net_income: Net income from the P&L agent — immutable, exact Decimal.
        ppa_schedule: Optional purchase price allocation schedule (Convergence).
        policy_doc: Optional accounting policy document (Layer 3).
        industry_profile: Optional industry profile for context.
        model: Anthropic model to use.

    Returns:
        BSResult with the validated output or halt information.

    Raises:
        anthropic.APIError: If the Anthropic API call fails.
        FileNotFoundError: If the prompt template file is missing.
    """
    system_prompt = _read_system_prompt()

    user_message = _build_user_message(
        entity_data=entity_data,
        entity_id=entity_id,
        period_end=period_end,
        net_income=net_income,
        ppa_schedule=ppa_schedule,
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
            "Calling Anthropic API for BS agent — model=%s, entity=%s",
            model, entity_id,
        )

        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        if not response_text:
            raise ValueError(
                f"BS agent received empty response from Anthropic API. "
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
        flags.extend(validated_output.flags)

        # Run equity roll-forward validation
        beginning_equity = None
        dividends = None
        oci = None
        share_txn = None

        if "beginning_equity" in entity_data:
            be = entity_data["beginning_equity"]
            if "total" in be:
                beginning_equity = Decimal(str(be["total"]))

        if "dividends_declared" in entity_data:
            dividends = Decimal(str(entity_data["dividends_declared"]))

        if "other_comprehensive_income" in entity_data:
            oci = Decimal(str(entity_data["other_comprehensive_income"]))

        if "share_transactions" in entity_data:
            share_txn = Decimal(str(entity_data["share_transactions"]))

        equity_rf = validate_equity_rollforward_with_supplementary(
            bs_output=validated_output,
            injected_net_income=net_income,
            beginning_equity=beginning_equity,
            dividends=dividends,
            other_comprehensive_income=oci,
            share_transactions=share_txn,
        )

        # Add warning flag if roll-forward doesn't reconcile
        if not equity_rf.reconciles:
            flags.append(Flag(
                severity="warning",
                code="EQUITY_ROLLFORWARD_VARIANCE",
                message=(
                    f"Equity roll-forward does not reconcile. "
                    f"Expected ending equity based on beginning_equity="
                    f"{equity_rf.beginning_equity}, net_income={net_income}, "
                    f"dividends={equity_rf.dividends}, OCI={equity_rf.other_comprehensive_income}, "
                    f"share_txn={equity_rf.share_transactions}. "
                    f"Actual ending equity={equity_rf.ending_equity}. "
                    f"Variance={equity_rf.variance}."
                ),
                affected_accounts=["3200"],
            ))

        return BSResult(
            output=validated_output,
            halted=False,
            halt_reasons=[],
            validation_attempts=validation_attempts,
            flags=flags,
            equity_rollforward=equity_rf,
        )
    else:
        # All attempts failed
        halt_reasons: list[str] = []
        if validation_attempts:
            last_result = validation_attempts[-1]
            for error in last_result.errors:
                if error.severity == "halt":
                    halt_reasons.append(
                        f"[{error.rule_code}] {error.message}"
                    )

        return BSResult(
            output=None,
            halted=True,
            halt_reasons=halt_reasons,
            validation_attempts=validation_attempts,
            flags=flags,
            equity_rollforward=None,
        )
