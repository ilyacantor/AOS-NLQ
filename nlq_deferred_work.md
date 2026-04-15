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

## Empty-set UX envelope
Filed 2026-04-14 during ARR fix session. Distinction between value=0
(Farm emitted a zero triple) and ∅ (Farm emitted no triples) is now
preserved in code, but the user-facing envelope is shared: both flow
through `WidgetData { value, formatted_value, trend, sparkline_data }`
where null-value widgets surface as "No data for X". The two states
warrant distinct UX — real zero should render "0" or "$0" with trend,
empty set should render an honest "not generated for this entity"
indicator. Proposed shape: add `status: "ok" | "empty" | "error"` and
`reason` fields to widget responses, wire through the React renderer.
Separate design — needs UX discussion before code.

## burn_multiple division-by-zero
`metric_concept_map.yaml:426` defines `burn_multiple` as
`cash_flow.net_burn / revenue.recurring`. If Farm emits
`revenue.recurring = 0` (or the concept is absent), the derived
formula divides by zero. Current derived-metric path in
`dcl_semantic_client_v2.py:get_derived_metric` does not guard. Needs
a decision: return null with reason="undefined", return infinity,
or fall back to a warning flag. Separate from the ARR fix — this is
a derived-metric robustness question, not a concept-mapping one.

## ME-boundary cleanup in NLQ
NLQ must remain entity-agnostic. Any vertical-specific or
multi-entity logic belongs in Convergence or Farm generators, not in
NLQ metric maps, test cases, or resolver code. Ongoing vigilance:
any future code or test that assumes an entity's vertical should be
flagged as a RACI violation (ME concerns live in Convergence per
v7.0). NLQ pre-commit hook already enforces this for SE-only
patterns.

## tests/harness/test_cases.yaml — pre-existing entity contamination
Filed 2026-04-15. The harness fixture file has 31 entities pinned to
the legacy ME-era seed names plus matching comment references. The
SE-only pre-commit hook now blocks any modification to this file
because the file body still contains those forbidden patterns. The
comment-strip task in this session was abandoned mid-flight — only
metric_concept_map.yaml + dashboard_data_resolver.py + this doc were
committed. Two paths forward:
  1. Hook scope fix — compare added lines vs full file, allow edits
     that don't introduce new forbidden patterns. Lower-risk; keeps
     fixtures stable.
  2. Full fixture rewrite — replace legacy names → SE entity_id
     (e.g. HelixEdge-0X4F at ~$124M scale), recalibrate every value
     range against current Farm output via DCL queries. Also
     resolves 8 pre-existing harness failures (PL_001-004,
     PERIOD_001-002, ALIAS_003, CLARIFY_002 all silently return null
     with the legacy entity name). Higher-effort but addresses D6.
Needs direction.

## Farm arr.ending is identical across entities
Direct DCL query confirms `HelixEdge-0X4F` and `SysLabs-ANYC` both
return `arr.ending` series `89.61, 96.05, 102.95, 110.35, 116.91...`
for 2024 quarters — byte-identical. NLQ fix resolves to $152.3M
regardless of entity, which is correct given Farm's output. Farm
data generation concern, not NLQ. Entity-agnostic ARR resolution
works; entity-specific values are Farm's responsibility.
