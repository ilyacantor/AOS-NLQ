"""
Tests for the Maestra P&L Agent — Phase 2.

All tests mock the Anthropic API. No live LLM calls.
"""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.maestra.agents.pnl.agent import (
    PnLResult,
    _build_user_message,
    _parse_llm_response,
    _read_system_prompt,
    run_pnl_agent,
)
from src.maestra.agents.pnl.extract import extract_net_income
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


@pytest.fixture
def meridian_entity_data() -> dict:
    with open(FIXTURES_DIR / "meridian_entity_data.json") as f:
        return json.load(f)


@pytest.fixture
def meridian_coa() -> list[dict]:
    with open(FIXTURES_DIR / "meridian_coa.json") as f:
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
        "- Revenue recognition: ASC 606, subscription revenue recognized "
        "ratably over contract term.\n"
        "- Professional services revenue recognized as services are delivered "
        "(percentage of completion).\n"
        "- Hosting costs classified as COGS.\n"
        "- R&D costs expensed as incurred (no capitalized software development).\n"
        "- SBC measured at grant-date fair value, expensed over vesting period."
    )


def _make_valid_financial_output(
    entity_id: str = "meridian-001",
    period_start: str = "2025-01-01",
    period_end: str = "2025-12-31",
    net_income_amount: str = "800000000.00",
) -> dict:
    """Build a valid FinancialOutput dict that passes all validation rules."""
    return {
        "statement_type": "income_statement",
        "entity_id": entity_id,
        "period_start": period_start,
        "period_end": period_end,
        "currency": "USD",
        "line_items": [
            {
                "account_code": "4000",
                "account_name": "Subscription Revenue",
                "element": "revenue",
                "natural_balance": "credit",
                "amount": "3750000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "4100",
                "account_name": "Professional Services Revenue",
                "element": "revenue",
                "natural_balance": "credit",
                "amount": "625000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "4200",
                "account_name": "Licensing Revenue",
                "element": "revenue",
                "natural_balance": "credit",
                "amount": "625000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "5000",
                "account_name": "Hosting & Infrastructure COGS",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "750000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "5100",
                "account_name": "Professional Services COGS",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "375000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "6000",
                "account_name": "Sales & Marketing",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "1000000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "6100",
                "account_name": "Research & Development",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "875000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "6200",
                "account_name": "General & Administrative",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "375000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "6300",
                "account_name": "Stock-Based Compensation",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "250000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "6400",
                "account_name": "Depreciation & Amortization",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "187500000.00",
                "source": "entity_a",
            },
            {
                "account_code": "7000",
                "account_name": "Interest Expense",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "62500000.00",
                "source": "entity_a",
            },
            {
                "account_code": "8000",
                "account_name": "Income Tax Provision",
                "element": "expense",
                "natural_balance": "debit",
                "amount": "75000000.00",
                "source": "entity_a",
            },
            {
                "account_code": "9000",
                "account_name": "Net Income",
                "element": "revenue",
                "natural_balance": "credit",
                "amount": net_income_amount,
                "source": "entity_a",
            },
        ],
        "journal_entries": [
            {
                "entry_id": "JE-001",
                "description": "Record subscription revenue for FY2025",
                "lines": [
                    {
                        "account_code": "1000",
                        "element": "asset",
                        "debit": "3750000000.00",
                        "credit": "0",
                    },
                    {
                        "account_code": "4000",
                        "element": "revenue",
                        "debit": "0",
                        "credit": "3750000000.00",
                    },
                ],
            },
        ],
        "flags": [],
    }


def _make_unbalanced_financial_output() -> dict:
    """Build a FinancialOutput dict where journal DR != CR (fails V-001)."""
    output = _make_valid_financial_output()
    # Make journal entry unbalanced
    output["journal_entries"] = [
        {
            "entry_id": "JE-BAD",
            "description": "Unbalanced entry",
            "lines": [
                {
                    "account_code": "1000",
                    "element": "asset",
                    "debit": "1000000.00",
                    "credit": "0",
                },
                {
                    "account_code": "4000",
                    "element": "revenue",
                    "debit": "0",
                    "credit": "999000.00",
                },
            ],
        }
    ]
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


def test_pnl_single_entity_success(
    meridian_entity_data, saas_policy_doc, saas_industry_profile
):
    """Feed Meridian entity data + policy doc + SaaS profile.
    Verify valid FinancialOutput, statement_type=income_statement,
    net_income extracted as signed Decimal.
    """
    valid_output = _make_valid_financial_output()
    mock_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.pnl.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_pnl_agent(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            policy_doc=saas_policy_doc,
            industry_profile=saas_industry_profile,
        ))

    assert not result.halted, f"Agent halted unexpectedly: {result.halt_reasons}"
    assert result.output is not None
    assert result.output.statement_type == "income_statement"
    assert result.output.entity_id == "meridian-001"
    assert result.net_income is not None
    assert isinstance(result.net_income, Decimal)
    assert result.net_income == Decimal("800000000.00")
    # With policy doc provided, no MISSING_POLICY flag
    missing_policy_flags = [f for f in result.flags if f.code == "MISSING_POLICY"]
    assert len(missing_policy_flags) == 0


def test_pnl_no_policy_flags(meridian_entity_data):
    """No policy doc provided. Verify warning flags about missing policy."""
    valid_output = _make_valid_financial_output()
    mock_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.pnl.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_pnl_agent(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            policy_doc=None,
            industry_profile=None,
        ))

    assert not result.halted
    # Must have MISSING_POLICY warning flag
    missing_policy_flags = [f for f in result.flags if f.code == "MISSING_POLICY"]
    assert len(missing_policy_flags) == 1
    assert missing_policy_flags[0].severity == "warning"


def test_pnl_validation_catches_bad_output(meridian_entity_data):
    """Mock LLM returns DR != CR first time, valid second time.
    Verify reprompt fires and eventually succeeds.
    """
    bad_output = _make_unbalanced_financial_output()
    valid_output = _make_valid_financial_output()

    bad_response = _mock_anthropic_response(bad_output)
    good_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.pnl.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        # First call returns bad output, second returns valid
        mock_client.messages.create.side_effect = [bad_response, good_response]
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_pnl_agent(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            policy_doc="Standard GAAP policy.",
            industry_profile=None,
        ))

    assert not result.halted
    assert result.output is not None
    # Should have 2 validation attempts: first failed, second passed
    assert len(result.validation_attempts) == 2
    assert not result.validation_attempts[0].valid  # First attempt failed
    assert result.validation_attempts[1].valid  # Second attempt passed
    # First attempt should have V-001 error
    v001_errors = [
        e for e in result.validation_attempts[0].errors if e.rule_code == "V-001"
    ]
    assert len(v001_errors) > 0


def test_pnl_halt_on_persistent_failure(meridian_entity_data):
    """Mock LLM returns invalid output 3 times.
    Verify halted=True, net_income=None.
    """
    bad_output = _make_unbalanced_financial_output()
    bad_response = _mock_anthropic_response(bad_output)

    with patch("src.maestra.agents.pnl.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        # All 3 attempts return bad output
        mock_client.messages.create.return_value = bad_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_pnl_agent(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            policy_doc="Standard GAAP policy.",
            industry_profile=None,
        ))

    assert result.halted is True
    assert result.output is None
    assert result.net_income is None
    assert len(result.halt_reasons) > 0
    assert len(result.validation_attempts) == 3
    # All 3 attempts should have failed
    for attempt in result.validation_attempts:
        assert not attempt.valid


def test_pnl_stub_period(meridian_entity_data):
    """4-month stub period. Verify period dates correct, no annualization."""
    valid_output = _make_valid_financial_output(
        period_start="2025-09-01",
        period_end="2025-12-31",
    )
    mock_response = _mock_anthropic_response(valid_output)

    with patch("src.maestra.agents.pnl.agent.anthropic") as mock_anthropic_mod:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = _run(run_pnl_agent(
            entity_data=meridian_entity_data,
            entity_id="meridian-001",
            period_start=date(2025, 9, 1),
            period_end=date(2025, 12, 31),
            policy_doc="Standard GAAP policy.",
            industry_profile=None,
        ))

    assert not result.halted
    assert result.output is not None
    assert result.output.period_start == date(2025, 9, 1)
    assert result.output.period_end == date(2025, 12, 31)
    # Verify the amounts are NOT annualized — they match what the LLM returned
    # (the same nominal amounts, representing stub period actuals)
    sub_rev = next(
        (li for li in result.output.line_items if li.account_code == "4000"),
        None,
    )
    assert sub_rev is not None
    assert sub_rev.amount == Decimal("3750000000.00")


def test_net_income_extraction():
    """Valid FinancialOutput, verify net income extracted from named line item."""
    output = FinancialOutput(
        statement_type="income_statement",
        entity_id="test-001",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        currency="USD",
        line_items=[
            LineItem(
                account_code="4000",
                account_name="Revenue",
                element="revenue",
                natural_balance="credit",
                amount=Decimal("5000000000"),
                source="entity_a",
            ),
            LineItem(
                account_code="5000",
                account_name="Total Expenses",
                element="expense",
                natural_balance="debit",
                amount=Decimal("4200000000"),
                source="entity_a",
            ),
            LineItem(
                account_code="9000",
                account_name="Net Income",
                element="revenue",
                natural_balance="credit",
                amount=Decimal("800000000"),
                source="entity_a",
            ),
        ],
        journal_entries=[],
        flags=[],
    )

    net_income = extract_net_income(output)
    assert net_income is not None
    assert net_income == Decimal("800000000")
    assert isinstance(net_income, Decimal)


def test_net_income_loss():
    """Expenses > revenue. Verify negative net income via fallback calculation."""
    output = FinancialOutput(
        statement_type="income_statement",
        entity_id="test-002",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        currency="USD",
        line_items=[
            LineItem(
                account_code="4000",
                account_name="Total Revenue",
                element="revenue",
                natural_balance="credit",
                amount=Decimal("2000000000"),
                source="entity_a",
            ),
            LineItem(
                account_code="5000",
                account_name="Cost of Goods Sold",
                element="expense",
                natural_balance="debit",
                amount=Decimal("1500000000"),
                source="entity_a",
            ),
            LineItem(
                account_code="6000",
                account_name="Operating Expenses",
                element="expense",
                natural_balance="debit",
                amount=Decimal("1200000000"),
                source="entity_a",
            ),
        ],
        journal_entries=[],
        flags=[],
    )

    net_income = extract_net_income(output)
    assert net_income is not None
    assert isinstance(net_income, Decimal)
    # Revenue 2B - Expenses (1.5B + 1.2B) = -0.7B (loss)
    assert net_income == Decimal("-700000000")
    assert net_income < 0  # Confirms it's a loss
