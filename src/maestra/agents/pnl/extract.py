"""
Maestra P&L Agent — Net income extraction from FinancialOutput.

Extracts net income from a validated income statement. Uses two strategies:
1. Direct: find line item named "net income" (case-insensitive)
2. Fallback: sum(revenue) - sum(expense) amounts

Returns signed Decimal. Positive = profit, negative = loss.
Returns None if neither approach works.
"""

from decimal import Decimal

from src.maestra.validation.schema import FinancialOutput


def extract_net_income(output: FinancialOutput) -> Decimal | None:
    """Extract net income from a validated FinancialOutput.

    Strategy 1: Find a line item whose account_name contains "net income"
    (case-insensitive). If found, return its amount directly.

    Strategy 2 (fallback): Sum all revenue line item amounts and subtract
    all expense line item amounts. Revenue is credit-natural (positive =
    income earned), expenses are debit-natural (positive = cost incurred).
    Result: revenue_total - expense_total. Positive = profit, negative = loss.

    Returns:
        Signed Decimal, or None if no revenue or expense data exists.
    """
    # Strategy 1: Direct extraction from named line item
    for item in output.line_items:
        if "net income" in item.account_name.lower():
            return item.amount

    # Strategy 2: Compute from revenue - expenses
    revenue_total = Decimal("0")
    expense_total = Decimal("0")
    has_revenue = False
    has_expense = False

    for item in output.line_items:
        if item.element == "revenue":
            revenue_total += item.amount
            has_revenue = True
        elif item.element == "expense":
            expense_total += item.amount
            has_expense = True

    if not has_revenue and not has_expense:
        return None

    # Revenue amounts are positive (income earned).
    # Expense amounts are positive (cost incurred).
    # Net income = revenue - expenses.
    return revenue_total - expense_total
