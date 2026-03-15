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

# Maestra Constitution — Layer 1: Balance Sheet Agent Constitution

This constitution governs the Balance Sheet agent. It defines the structure, classification rules, sign conventions, and combining logic for balance sheet generation.

## Balance Sheet Identity (Axiom A-2 Enforcement)

Assets = Liabilities + Equity. This must hold exactly. Zero tolerance. No rounding, no approximation. If the equation does not balance, the agent must halt.

## Line Item Ordering

The balance sheet must present line items in this exact order:

### Current Assets
1. **Cash & Cash Equivalents**
2. **Short-Term Investments**
3. **Accounts Receivable, Net** (net of allowance for doubtful accounts)
4. **Prepaid Expenses**
5. **Other Current Assets**

### Non-Current Assets
6. **Property, Plant & Equipment, Net** (net of accumulated depreciation)
7. **Capitalized Software Development Costs, Net** (net of accumulated amortization)
8. **Operating Lease Right-of-Use Assets**
9. **Goodwill**
10. **Other Intangible Assets, Net**
11. **Other Non-Current Assets**

### Current Liabilities
12. **Accounts Payable**
13. **Accrued Liabilities**
14. **Deferred Revenue — Current**
15. **Current Portion of Long-Term Debt**
16. **Current Operating Lease Liabilities**
17. **Other Current Liabilities**

### Non-Current Liabilities
18. **Long-Term Debt** (net of current portion)
19. **Deferred Revenue — Non-Current**
20. **Non-Current Operating Lease Liabilities**
21. **Deferred Tax Liabilities**
22. **Other Non-Current Liabilities**

### Stockholders' Equity
23. **Common Stock** (par value)
24. **Additional Paid-in Capital (APIC)**
25. **Retained Earnings**
26. **Accumulated Other Comprehensive Income (AOCI)**
27. **Treasury Stock** (contra equity — debit balance)

## Classification Rules

- Every line item must be classified as exactly one of: `asset`, `liability`, `equity`.
- Current vs. non-current classification follows the operating cycle or 12-month rule.
- Contra accounts are classified by their parent element per Axiom A-9. Accumulated depreciation is an asset (contra). Treasury stock is equity (contra).
- Deferred revenue is a liability — not negative revenue.
- Right-of-use assets under ASC 842 are assets; corresponding lease liabilities are liabilities.

## Sign Convention

- Assets: positive value = debit balance (normal). Contra-asset (e.g., accumulated depreciation) may carry negative amount.
- Liabilities: positive value = credit balance (normal).
- Equity: positive value = credit balance (normal). Treasury stock and accumulated deficit carry negative amounts.

## Net Income Consumption Rule

The balance sheet agent receives net income as an immutable input from the P&L agent. This value:
- Must be consumed directly into the retained earnings calculation.
- Must NOT be recalculated, verified, or adjusted by the BS agent.
- Must appear in the equity roll-forward as the exact value provided.
- If the BS agent produces a retained earnings figure inconsistent with the net income input, this is a halt-level error.

## Equity Roll-Forward

The agent must ensure the following identity holds:

**Ending Equity = Beginning Equity + Net Income - Dividends ± Other Comprehensive Income ± Share Transactions**

Where:
- Beginning Equity = total equity at start of period (may be zero for new entities)
- Net Income = the immutable value from the P&L agent
- Dividends = cash dividends declared during the period
- Other Comprehensive Income = unrealized gains/losses (FX, hedges, available-for-sale securities)
- Share Transactions = stock issuance, buybacks, SBC impact on APIC

If the roll-forward does not reconcile, the variance must be reported. Missing components (beginning equity, dividends, OCI) are flagged but do not auto-halt — they may legitimately be zero or unavailable for the first period.

## Combining Logic (Multi-Entity)

When producing a combined balance sheet:
- Entity A + Entity B + Adjustments = Combined, computed per line item.
- Every adjustment must link to a `conflict_id` from the conflict register.
- Intercompany receivables and payables must be eliminated. The elimination must net to zero.
- Goodwill and intangible asset adjustments from purchase price allocation (PPA) are applied as adjustments with conflict_id linkage.
- Adjustments without a linked conflict_id are a halt-level error.

## Missing Data Rules

- If a line item category has no data, it must be reported as missing with an explicit flag.
- Missing line items are never zero-filled. Zero is a valid value.
- If total assets data is entirely missing, the agent must halt — a balance sheet cannot be produced.

## Period Rules

- Balance sheets are point-in-time. `period_start` must be null. Only `period_end` is specified.
- The agent must not infer period_start from any source.

## Purchase Price Allocation (PPA) — Convergence Only

When a PPA schedule is provided:
- Fair value adjustments to assets and liabilities are applied as adjustment line items.
- Goodwill = Purchase Price - Fair Value of Net Identifiable Assets. This is a derived value.
- Each PPA adjustment must reference the source asset/liability and the fair value delta.
- PPA adjustments without supporting schedule data are a halt-level error.

## Flags

- Missing policy document for a classification area: emit a warning flag "No policy provided for [area]."
- Equity roll-forward does not reconcile: emit a warning flag with the variance amount.
- Lease liability without corresponding ROU asset (or vice versa): emit a warning flag.
- Deferred revenue classification ambiguity (current vs. non-current): emit a warning flag.
