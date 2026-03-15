"""
Tests for the Maestra BS Agent — Phase 3.

All tests mock the Anthropic API. No live LLM calls.
"""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.maestra.agents.bs.agent import (
    BSResult,
    _build_user_message,
    _parse_llm_response,
    _read_system_prompt,
    run_bs_agent,
)
from src.maestra.agents.bs.rollforward import (
    EquityRollforward,
    validate_equity_rollforward,
    validate_equity_rollforward_with_supplementary,
)
from src.maestra.validation.schema import (
    FinancialOutput,
    Flag,
    JournalEntry,
    JournalLine,
    LineItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "fixtures"

INJECTED_NET_INCOME = Decimal("800000000.00")


@pytest.fixture
def meridian_bs_entity_data() -> dict:
    with open(FIXTURES_DIR / "meridian_bs_entity_data.json") as f:
        return json.load(f)


@pytest.fixture
def saas_industry_profile() -> str:
    return (
        "SaaS / Enterprise Software. Revenue is primarily recurring "
        "subscription-based with ASC 606 multi-element arrangements. "
        "Typical gross margins 70-80%. High R&D spend (15-25% of revenue). "
        "Stock-based compensation is a material non-cash expense."
    )


@pytest.fixture
def saas_policy_doc() -> str:
    return (
        "Meridian Software Inc. Accounting Policy:\n"
        "- Capitalized software costs amortized over 3 years.\n"
        "- Operating leases under ASC 842 with ROU assets and lease liabilities.\n"
        "- Deferred revenue recognized as performance obligations are met.\n"
        "- Goodwill tested annually for impairment."
    )


def _make_valid_bs_output(
    entity_id: str = "meridian-001",
    period_end: str = "2025-12-31",
    retained_earnings: str = "2000000000.00",
) -> dict:
    """Build a valid BS FinancialOutput dict that passes all validation rules.

    Total assets = 6,250M. Total liabilities = 2,750M. Total equity = 3,500M.
    A = L + E.
    """
    return {
        "statement_type": "balance_sheet",
        "entity_id": entity_id,
        "period_end": period_end,
        "period_start": None,
        "currency": "USD",
        "line_items": [
            # Assets
            {
                "account_code": "1100",
                "account_name": "Cash & Cash Equivalents",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "2400000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1200",
                "account_name": "Accounts Receivable, Net",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "850000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1300",
                "account_name": "Prepaid Expenses",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "150000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1400",
                "account_name": "Capitalized Software Development Costs, Net",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "625000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1500",
                "account_name": "Property, Plant & Equipment, Net",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "400000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1600",
                "account_name": "Operating Lease Right-of-Use Assets",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "325000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1700",
                "account_name": "Goodwill",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "1200000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "1800",
                "account_name": "Other Intangible Assets, Net",
                "element": "asset",
                "natural_balance": "debit",
                "amount": "300000000.00",
                "source": "entity_a",
            },
            # Liabilities
            {
                "account_code": "2000",
                "account_name": "Accounts Payable",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "275000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2100",
                "account_name": "Accrued Liabilities",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "450000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2200",
                "account_name": "Deferred Revenue — Current",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "750000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2300",
                "account_name": "Current Operating Lease Liabilities",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "80000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2400",
                "account_name": "Long-Term Debt",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "600000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2500",
                "account_name": "Deferred Revenue — Non-Current",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "225000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2600",
                "account_name": "Non-Current Operating Lease Liabilities",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "245000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "2700",
                "account_name": "Deferred Tax Liabilities",
                "element": "liability",
                "natural_balance": "credit",
                "amount": "125000000.00",
                "source": "entity_a",
            },
            # Equity
            {
                "account_code": "3000",
                "account_name": "Common Stock",
                "element": "equity",
                "natural_balance": "credit",
                "amount": "10000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "3100",
                "account_name": "Additional Paid-in Capital",
                "element": "equity",
                "natural_balance": "credit",
                "amount": "1490000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "3200",
                "account_name": "Retained Earnings",
                "element": "equity",
                "natural_balance": "credit",
                "amount": retained_earnings,
                "source": "entity_a",
            },
        ],
        "journal_entries": [
            {
                "entry_id": "JE-BS-001",
                "description": "Record cash position as of 2025-12-31",
                "lines": [
                    {
                        "account_code": "1100",
                        "element": "asset",
                        "debit": "2400000000.00",
                        "credit": "0",
                    },
                    {
                        "account_code": "3200",
                        "element": "equity",
                        "debit": "0",
                        "credit": "2400000000.00",
                    },
                ],
            },
        ],
        "flags": [],
    }


def _make_imbalanced_bs_output() -> dict:
    """Build a BS output where A != L + E (fails V-003)."""
    output = _make_valid_bs_output()
    # Tamper with cash to break the equation
    output["line_items"][0]["amount"] = "9999999999.00"
    return output


def _mock_anthropic_response(output_dict: dict) -> MagicMock:
    """Create a mock Anthropic API response containing the given output JSON."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(output_dict)

    response = MagicMock()
    response.content = [text_block]
    response.stop_reason = "end_turn"
    return response


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bs_single_entity_success(
    meridian_bs_entity_data, saas_policy_doc, saas_industry_profile
):
    """Feed Meridian BS data with injected net income.
    Verify: valid FinancialOutput, statement_type=balance_sheet,
    period_start is None, A=L+E.
    """
    valid_output = _make_valid_bs_output()
    mock_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.bs.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_bs_agent(
            entity_data=meridian_bs_entity_data,
            entity_id="meridian-001",
            period_end=date(2025, 12, 31),
            net_income=INJECTED_NET_INCOME,
            ppa_schedule=None,
            policy_doc=saas_policy_doc,
            industry_profile=saas_industry_profile,
        ))

    assert not result.halted, f"Agent halted unexpectedly: {result.halt_reasons}"
    assert result.output is not None
    assert result.output.statement_type == "balance_sheet"
    assert result.output.entity_id == "meridian-001"
    assert result.output.period_start is None

    # Verify A = L + E
    assets = sum(
        Decimal(str(li.amount)) for li in result.output.line_items if li.element == "asset"
    )
    liabilities = sum(
        Decimal(str(li.amount)) for li in result.output.line_items if li.element == "liability"
    )
    equity = sum(
        Decimal(str(li.amount)) for li in result.output.line_items if li.element == "equity"
    )
    assert assets == liabilities + equity, (
        f"A={assets} != L+E={liabilities + equity}"
    )


def test_bs_net_income_consumed_not_recalculated(meridian_bs_entity_data):
    """Verify the BS output's retained earnings change equals the injected net income.

    Retained earnings in fixture: ending=2,000M, beginning=1,200M.
    Change = 800M = injected net income.
    """
    valid_output = _make_valid_bs_output()
    mock_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.bs.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_bs_agent(
            entity_data=meridian_bs_entity_data,
            entity_id="meridian-001",
            period_end=date(2025, 12, 31),
            net_income=INJECTED_NET_INCOME,
            ppa_schedule=None,
            policy_doc="Standard GAAP policy.",
            industry_profile=None,
        ))

    assert not result.halted
    assert result.equity_rollforward is not None
    # The injected net income must appear exactly in the roll-forward
    assert result.equity_rollforward.net_income == INJECTED_NET_INCOME

    # Verify retained earnings in the output
    re_items = [
        li for li in result.output.line_items
        if "retained earnings" in li.account_name.lower()
    ]
    assert len(re_items) == 1
    ending_re = re_items[0].amount
    beginning_re = Decimal("1200000000.00")  # from fixture
    assert ending_re - beginning_re == INJECTED_NET_INCOME


def test_equity_rollforward_reconciles():
    """Feed valid data where roll-forward reconciles.

    Beginning equity = 2,700M. Net income = 800M. No dividends/OCI/shares.
    Ending equity = 3,500M. Should reconcile.
    """
    bs_output = FinancialOutput.model_validate(_make_valid_bs_output())

    rf = validate_equity_rollforward_with_supplementary(
        bs_output=bs_output,
        injected_net_income=INJECTED_NET_INCOME,
        beginning_equity=Decimal("2700000000.00"),
        dividends=Decimal("0"),
        other_comprehensive_income=Decimal("0"),
        share_transactions=Decimal("0"),
    )

    assert rf.reconciles is True
    assert rf.variance is None
    assert rf.net_income == INJECTED_NET_INCOME
    assert rf.ending_equity == Decimal("3500000000.00")
    assert rf.beginning_equity == Decimal("2700000000.00")


def test_equity_rollforward_variance():
    """Feed data where roll-forward doesn't reconcile — verify variance is reported.

    Beginning equity = 2,700M. Net income = 800M. Expected ending = 3,500M.
    But we'll set retained earnings to 2,100M (equity = 3,600M) to create a 100M variance.
    """
    bs_output_dict = _make_valid_bs_output(retained_earnings="2100000000.00")
    bs_output = FinancialOutput.model_validate(bs_output_dict)

    # Ending equity with RE=2,100M: CS 10M + APIC 1,490M + RE 2,100M = 3,600M
    rf = validate_equity_rollforward_with_supplementary(
        bs_output=bs_output,
        injected_net_income=INJECTED_NET_INCOME,
        beginning_equity=Decimal("2700000000.00"),
        dividends=Decimal("0"),
        other_comprehensive_income=Decimal("0"),
        share_transactions=Decimal("0"),
    )

    assert rf.reconciles is False
    assert rf.variance is not None
    # Expected: 2,700M + 800M = 3,500M. Actual: 3,600M. Variance: 100M.
    assert rf.variance == Decimal("100000000.00")


def test_bs_validation_catches_imbalance(meridian_bs_entity_data):
    """Mock LLM to return A!=L+E. Verify reprompt fires."""
    bad_output = _make_imbalanced_bs_output()
    valid_output = _make_valid_bs_output()

    bad_response = _mock_anthropic_response(bad_output)
    good_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.bs.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [bad_response, good_response]
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_bs_agent(
            entity_data=meridian_bs_entity_data,
            entity_id="meridian-001",
            period_end=date(2025, 12, 31),
            net_income=INJECTED_NET_INCOME,
            ppa_schedule=None,
            policy_doc="Standard GAAP policy.",
            industry_profile=None,
        ))

    assert not result.halted
    assert result.output is not None
    # Should have 2 validation attempts: first failed (V-003), second passed
    assert len(result.validation_attempts) == 2
    assert not result.validation_attempts[0].valid
    assert result.validation_attempts[1].valid
    # First attempt should have V-003 error (accounting equation)
    v003_errors = [
        e for e in result.validation_attempts[0].errors if e.rule_code == "V-003"
    ]
    assert len(v003_errors) > 0
