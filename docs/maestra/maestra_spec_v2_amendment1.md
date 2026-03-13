# Maestra Spec v2 — Amendment 1

**Date:** March 2026
**Scope:** Aligns spec v2 with final build plan decisions. Supersedes conflicting sections in v2.

---

## Amendment 1: Scope Narrowed to M&A Convergence

**Spec v2 says:** Four scenario variants (Single Entity, Multi-Entity, M&A, Portfolio) are described as "prompt variants, not code variants" and presented as part of the build.

**Actual decision:** Only M&A Convergence is being built. Single Entity, Multi-Entity, and Portfolio are deferred entirely. They are not prompt variants to write now — they are future product expansions that depend on capabilities and infrastructure that don't exist yet (cross-entity aggregation for Portfolio, ContextOS product definition for Single Entity).

**What changes:** Section 9 (Scenario Variants) moves to a "Future" appendix. The build sequence, constitution documents, engagement state schema, and action catalog are scoped exclusively to M&A Convergence. The schema supports other scenario_types (the ENUM is there) but no constitution, action catalog, or test coverage exists for them.

---

## Amendment 2: Capability Inventory Trimmed

**Spec v2 says:** 63 capabilities across 8 sections, all presented as the plan.

**Actual decision:** After pressure testing, only 23 capabilities survive for M&A Convergence. 14 were rated "questionable" and 6 were rated "magic beans" — meaning they depend on infrastructure that doesn't exist (iPaaS monitoring, drift detection, triage alerting, portfolio roll-ups, data lineage tracing, CSAT analytics).

**What changes:** The main capability tables in Sections 4.1–4.8 are reclassified. Only capabilities rated "solid" or "feasible" are in scope for the build sessions. All others move to a deferred appendix with explicit engineering prerequisites listed (e.g., "Requires iPaaS production pipeline," "Requires DCL conflict detection subsystem").

Specific removals from active build:
- Section 4.3 item 2 (Monitor iPaaS execution) — iPaaS doesn't exist
- Section 4.3 item 5 (Configure refresh schedules) — no production scheduling
- Section 4.4 items 5-8 (DCL write operations) — LLM-generated config too unreliable
- Section 4.5 item 2 (Proactive insight surfacing) — no background change detection
- Section 4.5 item 6 (Configure triage workflows) — no alerting infrastructure
- Section 4.5 item 9 (Data lineage tracing) — no lineage infrastructure
- Section 4.6 item 4 (Drift detection) — no baseline infrastructure
- Section 4.6 item 9 (CSAT measurement) — no analytics instrumentation
- Section 4.7 items 3-4 (Entity resolution management, Cross-sell surfacing) — expert config / unbuilt
- Section 4.8 items 1-2, 4-5 (Portfolio roll-up, benchmarking, standardization, value tracking) — no infrastructure

---

## Amendment 3: Build Sequence is 5 Sessions, Not 6

**Spec v2 says:** 6 sessions — with Session 5 as Plan Mode and Session 6 as Portal Wiring.

**Actual decision:** Consolidated to 5 sessions. Plan mode is combined with action dispatch in Session 4. Portal wiring is Session 5. This reflects the actual CC session prompts produced.

**What changes:** Section 10 build sequence becomes:
- Session 1: Module Status Endpoints (AOD, AAM, Farm, DCL)
- Session 2: Engagement State Schema + API (Supabase + NLQ)
- Session 3: Constitution + Context Assembly (NLQ)
- Session 4: Action Dispatch + Plan Mode (NLQ)
- Session 5: Wire to Report Portal + Logging (NLQ)

---

## Amendment 4: Demo Mode Eliminated

**Spec v2 says:** "Demo mode stays as-is (separate code path, self-contained)" — repeated in Sections 1.1, 10, and 11.

**Actual decision:** There is no separate demo path. The live Maestra path handles the demo scenario.

**Rationale:** The demo data (Meridian $5B / Cascadia $1B) already flows through the real pipeline — Farm generates it, DCL maps it, NLQ queries it. Once module status endpoints exist (Session 1), Maestra reads real state for the demo tenant. She narrates the Meridian/Cascadia deal by reading live module state, not by reciting a canned script.

The demo tenant is seeded in the engagement state schema (Session 2 SQL migration) as a real customer engagement with scenario_type='convergence', deal_phase='analysis', and pre-populated playbook data. To Maestra, it's a regular customer.

**What changes:**
- Section 11 "Demo mode stays self-contained" is deleted
- Session 5 no longer includes a demo/live switch
- The old demo code in the report portal is archived (kept in git history) and eventually deleted
- The build sessions no longer carry the constraint "do not modify existing demo code"
- All test cases that reference demo mode are replaced with tests against the seeded demo tenant using the live path

**Edge case:** If modules are down during a demo, Maestra handles it per the constitution's graceful degradation rule: she reports stale cached state with a timestamp, or says the module is unreachable. For important demos, ensure modules are running — which you'd do anyway.

---

## Amendment 5: "Maestra Lives Above NLQ" Clarification

**Spec v2 says:** "Maestra does not live inside NLQ. She lives above it."

**Build plan says:** Maestra's code goes in `nlq/src/maestra/` — inside the NLQ repo.

**Clarification:** Both are correct. "Lives above NLQ" means architecturally — she is not entangled with the NLQ query resolution pipeline (regex → keyword → ambiguity → LLM tiers). She calls NLQ as a client when she needs data. She shares the NLQ repo, Render deployment, and Supabase connection for infrastructure convenience, but has zero code dependencies on NLQ query internals.

The `nlq/src/maestra/` directory is a peer of the query pipeline code, not nested inside it. Deleting the maestra directory would leave NLQ functioning exactly as before.

This is Option C from the architecture discussion: Maestra logic in the existing reports/portal surface, engagement state in dedicated Supabase schema, no new service deployment. She's a tenant of NLQ's infrastructure, not a component of NLQ's query engine.

---

## Amendment 6: NLQ Status Endpoint Deferred

**Spec v2 says:** Session 1 adds GET /maestra/status to AOD, AAM, Farm, DCL, and NLQ.

**Actual decision:** NLQ status endpoint is deferred from Session 1. The four other modules get status endpoints. NLQ's status (query success rates, persona usage, feature adoption) requires instrumentation that doesn't exist yet. Adding it means modifying the NLQ query pipeline, which violates the "no NLQ internals changes" constraint.

Maestra can function without NLQ status. She reads data from NLQ by dispatching queries, not by reading NLQ's internal metrics. NLQ status becomes a later enhancement when the value of query analytics justifies the instrumentation work.

**What changes:** Session 1 covers 4 modules (AOD, AAM, Farm, DCL), not 5.

---

## Summary of Amendments

| # | Topic | v2 Spec Said | Amended To |
|---|-------|-------------|------------|
| 1 | Scope | 4 scenarios | M&A Convergence only |
| 2 | Capabilities | 63 active | 23 active, rest deferred with prerequisites |
| 3 | Sessions | 6 sessions | 5 sessions |
| 4 | Demo mode | Separate code path preserved | Eliminated; live path handles demo tenant |
| 5 | NLQ relationship | "Above NLQ" vs in NLQ repo | Clarified: in repo, not in query pipeline |
| 6 | NLQ status | Included in Session 1 | Deferred |

---

*This amendment is the authoritative reference. Where it conflicts with v2 spec, this document wins.*
