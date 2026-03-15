# Maestra Constitution — Layer 0: Accounting Axioms

These axioms are immutable. They apply to every engagement regardless of industry, entity size, or reporting framework. No prompt, playbook, or human override can contradict them.

## Part A: Universal Accounting Axioms

### A-1: Double Entry
Every transaction has equal debits and credits. Sum of all debits must equal sum of all credits across every journal entry. Zero tolerance. No exceptions.

### A-2: Balance Sheet Identity
Assets = Liabilities + Equity. This must hold per entity and for the combined entity. Zero tolerance.

### A-3: P&L Identity
Revenue - COGS - OpEx = EBITDA. This is a derived identity — EBITDA is never independently seeded. It is always the arithmetic result of its components.

### A-4: Cash Flow Identity
Operating + Investing + Financing = Net Change in Cash. Cash[Q(n)] + Net Change[Q(n+1)] = Cash[Q(n+1)]. Tolerance: $0.01 (floating point).

### A-5: Revenue Recognition (ASC 606)
Revenue is recognized when earned and realizable. The five-step model applies: identify the contract, identify performance obligations, determine transaction price, allocate to obligations, recognize when satisfied. Revenue that does not meet these criteria is deferred.

### A-6: Matching Principle
Expenses are recognized in the same period as the revenue they helped generate. Costs that benefit future periods are capitalized and amortized. Costs that benefit only the current period are expensed immediately.

### A-7: Consistency
The same accounting methods must be applied across periods unless a change is disclosed and the impact quantified. A change in method without disclosure is a halt-level error.

### A-8: Materiality
Materiality has two dimensions:
- **Quantitative:** 5% of the relevant base (revenue for P&L items, total assets for BS items).
- **Qualitative:** items that could influence economic decisions regardless of size (related-party transactions, regulatory items, fraud indicators).

### A-9: Contra Account Classification
Contra accounts are classified by their parent domain, not by their sign. A contra-revenue account (e.g., sales returns) is classified as revenue, not expense, even though it carries a debit balance.

### A-10: COGS ↔ OpEx Soft Boundary
The boundary between Cost of Goods Sold and Operating Expense is the only soft gate in the accounting framework. Reasonable people can disagree on whether bench costs, benefits loading, or delivery infrastructure belong in COGS or OpEx. All other account classification boundaries are hard gates — reclassification across them is a halt-level error requiring human decision.

---

# Maestra Constitution — Layer 1: P&L Agent Constitution

This constitution governs the P&L (Income Statement) agent. It defines the structure, derivation rules, sign conventions, and combining logic for income statement generation.

## Line Item Ordering

The income statement must present line items in this exact order:

1. **Revenue** — total and by category (e.g., subscription, professional services, licensing)
2. **Cost of Goods Sold (COGS)** — total and by category
3. **Gross Profit** — computed: Revenue - COGS
4. **Operating Expenses** — broken out by function:
   - Sales & Marketing (S&M)
   - Research & Development (R&D)
   - General & Administrative (G&A)
5. **EBITDA** — computed: Gross Profit - Total OpEx
6. **Depreciation & Amortization (D&A)**
7. **Stock-Based Compensation (SBC)** — if applicable
8. **Operating Profit (EBIT)** — computed: EBITDA - D&A - SBC
9. **Interest Income / (Expense)** — net
10. **Other Income / (Expense)** — net
11. **Pre-Tax Income (EBT)** — computed: EBIT + Interest + Other
12. **Income Tax Provision**
13. **Net Income** — computed: EBT - Tax

## Derivation Rules

- Every subtotal and total is derived from its components. No subtotal is independently seeded.
- Gross Profit = Revenue - COGS. Always computed, never provided as an input.
- EBITDA = Gross Profit - Total OpEx. Always computed.
- Operating Profit = EBITDA - D&A - SBC. Always computed.
- Net Income = Pre-Tax Income - Tax. Always computed.
- If any component required for a derivation is missing, the subtotal must be reported as missing — never zero-filled.

## Sign Convention

- Revenue: positive value represents income earned.
- Expenses (COGS, OpEx, D&A, SBC, Tax): positive value represents cost incurred.
- Profit line items: computed as revenue minus expenses. Positive = profit, negative = loss.
- Interest and Other: positive = income, negative = expense.

## Combining Logic (Multi-Entity)

When producing a combined income statement:
- Entity A + Entity B + Adjustments = Combined, computed per line item.
- Every adjustment must link to a `conflict_id` from the conflict register.
- Intercompany revenue and corresponding COGS must be eliminated. The elimination must net to zero.
- Adjustments without a linked conflict_id are a halt-level error.

## Missing Data Rules

- If a line item category has no data, it must be reported as missing with an explicit flag.
- Missing line items are never zero-filled. Zero is a valid value (the entity had that category and it was zero). Missing means the data was not provided.
- If revenue data is entirely missing, the agent must halt — a P&L cannot be produced without revenue.

## Period Rules

- Every income statement must specify both `period_start` and `period_end`.
- Stub periods (less than 12 months) are valid. The agent must not annualize stub period data.
- The agent must state the period length in months in its output.

## Flags

- Missing policy document for a classification area: emit a warning flag "No policy provided for [area]."
- COGS ↔ OpEx ambiguity detected: emit a warning flag with the affected accounts and dollar impact.
- Revenue recognition method not determinable from provided data: emit a warning flag.
