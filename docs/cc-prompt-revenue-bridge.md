# NLQ: Revenue Variance Bridge (Waterfall) — Live Data, FY 2025 vs FY 2024

## Context

Building on the P&L financial statement feature. Adding a revenue bridge (waterfall) chart that decomposes the year-over-year revenue change into its contributing drivers: New Logo, Expansion, and Renewal.

This is a preset "gee whiz" visualization. When a user asks "why did revenue increase" or "revenue bridge," they get a horizontal waterfall chart showing FY 2024 total revenue on the left, the three drivers in the middle, and FY 2025 total revenue on the right. Downloadable as Excel with both the data table and an embedded chart.

**This must work against live DCL data, not fact_base.json.**

## Data strategy

All data comes from DCL via the existing `dcl_semantic_client`. The bridge needs these 4 metrics, each for FY 2024 and FY 2025:

| Metric | DCL concept name (verify in codebase) |
|--------|---------------------------------------|
| Total Revenue | `revenue` |
| New Logo Revenue | `new_logo_revenue` |
| Expansion Revenue | `expansion_revenue` |
| Renewal Revenue | `renewal_revenue` |

**IMPORTANT — Before writing any code:**
1. Check DCL's concept registry / persona_concepts.yaml to confirm these metric names are registered
2. Check the dcl_semantic_client to see how annual queries work — does it accept `FY 2024` as a period, or do you need to query Q1–Q4 and sum?
3. Check how the P&L composite handler already solves the annual aggregation problem — reuse that logic

**Query approach:**
- 4 metrics × 2 years = 8 DCL queries
- Use asyncio.gather() to parallelize — should complete in under 1 second
- If DCL returns quarterly data, sum Q1–Q4 for each year

**If a metric is not available from DCL:** Do NOT fall back to fact_base.json. Do NOT silently substitute zeros. Return the bar with `value: null` and render it as "Data unavailable" in the UI. Fail loudly. The user should see exactly what DCL can and cannot resolve.

**In demo mode:** Same bridge, same logic, but data comes from whatever the demo mode data path is (fact_base or demo DCL). The bridge handler should respect the existing data_mode toggle — same pattern as the P&L handler.

## Bridge calculation logic

```
FY 2024 Revenue     = DCL query: revenue, period FY 2024
FY 2025 Revenue     = DCL query: revenue, period FY 2025

FY 2024 New Logo    = DCL query: new_logo_revenue, period FY 2024
FY 2025 New Logo    = DCL query: new_logo_revenue, period FY 2025
New Logo Δ          = FY 2025 New Logo - FY 2024 New Logo

FY 2024 Expansion   = DCL query: expansion_revenue, period FY 2024
FY 2025 Expansion   = DCL query: expansion_revenue, period FY 2025
Expansion Δ         = FY 2025 Expansion - FY 2024 Expansion

FY 2024 Renewal     = DCL query: renewal_revenue, period FY 2024
FY 2025 Renewal     = DCL query: renewal_revenue, period FY 2025
Renewal Δ           = FY 2025 Renewal - FY 2024 Renewal

Validation: New Logo Δ + Expansion Δ + Renewal Δ should ≈ (FY 2025 Revenue - FY 2024 Revenue)
If it doesn't balance within $0.5M (rounding tolerance), add a "Rounding" bar.
Do NOT silently absorb the gap into one of the other bars.
```

**Bar order (top to bottom, since horizontal):**
1. FY 2024 Revenue (gray total bar)
2. New Logo Growth (green if positive, red if negative)
3. Expansion Growth (green if positive, red if negative)
4. Renewal Change (green if positive, red if negative)
5. FY 2025 Revenue (gray total bar)

That's 5 bars minimum. If a rounding bar is needed, 6.

## Backend

### Bridge handler: `src/nlq/core/bridge_query.py`

Create a new module with:

**`is_bridge_query(question: str) -> Optional[str]`**
Returns the bridge type string (`"revenue"`) if the query is a bridge request, else None.

**`BridgeHandler` class:**
1. Accepts the query and data mode
2. Queries DCL for all required metrics (parallel)
3. Computes the driver decomposition
4. Returns structured response

**Response structure:**

```json
{
  "response_type": "bridge_chart",
  "bridge_type": "revenue",
  "title": "Revenue Bridge: FY 2024 → FY 2025",
  "subtitle": "All amounts in $M",
  "period_start": "FY 2024",
  "period_end": "FY 2025",
  "start_value": 109.0,
  "end_value": 155.0,
  "unit": "usd_millions",
  "format": "currency",
  "bars": [
    {
      "label": "FY 2024 Revenue",
      "value": 109.0,
      "type": "total",
      "running_total": 109.0
    },
    {
      "label": "New Logo Growth",
      "value": 12.5,
      "type": "increase",
      "running_total": 121.5
    },
    {
      "label": "Expansion Growth",
      "value": 8.3,
      "type": "increase",
      "running_total": 129.8
    },
    {
      "label": "Renewal Change",
      "value": 25.2,
      "type": "increase",
      "running_total": 155.0
    },
    {
      "label": "FY 2025 Revenue",
      "value": 155.0,
      "type": "total",
      "running_total": 155.0
    }
  ],
  "data_source": "live",
  "downloadable": true
}
```

Notes:
- `type` is `"total"` for the start/end bars, `"increase"` for positive drivers, `"decrease"` for negative drivers
- `running_total` is cumulative — each bar starts where the previous ended. The chart uses this to position floating bars.
- `value` for driver bars is the signed delta (positive or negative)
- The example numbers above are illustrative — actual values come from DCL

### Wire into routes.py

Add bridge detection BEFORE single-metric resolution, AFTER the P&L composite check:

```python
# Check for bridge/waterfall intent
bridge_result = await _try_bridge_query(question, persona, session_id)
if bridge_result:
    return bridge_result
```

### Export endpoint

Add `GET /api/v1/export/bridge?session_id={id}&format=xlsx`

Or extend the existing financial-statement export endpoint to handle `bridge_chart` response types too — whichever is cleaner.

The Excel file must include TWO sheets:

**Sheet 1 — Data Table:**
| Driver | FY 2024 | FY 2025 | Change |
|--------|---------|---------|--------|
| New Logo Revenue | $X.X | $X.X | +$X.X |
| Expansion Revenue | $X.X | $X.X | +$X.X |
| Renewal Revenue | $X.X | $X.X | +$X.X |
| **Total Revenue** | **$X.X** | **$X.X** | **+$X.X** |

Formatting:
- Bold total row with top border
- Currency format: `#,##0.0` for $M values
- Change column: green font for positive, red for negative
- Column widths auto-fit, minimum 14 for data columns
- Freeze header row

**Sheet 2 — Waterfall Chart:**
Build an Excel chart using openpyxl:
- Use a stacked bar chart with invisible base segments to simulate waterfall
- Horizontal orientation (categories on Y axis, values on X axis)
- Total bars: solid gray (#6B7280)
- Increase bars: solid green (#10B981)
- Decrease bars: solid red (#EF4444)
- Data labels on each bar showing the value
- Title: "Revenue Bridge: FY 2024 → FY 2025"

If openpyxl's charting is too limited for a clean waterfall (the invisible base trick can be finicky), fall back to: put the data table on Sheet 1 only, well-formatted. Do NOT ship a broken or ugly chart. A clean table alone is better than a mangled chart. But try the chart first.

## Frontend

### BridgeChart component

Create `BridgeChart.tsx` (or equivalent — check what framework/pattern the NLQ frontend uses).

**Chart rendering — Horizontal Waterfall:**

Use Recharts BarChart with `layout="vertical"` (or d3 if Recharts can't handle it). The waterfall is a stacked bar chart where:

- Each bar has an invisible base segment (transparent, from 0 to the bar's start position) and a visible segment (the actual value)
- Total bars: invisible base = 0, visible segment = full value
- Driver bars: invisible base = running_total before this bar, visible segment = the delta value

Implementation pattern (Recharts):
```jsx
<BarChart layout="vertical" data={bars}>
  <XAxis type="number" />
  <YAxis type="category" dataKey="label" width={150} />
  <Bar dataKey="base" stackId="stack" fill="transparent" />
  <Bar dataKey="value" stackId="stack">
    {bars.map((bar) => (
      <Cell fill={bar.type === 'total' ? '#6B7280' : bar.value >= 0 ? '#10B981' : '#EF4444'} />
    ))}
  </Bar>
</BarChart>
```

Where `base` for each bar = `running_total - value` (the invisible starting position).

**Colors:**
- Total bars (FY 2024, FY 2025): gray (#6B7280)
- Positive drivers: green (#10B981)
- Negative drivers: red (#EF4444)

**Data labels:**
- Each bar shows its value at the end (right side) of the bar
- Totals: `$109.0M` (no sign)
- Drivers: `+$12.5M` or `-$3.2M` (always show sign)

**Layout:**
- Clean white card, same visual family as the P&L financial statement
- Title: "Revenue Bridge: FY 2024 → FY 2025" — bold, centered
- Subtitle: "All amounts in $M" — right-aligned, gray, small
- Download Excel button: top-right corner, same pattern as the P&L download
- Chart fills the card width
- Minimum bar thickness so small values are still visible and readable
- Bar labels (left side Y axis): clean, left-aligned, readable font size

**Connecting lines (optional but preferred):**
Thin gray dotted horizontal lines from the end of each driver bar to the start of the next — this is the classic waterfall visual cue. Skip if too complex with Recharts.

**Card behavior:**
This is a full-card takeover — same as the P&L. It does NOT render inside Galaxy. It replaces the main response area entirely.

### Wire into response router

```jsx
if (response.response_type === "bridge_chart") {
  return <BridgeChart data={response} />
}
```

Must fire before Galaxy/text fallback, alongside the financial_statement check.

## Intent detection

Add detection in `ambiguity.py` and/or `bridge_query.py`.

### These queries should trigger the revenue bridge:

- "why did revenue increase"
- "why did revenue go up"
- "what drove revenue growth"
- "revenue bridge"
- "revenue waterfall"
- "explain revenue change"
- "walk me through revenue growth"
- "revenue drivers"
- "what's driving the revenue increase"
- "break down revenue change"
- "revenue growth drivers"
- "decompose revenue"
- "what changed in revenue"
- "revenue walk"

### These should NOT trigger it:

- "what's revenue" → single metric
- "revenue by quarter" → trend/time series
- "show me the P&L" → financial statement (already handled)
- "revenue by region" → dimensional breakdown

### Detection pattern:

Look for revenue-related terms combined with variance/change/driver language:
```python
BRIDGE_REVENUE_PATTERNS = [
    r'revenue\s+(bridge|waterfall|walk|drivers?)',
    r'(why|what).*(revenue|rev).*(increase|decrease|change|grow|drop|move)',
    r'(drove|driving|explain|decompose|break\s*down).*(revenue|rev)',
    r'revenue\s+growth\s+drivers?',
]
```

Test these patterns against the trigger queries AND the non-trigger queries. Zero false positives on the non-trigger list.

## Rules

- No silent fallbacks. If DCL can't resolve a metric, show it as null with "Data unavailable" — never substitute fact_base data in live mode.
- The Excel output must reflect the same data as the on-screen chart — same values, same labels.
- Do not break existing harness tests. Run the full harness after implementation.
- Do not break the P&L financial statement feature.
- The bridge component must be responsive — horizontal bars are already mobile-friendly but verify scrolling/sizing on narrow viewports.
- The chart should handle edge cases: what if all three drivers are negative (revenue declined)? What if one driver is null? What if revenue is flat (all deltas near zero)?

## Verification

1. Start NLQ (demo mode first, then live if DCL is available)
2. Type "why did revenue increase" → should see horizontal waterfall with 5 bars
3. Verify: FY 2024 total + New Logo Δ + Expansion Δ + Renewal Δ = FY 2025 total (visually and numerically)
4. Click Download → should get .xlsx with data table + chart (or data table if chart failed)
5. Open the .xlsx — confirm formatting and values match on-screen
6. Type "what's revenue" → should still get single-metric response, NOT the bridge
7. Type "show me the P&L" → should still get the P&L financial statement, NOT the bridge
8. Run full harness → must pass at same level as before
9. If live DCL is available: switch to live mode, repeat steps 2–5, confirm data_source shows "live"

## Report

- Screenshot of the rendered waterfall in the browser
- Screenshot of the downloaded Excel opened in a spreadsheet app
- Harness results (before and after)
- Whether the Excel chart rendered correctly or fell back to data-table-only
- Any DCL metric resolution failures in live mode (which metrics, what error)
- Edge case behavior: what happens if you ask "revenue bridge" when DCL has no data at all
