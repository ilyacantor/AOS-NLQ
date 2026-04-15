# NLQ deferred work

## 8 harness failures — single-metric value/unit/confidence
Filed 2026-04-14 during multi-metric 422 fix session. Baseline and
post-edit harness runs returned identical 97/8. Each fails on value=None
or unit=None or confidence-below-threshold. None involve multi-metric
decomposition, so they are out of scope for the 422 fix.

| ID | Query | Failure |
|---|---|---|
| PL_001 | What is our EBITDA for 2025? | value None, unit None, confidence 0.5 |
| PL_002 | Show me the 2025 P&L | revenue/cogs/gross_profit/ebitda/net_income all None |
| PL_003 | What was gross margin in Q3 2025? | value None, unit None |
| PL_004 | What is our net income margin? | value None, unit None, confidence 0.5 |
| PERIOD_001 | What is 2025 revenue? | value None |
| PERIOD_002 | What is 2024 revenue? | value None |
| ALIAS_003 | What is gross margin? | unit None |
| CLARIFY_002 | show me the margin | confidence 0.3 |

Shape: response returns success=True with data_source=None and null
values instead of surfacing a real error. Likely another reclassification
or dcl_v2 path with missing data. Separate audit needed.

## Bug #2 — tenant_id guard (scoped out)
Multi-metric 422 payloads currently include `tenant_id: null` inside the
DCL request. Pipeline identity I2 says missing tenant_id must 422. NLQ
is submitting null downstream. Separate fix.

## DebugTracePanel hint regression (cosmetic)
`src/components/DebugTracePanel.tsx:71-75` gates the ANTHROPIC_API_KEY
hint on `error_type === 'CONFIG_ERROR'`. After the HTTPException
re-raise fix in routes.py:5079, App.tsx sets `error_type = 'HTTP_ERROR'`
for all non-200 responses, so this hint no longer fires for the missing
API key case. The underlying error text ("ANTHROPIC_API_KEY not
configured") is still visible in the banner. The hint itself references
Replit which is CLAUDE.md-banned. Replacement path: match on error text
directly (`debugInfo?.error?.includes('ANTHROPIC_API_KEY')`), drop the
Replit copy. Separate cleanup — A13 scope.

## Bug #3 — decomposer treats years as metric names
"show me revenue for 2024, 2025, 2026" is decomposed into
`['revenue_for_2024', '2025', '2026']`. The comma is a year dimension
separator, not a metric separator. Decomposer at routes.py:1982 uses
`re.split(r'\s+and\s+|,\s*', q)` and normalize_metric() is naive, so
bare year strings pass as "metrics". Fix belongs in the decomposer
(detect year-only tokens and reroute to a trend query shape) or in
tiered_intent complexity detection (add a pattern for multi-year).
