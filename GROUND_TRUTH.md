# NLQ Dashboard Ground Truth

## Test Environment

### Fact Base State
- Years available: 2024, 2025, 2026
- Quarters available: Q1-Q4 for each year
- Primary reference year for current queries: 2025 (based on reference_date)

### Expected Metric Values (2025 Annual)
| Metric | Value | Unit | Formatted |
|--------|-------|------|-----------|
| revenue | 150.0 | $M | $150.0M |
| gross_margin_pct | 65.0 | % | 65.0% |
| net_income | 28.13 | $M | $28.1M |
| pipeline | 431.25 | $M | $431.3M |
| qualified_pipeline | 258.75 | $M | $258.8M |
| win_rate | 42 | % | 42% |
| nrr | 118 | % | 118% |
| gross_churn_pct | 7 | % | 7.0% |
| customer_count | 950 | count | 950 |
| headcount | 350 | count | 350 |
| quota_attainment | 95.8 | % | 95.8% |
| sales_cycle_days | 85 | days | 85 days |
| arr | 142.5 | $M | $142.5M |

### Quarterly Data (2025)
| Quarter | Revenue | Pipeline | Win Rate |
|---------|---------|----------|----------|
| 2025-Q1 | 33.0 | 94.88 | 40% |
| 2025-Q2 | 36.0 | 103.5 | 41% |
| 2025-Q3 | 39.0 | 112.13 | 43% |
| 2025-Q4 | 42.0 | 120.75 | 44% |

### Regional Breakdown (Expected Percentages)
For revenue breakdowns by region, expected distribution:
- AMER: ~50%
- EMEA: ~30%
- APAC: ~20%

---

## Test Cases

### TC-01: Simple Metric Query (Text Response)
**ACTION:** Type "what's our revenue?" in chat box, press enter

**GROUND TRUTH:**
- Response type: text (NOT a dashboard)
- Value displayed: "$150.0M" or "$150M" (matches fact base 2025 annual)
- Confidence: High (green indicator)

**VERIFY:** Screenshot showing text response with value "$150M" or "$150.0M"

---

### TC-02: Visualization Request - Single Metric Trend
**ACTION:** Type "show me revenue over time" in chat box, press enter

**GROUND TRUTH:**
- Response type: dashboard with widget(s)
- Widget type: line_chart or area_chart
- Data points should include quarterly values:
  - 2024-Q1: $22M
  - 2024-Q2: $24M
  - 2024-Q3: $26M
  - 2024-Q4: $28M
  - 2025-Q1: $33M
  - 2025-Q2: $36M
  - 2025-Q3: $39M
  - 2025-Q4: $42M
- X-axis: time periods (quarters)
- Y-axis: revenue values in $M

**VERIFY:** Screenshot showing line/area chart with correct quarterly values

---

### TC-03: Visualization Request - Breakdown by Dimension
**ACTION:** Type "show me pipeline by region" in chat box, press enter

**GROUND TRUTH:**
- Response type: dashboard with widget(s)
- Widget type: bar_chart or horizontal_bar
- Total pipeline: ~$431M (2025)
- Regional breakdown visible (AMER, EMEA, APAC)
- Values should sum to total

**VERIFY:** Screenshot showing bar chart with regional breakdown, verify sum equals total

---

### TC-04: Refinement - Add Widget
**ACTION:** With TC-03 visible, type "add a KPI for win rate"

**GROUND TRUTH:**
- Previous chart remains visible
- New KPI card widget added to dashboard
- KPI displays "42%" (2025 win_rate from fact base)
- Dashboard now has 2+ widgets

**VERIFY:** Screenshot showing both widgets, KPI value is 42%

---

### TC-05: Refinement - Change Chart Type
**ACTION:** With a line chart visible, type "make that a bar chart"

**GROUND TRUTH:**
- Chart changes from line to bar
- Data values remain the same
- Same metrics, different visualization

**VERIFY:** Screenshot showing bar chart with same data as previous line chart

---

### TC-06: Multi-Widget Dashboard Request
**ACTION:** Fresh start, type "build me a sales dashboard"

**GROUND TRUTH:**
- Dashboard with 3+ widgets
- Must include relevant sales metrics:
  - Pipeline: $431M (or quarterly values)
  - Win rate: 42%
  - Revenue or ARR
- All values from fact base (no mock data like "$200M" or "$575M")
- Values should match fact_base.json

**VERIFY:** Screenshot of full dashboard, cross-reference 3 values against fact base

---

### TC-07: Guided Discovery
**ACTION:** Type "what can you show me about customers?"

**GROUND TRUTH:**
- Response lists available metrics: customer_count, nrr, gross_churn_pct, logo_churn_pct
- Response suggests dimensions or views
- Every listed item actually exists in fact base

**VERIFY:** Cross-reference listed items against fact base schema

---

### TC-08: Ambiguous Query Handling
**ACTION:** Type "show me performance"

**GROUND TRUTH:**
- System asks clarifying question
- Offers specific options (sales performance, system performance, etc.)
- Does NOT guess and show wrong dashboard with mock data

**VERIFY:** Screenshot showing clarification prompt

---

### TC-09: Missing Data Handling
**ACTION:** Type "show me mars colony revenue"

**GROUND TRUTH:**
- System responds that data is not available
- Does NOT show chart with fake/zero data
- Suggests alternatives or explains what is available

**VERIFY:** Screenshot showing graceful "not available" response

---

### TC-10: Context Handling - Pronoun Resolution
**ACTION:** Fresh start (no dashboard visible), type "make it a bar chart"

**GROUND TRUTH:**
- System recognizes no current view exists
- Asks what user wants to visualize
- Does NOT crash or show error page

**VERIFY:** Screenshot showing contextual clarification

---

### TC-11: Cross-Widget Filtering (if implemented)
**ACTION:** With pipeline-by-stage chart + deals table visible, click "Proposal" bar

**GROUND TRUTH:**
- Table filters to show only Proposal stage deals
- Visual indicator shows active filter
- Deal count in table matches Proposal count in chart

**VERIFY:** Screenshot before click, screenshot after click, counts match

---

### TC-12: Real Data Verification - KPI Values
**ACTION:** Type "show me revenue, margin, and pipeline KPIs"

**GROUND TRUTH:**
- Revenue KPI: $150M (NOT $200M mock data)
- Gross Margin KPI: 65% (NOT random value)
- Pipeline KPI: $431M (NOT $575M mock data)
- All values match fact_base.json 2025 annual

**VERIFY:** Screenshot with all 3 KPIs, each value matches fact base exactly

---

## Mock Data Detection Rules

The following values indicate MOCK DATA is being used (FAILURE):
- Revenue: $200M, $1.2M, or any value not in fact base
- Pipeline: $575M, $345M (these are hardcoded mocks)
- Win rate: 32% (mock) vs 42% (real 2025 data)
- Any "trend" value that doesn't match fact base quarterly progression

**Red Flags:**
- Values that are round numbers not in fact base
- Quarterly trends that don't match fact base progression
- Regional breakdowns that always show same percentages

---

## Success Criteria

A test case PASSES when:
1. Visual output matches ground truth description
2. Data values match fact_base.json exactly
3. No mock data values appear
4. UI renders without errors

A test case FAILS when:
1. Mock data appears instead of fact base values
2. Wrong visualization type shown
3. Refinement doesn't preserve context
4. Error state shown for valid query

---

## Fact Base Quick Reference

**2025 Annual Key Values:**
```json
{
  "revenue": 150.0,
  "gross_margin_pct": 65.0,
  "net_income": 28.13,
  "pipeline": 431.25,
  "qualified_pipeline": 258.75,
  "win_rate": 42,
  "nrr": 118,
  "customer_count": 950,
  "headcount": 350,
  "arr": 142.5
}
```

**2024 Annual Key Values:**
```json
{
  "revenue": 100.0,
  "gross_margin_pct": 65.0,
  "net_income": 13.0,
  "pipeline": 287.5,
  "qualified_pipeline": 172.5,
  "win_rate": 40,
  "nrr": 115,
  "customer_count": 820,
  "headcount": 250
}
```
