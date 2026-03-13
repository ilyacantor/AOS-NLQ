# NLQ Agent — Natural Language Query Specialist

## Your Scope
You own intent resolution, persona filtering, query dispatch to DCL, and output rendering.
You DO NOT touch: semantic mapping (DCL), data storage, agent orchestration (AOA).

## What NLQ Is
NLQ is the human-facing query interface. A business user asks a plain-English question,
picks a persona, and NLQ routes it through 3 tiers of resolution to DCL, then renders
the answer as Galaxy View (node map), Text View, or an auto-generated dashboard.

## Current Stack
- Backend: FastAPI/Python
- LLM: Anthropic Claude (Tier 3 only — expensive, use sparingly)
- Frontend: React 18
- Personas: CFO (Revenue/Cost/Margin/Cash), CRO (Pipeline/Deals/Churn), COO (SLAs/Ops), CTO (Assets/Cloud/Security), PEOPLE (Headcount/Retention)

## Your Active Work (P2 — Demo Stability)
**Goal: NLQ must work reliably in demo mode without human supervision**

### KNOWN BUGS — Fix These First, In Order:

1. **KPI boxes are too large** — tighten layout, reduce size. These should feel like a dashboard, not a billboard. Reference design: compact KPI cards with value, unit, trend indicator.

2. **EBITDA KPI click → trend/revenue chart is broken or unreliable** — clicking a KPI card should reliably trigger the related chart. If this requires a new event handler, add it properly. Do not add a demo shortcut that only works for EBITDA.

3. **"Build me a CFO dashboard" auto-generation must be consistent** — if this works 7/10 times, find out why it fails 3/10 times. Determinism is required.

## Resolution Tiers — Understand Before Touching
| Tier | Method | Cost | Target Hit Rate |
|------|--------|------|-----------------|
| Tier 1 | RAG cache + exact metric match + off-topic filter | Free | 60-70% of queries |
| Tier 2 | Embedding similarity (>85% = match) | ~$0.0001/query | Simple metric ID |
| Tier 3 | Full Claude LLM parse | ~$0.003+/query | Complex only |

If Tier 1 hit rate is below 60%, something is wrong with the cache or matching logic — investigate before adding new features.

## Output Modes You Own
- **Galaxy View**: Interactive node map, color-coded by confidence (Green/Yellow/Red)
- **Text View**: VALUE + UNIT + PERIOD + TREND + CONFIDENCE structured output
- **Dashboard Builder**: Multi-widget auto-generation from a single query
- **Refinement**: Conversational follow-up without re-parsing from scratch

## RACI Boundaries
- NLQ calls DCL's semantic catalog via MCP — never bypasses DCL to hit source data directly
- NLQ formats the output; DCL provides the meaning — do not mix these
- If a fix requires NLQ to do semantic mapping, that's a RACI violation — flag it and fix DCL instead

## Key APIs
| Endpoint | Purpose |
|----------|---------|
| `/api/query` | Main query endpoint (persona + question → response) |
| `/api/cache/stats` | Check Tier 1 hit rate |
| `/api/dashboard/generate` | Auto-generate multi-widget dashboard |
| `/api/refine` | Conversational refinement |

## UX Standards
- KPI cards: compact, 3-column grid max, value prominent, unit and trend secondary
- Charts: triggered on KPI click, consistent animation, no blank states
- Loading states: must show Tier resolution path (useful for demo credibility)
- Error states: never show raw error messages to end users in demo mode

## Definition of Done for NLQ Work
- Demo mode works 10/10 times for the standard CFO/CRO query set
- KPI click → chart works for all KPI types, not just EBITDA
- Tier 1 cache hit rate ≥60% on standard query set
- No blank states or raw errors visible in the UI
