"""
Maestra Handshake Orchestrator — Phase 3.

Ties the P&L agent to the BS agent. The P&L agent runs first, produces
a validated net income, and the BS agent consumes that number as an
immutable fact. If the P&L agent halts, the BS agent never runs.

This is the ONLY place that connects P&L to BS. The BS agent has no
knowledge of or access to the P&L agent.
"""

import logging
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from src.maestra.agents.bs.agent import BSResult, run_bs_agent
from src.maestra.agents.pnl.agent import PnLResult, run_pnl_agent
from src.maestra.validation.schema import Flag

logger = logging.getLogger(__name__)


class FinancialStatementResult(BaseModel):
    """Combined result of P&L + BS agent execution.

    Attributes:
        pnl_result: The P&L agent result (always present).
        bs_result: The BS agent result, or None if the P&L agent halted.
        handshake_passed: True only if both agents succeeded without halting.
        combined_flags: All flags from both agents, deduplicated, halt-severity first.
        net_income_handshake: The net income value passed from P&L to BS, or None if P&L halted.
    """

    pnl_result: PnLResult
    bs_result: BSResult | None
    handshake_passed: bool
    combined_flags: list[Flag]
    net_income_handshake: Decimal | None


def _combine_flags(pnl_flags: list[Flag], bs_flags: list[Flag]) -> list[Flag]:
    """Combine and deduplicate flags from both agents, ordered by severity.

    Halt-severity flags come first, then warnings. Within each severity
    group, P&L flags precede BS flags. Deduplication is by (code, message).
    """
    seen: set[tuple[str, str]] = set()
    combined: list[Flag] = []

    all_flags = pnl_flags + bs_flags

    # Halt flags first
    for flag in all_flags:
        key = (flag.code, flag.message)
        if key not in seen and flag.severity == "halt":
            seen.add(key)
            combined.append(flag)

    # Then warning flags
    for flag in all_flags:
        key = (flag.code, flag.message)
        if key not in seen and flag.severity == "warning":
            seen.add(key)
            combined.append(flag)

    return combined


async def run_financial_statements(
    entity_data: dict,
    entity_id: str,
    period_start: date,
    period_end: date,
    policy_doc: str | None = None,
    industry_profile: str | None = None,
    ppa_schedule: dict | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> FinancialStatementResult:
    """Run P&L and BS agents in sequence with handshake.

    1. Run the P&L agent.
    2. If P&L halts or produces no net income: return immediately, BS never runs.
    3. Run the BS agent with the P&L's net income.
    4. Return combined result.

    Args:
        entity_data: Financial data for the entity.
        entity_id: Unique identifier for the entity.
        period_start: Start of the P&L reporting period.
        period_end: End of the reporting period (also the BS date).
        policy_doc: Optional accounting policy document (Layer 3).
        industry_profile: Optional industry profile for context.
        ppa_schedule: Optional purchase price allocation schedule (Convergence).
        model: Anthropic model to use for both agents.

    Returns:
        FinancialStatementResult with combined results from both agents.
    """
    # Step 1: Run P&L agent
    logger.info(
        "Handshake: starting P&L agent for entity=%s, period=%s to %s",
        entity_id, period_start, period_end,
    )

    pnl_result = await run_pnl_agent(
        entity_data=entity_data,
        entity_id=entity_id,
        period_start=period_start,
        period_end=period_end,
        policy_doc=policy_doc,
        industry_profile=industry_profile,
        model=model,
    )

    # Step 2: Check P&L result — halt propagation
    if pnl_result.halted:
        halt_msg = (
            f"P&L agent halted. BS agent not invoked. "
            f"Reasons: {pnl_result.halt_reasons}"
        )
        logger.warning("Handshake: %s", halt_msg)

        return FinancialStatementResult(
            pnl_result=pnl_result,
            bs_result=None,
            handshake_passed=False,
            combined_flags=_combine_flags(pnl_result.flags, []),
            net_income_handshake=None,
        )

    if pnl_result.net_income is None:
        halt_msg = (
            "P&L agent succeeded but produced null net income. "
            "BS agent not invoked — net income is required for the handshake."
        )
        logger.warning("Handshake: %s", halt_msg)

        return FinancialStatementResult(
            pnl_result=pnl_result,
            bs_result=None,
            handshake_passed=False,
            combined_flags=_combine_flags(pnl_result.flags, []),
            net_income_handshake=None,
        )

    # Step 3: Run BS agent with net income from P&L
    net_income = pnl_result.net_income

    logger.info(
        "Handshake: P&L succeeded with net_income=%s. Starting BS agent.",
        net_income,
    )

    bs_result = await run_bs_agent(
        entity_data=entity_data,
        entity_id=entity_id,
        period_end=period_end,
        net_income=net_income,
        ppa_schedule=ppa_schedule,
        policy_doc=policy_doc,
        industry_profile=industry_profile,
        model=model,
    )

    # Step 4: Combine results
    handshake_passed = not pnl_result.halted and not bs_result.halted
    combined_flags = _combine_flags(pnl_result.flags, bs_result.flags)

    logger.info(
        "Handshake: complete. handshake_passed=%s, total_flags=%d",
        handshake_passed, len(combined_flags),
    )

    return FinancialStatementResult(
        pnl_result=pnl_result,
        bs_result=bs_result,
        handshake_passed=handshake_passed,
        combined_flags=combined_flags,
        net_income_handshake=net_income,
    )
