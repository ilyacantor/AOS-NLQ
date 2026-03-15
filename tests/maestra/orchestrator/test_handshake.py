"""
Tests for the Maestra Handshake Orchestrator — Phase 3.

All tests mock the Anthropic API. No live LLM calls.
"""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maestra.agents.bs.agent import BSResult
from src.maestra.agents.pnl.agent import PnLResult
from src.maestra.orchestrator.handshake import (
    FinancialStatementResult,
    run_financial_statements,
)
from src.maestra.agents.bs.rollforward import EquityRollforward
from src.maestra.validation.schema import (
    FinancialOutput,
    Flag,
    LineItem,
    ValidationError,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"

NET_INCOME = Decimal("800000000.00")


def _stub_pnl_output() -> FinancialOutput:
    """Minimal valid income statement FinancialOutput for test stubs."""
    return FinancialOutput(
        statement_type="income_statement",
        entity_id="meridian-001",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        currency="USD",
        line_items=[
            LineItem(
                account_code="4000", account_name="Revenue",
                element="revenue", natural_balance="credit",
                amount=Decimal("5000000000"), source="entity_a",
            ),
            LineItem(
                account_code="5000", account_name="Expenses",
                element="expense", natural_balance="debit",
                amount=Decimal("4200000000"), source="entity_a",
            ),
        ],
        journal_entries=[],
        flags=[],
    )


def _stub_bs_output() -> FinancialOutput:
    """Minimal valid balance sheet FinancialOutput for test stubs."""
    return FinancialOutput(
        statement_type="balance_sheet",
        entity_id="meridian-001",
        period_end=date(2025, 12, 31),
        period_start=None,
        currency="USD",
        line_items=[
            LineItem(
                account_code="1100", account_name="Cash",
                element="asset", natural_balance="debit",
                amount=Decimal("6250000000"), source="entity_a",
            ),
            LineItem(
                account_code="2000", account_name="Liabilities",
                element="liability", natural_balance="credit",
                amount=Decimal("2750000000"), source="entity_a",
            ),
            LineItem(
                account_code="3200", account_name="Retained Earnings",
                element="equity", natural_balance="credit",
                amount=Decimal("3500000000"), source="entity_a",
            ),
        ],
        journal_entries=[],
        flags=[],
    )


@pytest.fixture
def meridian_entity_data() -> dict:
    """Combined entity data that works for both P&L and BS agents."""
    with open(FIXTURES_DIR / "meridian_entity_data.json") as f:
        pnl_data = json.load(f)
    with open(FIXTURES_DIR / "meridian_bs_entity_data.json") as f:
        bs_data = json.load(f)
    # Merge — the handshake passes the same entity_data to both agents
    merged = {**pnl_data, **bs_data}
    # Combine chart_of_accounts
    coa_codes = set()
    combined_coa = []
    for entry in pnl_data.get("chart_of_accounts", []) + bs_data.get("chart_of_accounts", []):
        if entry["account_code"] not in coa_codes:
            coa_codes.add(entry["account_code"])
            combined_coa.append(entry)
    merged["chart_of_accounts"] = combined_coa
    return merged


def _make_successful_pnl_result() -> PnLResult:
    return PnLResult(
        output=_stub_pnl_output(),
        net_income=NET_INCOME,
        halted=False,
        halt_reasons=[],
        validation_attempts=[ValidationResult(valid=True, errors=[])],
        flags=[
            Flag(
                severity="warning",
                code="PNL_FLAG_1",
                message="P&L warning flag for testing",
                affected_accounts=["4000"],
            ),
        ],
    )


def _make_halted_pnl_result() -> PnLResult:
    return PnLResult(
        output=None,
        net_income=None,
        halted=True,
        halt_reasons=["[V-001] Journal entry unbalanced"],
        validation_attempts=[
            ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        rule_code="V-001",
                        message="Journal entry unbalanced",
                        severity="halt",
                        failing_data={"entry_id": "JE-001"},
                    ),
                ],
            ),
        ],
        flags=[],
    )


def _make_null_net_income_pnl_result() -> PnLResult:
    return PnLResult(
        output=_stub_pnl_output(),
        net_income=None,
        halted=False,
        halt_reasons=[],
        validation_attempts=[ValidationResult(valid=True, errors=[])],
        flags=[],
    )


def _make_successful_bs_result() -> BSResult:
    return BSResult(
        output=_stub_bs_output(),
        halted=False,
        halt_reasons=[],
        validation_attempts=[ValidationResult(valid=True, errors=[])],
        flags=[
            Flag(
                severity="warning",
                code="BS_FLAG_1",
                message="BS warning flag for testing",
                affected_accounts=["3200"],
            ),
        ],
        equity_rollforward=EquityRollforward(
            beginning_equity=Decimal("2700000000"),
            net_income=NET_INCOME,
            dividends=Decimal("0"),
            other_comprehensive_income=Decimal("0"),
            share_transactions=Decimal("0"),
            ending_equity=Decimal("3500000000"),
            reconciles=True,
            variance=None,
        ),
    )


def _make_halted_bs_result() -> BSResult:
    return BSResult(
        output=None,
        halted=True,
        halt_reasons=["[V-003] Balance sheet doesn't balance"],
        validation_attempts=[
            ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        rule_code="V-003",
                        message="Balance sheet doesn't balance",
                        severity="halt",
                        failing_data={"assets": "100", "liabilities": "50", "equity": "40"},
                    ),
                ],
            ),
        ] * 3,
        flags=[
            Flag(
                severity="halt",
                code="BS_HALT_FLAG",
                message="BS halted due to persistent imbalance",
                affected_accounts=[],
            ),
        ],
        equity_rollforward=None,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_handshake_full_success(meridian_entity_data):
    """P&L succeeds → net income extracted → BS succeeds → handshake_passed=True."""
    pnl_result = _make_successful_pnl_result()
    bs_result = _make_successful_bs_result()

    with patch(
        "src.maestra.orchestrator.handshake.run_pnl_agent",
        new_callable=AsyncMock,
        return_value=pnl_result,
    ), patch(
        "src.maestra.orchestrator.handshake.run_bs_agent",
        new_callable=AsyncMock,
        return_value=bs_result,
    ) as mock_bs:
        result = _run(run_financial_statements(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ))

    assert result.handshake_passed is True
    assert result.pnl_result is pnl_result
    assert result.bs_result is bs_result
    assert result.net_income_handshake == NET_INCOME

    # BS agent should have been called with the P&L's net income
    mock_bs.assert_called_once()
    call_kwargs = mock_bs.call_args.kwargs
    assert call_kwargs["net_income"] == NET_INCOME


def test_handshake_pnl_halts(meridian_entity_data):
    """P&L halts. Verify: BS never runs, bs_result is None, handshake_passed=False."""
    pnl_result = _make_halted_pnl_result()

    with patch(
        "src.maestra.orchestrator.handshake.run_pnl_agent",
        new_callable=AsyncMock,
        return_value=pnl_result,
    ), patch(
        "src.maestra.orchestrator.handshake.run_bs_agent",
        new_callable=AsyncMock,
    ) as mock_bs:
        result = _run(run_financial_statements(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ))

    assert result.handshake_passed is False
    assert result.bs_result is None
    assert result.net_income_handshake is None
    mock_bs.assert_not_called()


def test_handshake_pnl_null_net_income(meridian_entity_data):
    """P&L returns valid output but null net income. Verify: BS never runs."""
    pnl_result = _make_null_net_income_pnl_result()

    with patch(
        "src.maestra.orchestrator.handshake.run_pnl_agent",
        new_callable=AsyncMock,
        return_value=pnl_result,
    ), patch(
        "src.maestra.orchestrator.handshake.run_bs_agent",
        new_callable=AsyncMock,
    ) as mock_bs:
        result = _run(run_financial_statements(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ))

    assert result.handshake_passed is False
    assert result.bs_result is None
    assert result.net_income_handshake is None
    mock_bs.assert_not_called()


def test_handshake_bs_halts(meridian_entity_data):
    """P&L succeeds but BS fails validation 3 times.
    Verify: pnl_result is valid, bs_result is halted.
    """
    pnl_result = _make_successful_pnl_result()
    bs_result = _make_halted_bs_result()

    with patch(
        "src.maestra.orchestrator.handshake.run_pnl_agent",
        new_callable=AsyncMock,
        return_value=pnl_result,
    ), patch(
        "src.maestra.orchestrator.handshake.run_bs_agent",
        new_callable=AsyncMock,
        return_value=bs_result,
    ):
        result = _run(run_financial_statements(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ))

    assert result.handshake_passed is False
    assert result.pnl_result is pnl_result
    assert not result.pnl_result.halted
    assert result.bs_result is bs_result
    assert result.bs_result.halted
    assert result.net_income_handshake == NET_INCOME


def test_handshake_combined_flags(meridian_entity_data):
    """Both agents produce flags. Verify combined_flags contains all of them,
    halt-severity first.
    """
    pnl_result = _make_successful_pnl_result()
    # Add a halt-level flag to PnL for sorting verification
    pnl_result.flags.append(Flag(
        severity="halt",
        code="PNL_HALT_FLAG",
        message="P&L halt flag for testing",
        affected_accounts=[],
    ))

    bs_result = _make_successful_bs_result()
    # Add another warning to BS
    bs_result.flags.append(Flag(
        severity="warning",
        code="BS_FLAG_2",
        message="Second BS warning",
        affected_accounts=["2200"],
    ))

    with patch(
        "src.maestra.orchestrator.handshake.run_pnl_agent",
        new_callable=AsyncMock,
        return_value=pnl_result,
    ), patch(
        "src.maestra.orchestrator.handshake.run_bs_agent",
        new_callable=AsyncMock,
        return_value=bs_result,
    ):
        result = _run(run_financial_statements(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
        ))

    # Should have all flags from both agents
    all_codes = {f.code for f in result.combined_flags}
    assert "PNL_FLAG_1" in all_codes
    assert "PNL_HALT_FLAG" in all_codes
    assert "BS_FLAG_1" in all_codes
    assert "BS_FLAG_2" in all_codes

    # Halt-severity flags must come first
    halt_indices = [
        i for i, f in enumerate(result.combined_flags) if f.severity == "halt"
    ]
    warning_indices = [
        i for i, f in enumerate(result.combined_flags) if f.severity == "warning"
    ]
    if halt_indices and warning_indices:
        assert max(halt_indices) < min(warning_indices), (
            "Halt flags must precede warning flags in combined_flags"
        )
