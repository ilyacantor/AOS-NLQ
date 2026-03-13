  
**MAESTRA**

Platform Architecture Specification

Version 2.0  |  March 2026

*Supersedes original Maestra spec. Incorporates CTO architecture review, inference cost analysis, and revised build sequencing for Claude Code sessions.*

# **1\. The Problem**

Maestra currently lives in /nlq/reports as a self-contained onboarding demo for a single M\&A scenario (Meridian/Cascadia). She has no awareness of AOD, AAM, Farm, or DCL as live systems. She cannot reach into them, react to their state, or drive them. She is a narrator on top of NLQ, not an operator woven through the stack.

The vision is fundamentally different: Maestra is the persistent AI engagement lead for every customer, across every module, for the entire lifecycle. Not just onboarding. Not just M\&A. She is responsible for customer success functionally and CSAT as her incentive metric.

She is also the action surface. Customers talk to Maestra. When they need something done, she dispatches it. The customer never needs to know which module does what.

## **1.1 What Changed Since v1**

**CTO Architecture Review.** The original spec called for Maestra as a full separate service with her own repo and Render deployment. After cost modeling and latency analysis, this was revised to Option C: Maestra logic lives in the existing reports/portal surface, engagement state lives in a dedicated Supabase schema, and modules expose REST status \+ action endpoints. No new service deployment.

**Inference Cost Modeling.** At enterprise scale (10 users, 20 interactions/day per user), Maestra inference costs $400-420/month per customer at frontier model pricing. This is acceptable for enterprise ARR but requires model routing architecture from day one to prevent cost scaling problems.

**NLQ Decoupling.** Hard decision: Maestra does not live inside NLQ. She lives above it. NLQ is a query engine she calls when needed. The customer talks to Maestra. If the question requires data, Maestra internally dispatches to the NLQ engine. This eliminates the complexity of NLQ as an interaction surface and positions Maestra to eventually replace the NLQ front-end entirely.

**REST Over MCP.** MCP (Model Context Protocol) is the emerging industry standard for agent-to-tool communication. The module endpoint contracts are designed to be MCP-compatible but implemented as REST for this cycle. MCP transport can wrap these endpoints later without architectural change.

**Plan Mode for Write Actions.** Write actions that require code modification generate a structured plan document instead of executing directly. The plan becomes a Claude Code prompt. Human approval required before execution. This is the human-in-the-loop pattern applied to platform operations.

# **2\. Architecture Decisions**

## **2.1 What Maestra Is**

Maestra is a prompt-engineered persona running on a frontier LLM (Claude) with structured context injection. She is not a fine-tuned model, not a small language model, not something that requires training. She is a constitution document \+ live platform state \+ persistent engagement state, assembled at runtime into an LLM call.

This is the correct architecture for March 2026\. Fine-tuning is expensive, brittle, and locks you into a model snapshot. Prompt engineering on frontier models rides the improvement curve automatically.

## **2.2 What Maestra Is Not**

She is not a separate deployed service (for now). She is not a vector database or RAG pipeline (for now). She is not entangled with NLQ internals. She does not read or modify code directly. She does not bypass RACI module boundaries.

## **2.3 The Runtime Pattern**

Every Maestra interaction follows this flow:

| Step | Action | Source |
| :---- | :---- | :---- |
| 1 | Customer sends message via report portal / chat surface | UI layer |
| 2 | Context assembler pulls Maestra constitution (scenario variant) | Static document |
| 3 | Context assembler pulls engagement state for this customer | Supabase: maestra schema |
| 4 | Context assembler pulls live module state (cached, event-driven) | Module REST endpoints via state cache |
| 5 | Assembled prompt sent to LLM with customer message | Claude API (model per routing tier) |
| 6 | LLM responds as Maestra; response may include structured action blocks | LLM output |
| 7 | If action block present: dispatch to module endpoint (read) or generate plan (write) | Action dispatch layer |
| 8 | Update engagement state with interaction record | Supabase: maestra schema |

## **2.4 Three Knowledge Sources**

**The Maestra Constitution (static, versioned).** Her identity, voice, role boundaries, action catalog, scenario variants. Think of it as her CLAUDE.md equivalent. A markdown file that evolves with the product. Separate constitution variants per scenario type (single entity, multi-entity, M\&A, portfolio) that share a common base.

**Engagement State (persistent, per-customer).** Structured data in Supabase tracking: onboarding steps completed, what the customer has seen, questions asked, items flagged, outstanding issues. Not conversation history. Structured state that survives across sessions.

**Live Module State (dynamic, cached).** Current state from each AOS module. Instead of pulling synchronously on every interaction (latency bomb), modules publish state changes to a cache layer. Maestra reads from the cache. Modules push; Maestra never waits.

## **2.5 Model Routing**

Not every Maestra interaction needs a frontier model. The dispatch function routes based on interaction classification:

| Interaction Type | Model Tier | Examples | Est. % of Volume |
| :---- | :---- | :---- | :---- |
| Status / navigation | Haiku-class (fast, cheap) | What is our integration status? Where are we in onboarding? | 60-70% |
| Analysis / synthesis | Sonnet-class (balanced) | Compare revenue recognition across entities. Explain this gap. | 25-35% |
| Strategic / complex | Opus-class (frontier) | Build an integration plan. Diagnose a cross-module failure chain. | 5-10% |

For MVP/demo: Sonnet for everything. Model routing is a cost lever activated when customer volume justifies it. The architecture must support it from day one (single dispatch function with model parameter), but implementation is deferred.

Multi-model support (Claude, Gemini, others) is strategic resilience. Same dispatch function, different provider. Abstraction cost: one function signature.

## **2.6 Event-Driven State Cache**

The original spec proposed that Maestra pull live state from multiple modules via synchronous API calls before each LLM call. CTO review identified this as a latency risk: if AOD, AAM, Farm, DCL, and NLQ status endpoints are called sequentially, multi-second pre-LLM latency accumulates.

Revised approach: each module publishes state changes to a lightweight cache (Supabase table or Redis). Maestra reads from the cache, which is always current. This also prevents N x M request amplification as customer count grows.

# **3\. Capability Layers**

Everything Maestra does falls into one of three layers. Each has different architectural requirements.

## **3.1 Layer 1: Platform Oracle**

Maestra can answer any question about platform state by reading module status, engagement state, and her constitution. She does not scan codebases at query time (deferred to later phase). For now, her knowledge comes from the structured state each module exposes.

## **3.2 Layer 2: Action Agent**

**This is the key upgrade from v1.** Maestra does not just narrate. She dispatches actions. Read actions execute immediately against module endpoints. Write actions generate a plan document for human approval.

Action tiers:

| Tier | Action Type | Behavior | Examples |
| :---- | :---- | :---- | :---- |
| Read | Query / status / report generation | Execute immediately, return result | Show discovery results, generate overlap report, pull connection status |
| Write (safe) | Configuration that is reversible | Execute with confirmation prompt | Reorder connection priorities, set report schedule |
| Write (critical) | Code changes, schema changes, irreversible ops | Generate plan document, require human approval before execution | Create new extraction rules, build custom pipe definitions, re-run discovery |

## **3.3 Layer 3: Engagement Lead**

Maestra owns the full customer lifecycle. She tracks what the customer has seen, what has changed, what needs attention, and proactively surfaces insights. She remembers context across sessions and across modules. She is responsible for CSAT as her incentive metric.

# **4\. Full Capability Inventory**

Every capability is tagged with its access pattern. These tags determine implementation requirements.

| Tag | Meaning |
| :---- | :---- |
| READ | Maestra consumes state/data from the module (cached status, API call) |
| WRITE | Maestra modifies state in the module (creates configs, dispatches actions) |
| STATEFUL | Requires Maestra to persist context across sessions or interactions |
| LLM | Requires LLM reasoning (not just data retrieval or rule execution) |
| PLAN | Write action that generates a plan document for human approval |

## **4.1 AOD (Discovery)**

Where Maestra first meets the customer. Discovery produces the initial system inventory.

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Narrate discovery results | Translate AOD output into business language | READ LLM |
| 2 | Surface governance decisions | Flag items needing human decision: duplicate CRMs, conflicting sources | READ LLM |
| 3 | Track discovery progress | Which phases complete, what % of landscape mapped | READ STATEFUL |
| 4 | Configure discovery scope | Adjust what AOD looks for: categories, thresholds, exclusion zones | WRITE |
| 5 | Handle no-fabric scenarios | Explain alternatives when customer lacks fabrics: manual ingest, partial mode | READ LLM |
| 6 | Create manual ingest paths | Build ingest configs for customer-provided data (spreadsheets, CSVs) | WRITE LLM PLAN |
| 7 | Compare discovery runs | Diff successive runs: new, disappeared, reclassified | READ STATEFUL |
| 8 | Generate discovery summary | Formatted reports for customer stakeholders | READ LLM |
| 9 | Re-run discovery | Trigger AOD discovery for specific system or full scope | WRITE PLAN |

## **4.2 AAM (Action & Mapping)**

AAM generates connection manifests. Maestra is the project manager translating manifest status into human terms.

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Report manifest status | 14 of 16 connections live, 2 need your attention | READ |
| 2 | Explain connection failures | Why a manifest failed; suggest remediation | READ LLM |
| 3 | Track SSO confirmations | Which connections require SSO, which are pending | READ STATEFUL |
| 4 | Configure connection priorities | Reorder which systems connect first by business priority | WRITE |
| 5 | Explain idempotency skips | Normal behavior, not an error | READ LLM |
| 6 | Retry failed manifests | Re-dispatch specific manifests that failed | WRITE PLAN |
| 7 | Monitor connection health | Post-deployment, track status and alert on degradation | READ STATEFUL |

## **4.3 Farm (Dev/Test) / iPaaS (Production)**

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Narrate data generation | What Farm is generating, which personas, what financial model produces | READ LLM |
| 2 | Monitor iPaaS execution | In production, track manifest execution; surface completions, failures | READ STATEFUL |
| 3 | Explain data model | Driver assumptions, quarter structure, metric derivations | READ LLM |
| 4 | Surface data quality issues | Explain quality flags in business terms | READ LLM |
| 5 | Configure refresh schedules | Set how often data is pulled from connected systems | WRITE |
| 6 | Handle partial data scenarios | Explain what is available vs. missing without alarming the customer | READ LLM STATEFUL |
| 7 | Manage tenant context | Maintain awareness of active tenant, ensure correct tenant\_id | READ STATEFUL |

## **4.4 DCL (Semantic Layer)**

DCL is the brain: 107 concepts, 325 pairings, entity resolution. Maestra is the semantic layer's voice.

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Explain what DCL knows | Concepts mapped, dimensions available, what can be answered | READ LLM |
| 2 | Surface semantic gaps | When a query fails due to missing mapping, explain gap \+ what fills it | READ LLM |
| 3 | Report data conflicts | Sources disagree on revenue; surface conflict with context | READ LLM |
| 4 | Track semantic coverage | As new sources come online, report expanding coverage | READ STATEFUL |
| 5 | Configure extraction rules | Build/modify extraction rules for customer-specific metrics | WRITE LLM PLAN |
| 6 | Create concept mappings | Map customer proprietary KPIs into DCL | WRITE LLM PLAN |
| 7 | Manage entity resolution | Configure entity tagging, resolution, display for multi-entity | WRITE STATEFUL PLAN |
| 8 | Build custom pipe definitions | Create data paths that do not exist (e.g., missing financial\_summary pipe) | WRITE LLM PLAN |
| 9 | Validate semantic integrity | All concepts reachable? Extraction rules producing data? Orphaned mappings? | READ |

## **4.5 NLQ (Query Engine)**

**Critical change from v1:** Maestra does not live inside NLQ. She calls NLQ when a question requires data. NLQ is the semantic query engine. Maestra is the engagement surface that decides when to invoke it.

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Contextual onboarding | Walk users through capabilities, tailored to role and data | READ LLM STATEFUL |
| 2 | Proactive insight surfacing | Notice metric shifts, suggest queries | READ LLM STATEFUL |
| 3 | Session memory | Remember prior context within and across sessions | STATEFUL |
| 4 | Query coaching | When a query fails, help refine it | READ LLM |
| 5 | Build custom dashboards | Create dashboard configs from customer requests | WRITE STATEFUL |
| 6 | Configure triage workflows | Set alerting: notify me when margin drops below 20% | WRITE STATEFUL |
| 7 | Adapt to customer vocabulary | Map customer terms to platform concepts | WRITE LLM STATEFUL |
| 8 | Cross-entity comparison | Guide cross-entity queries without conflation | READ LLM |
| 9 | Data lineage tracing | For any metric, trace to source system, pipe, extraction rule | READ LLM |

## **4.6 Cross-Module / Platform-Wide**

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | E2E pipeline health | Full chain health (AOD \> AAM \> Farm \> DCL \> NLQ). Diagnose breaks. | READ STATEFUL |
| 2 | Customer engagement state | Track what customer has seen, not explored, what is new | STATEFUL |
| 3 | Implementation project plan | Generate and maintain project plan, track milestones across modules | WRITE LLM STATEFUL |
| 4 | Drift detection | Schema drift, metric drift, volume anomalies. Alert proactively. | READ STATEFUL |
| 5 | Customer playbook | Living context: their systems, vocabulary, pain points, priorities | WRITE LLM STATEFUL |
| 6 | Escalation management | Know when to escalate to human. Track unresolved issues. | LLM STATEFUL |
| 7 | Training and enablement | Walk users through capabilities role by role. Track who is trained. | READ LLM STATEFUL |
| 8 | Multi-scenario awareness | Know scenario type (single, multi, M\&A, portfolio) and adapt | READ STATEFUL |
| 9 | CSAT measurement | Query success rate, time-to-answer, repeat questions, feature adoption | READ STATEFUL |
| 10 | Configuration versioning | Track what was configured, when, by whom. Allow rollback. | WRITE STATEFUL |

## **4.7 Convergence-Specific (M\&A)**

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Dual-entity onboarding | Walk through Acquirer \+ Target discovery, overlaps | READ LLM STATEFUL |
| 2 | COFA unification guidance | Guide combined financial statement unification | READ LLM |
| 3 | Entity resolution management | Configure matching rules across Acquirer and Target | WRITE LLM STATEFUL PLAN |
| 4 | Cross-sell opportunity surfacing | Identify cross-sell from combined customer base | READ LLM |
| 5 | EBITDA bridge construction | Guide standalone-to-combined financials bridge | READ LLM |
| 6 | Integration milestone tracking | Post-close: system consolidation, org merge, data unification | WRITE STATEFUL |
| 7 | Deal lifecycle awareness | Adapt to diligence / close / integration / monitoring phase | READ STATEFUL |

## **4.8 Portfolio-Specific**

| \# | Capability | Description | Tags |
| :---- | :---- | :---- | :---- |
| 1 | Portfolio roll-up view | Aggregate metrics across portfolio companies, drill-down | READ LLM STATEFUL |
| 2 | Cross-company benchmarking | Compare KPIs, identify outliers and best practices | READ LLM |
| 3 | Implementation status across companies | Which companies at which stage | READ STATEFUL |
| 4 | Standardize reporting | Consistent metric definitions across portfolio | WRITE LLM STATEFUL |
| 5 | Value creation tracking | Post-acquisition value vs. original investment thesis | READ LLM STATEFUL |

# **5\. Plan Mode: The Action Dispatch Architecture**

Plan Mode is how Maestra handles write actions that could affect production state or require code changes. It is the human-in-the-loop pattern applied to platform operations.

## **5.1 How It Works**

When Maestra determines that an action requires a write operation (configuration change, code modification, or any irreversible operation), she does not execute. She generates a plan document: a structured proposal describing what she wants to do, why, what modules are affected, and what the expected outcome is.

| Step | Actor | Action |
| :---- | :---- | :---- |
| 1 | Maestra | Identifies need for write action from customer conversation |
| 2 | Maestra (LLM) | Generates structured plan document with rationale, affected modules, expected outcome |
| 3 | System | Persists plan to maestra\_plans table in Supabase with status: pending |
| 4 | System | Notifies approver (webhook to Slack, email, dashboard alert) |
| 5 | Human | Reviews plan, approves or rejects with optional notes |
| 6a | System (if action dispatch) | Calls module REST endpoint to execute the action |
| 6b | Human (if code change) | Plan document becomes a Claude Code prompt; CC executes, runs harness, human reviews diff |
| 7 | System | Updates engagement state: what changed, when, result |

## **5.2 Plan Document Schema**

| Field | Type | Description |
| :---- | :---- | :---- |
| id | UUID | Unique plan identifier |
| customer\_id | UUID | Which customer this is for |
| plan\_type | ENUM | action\_dispatch | code\_change | configuration |
| title | TEXT | Human-readable summary of what Maestra proposes |
| rationale | TEXT | Why this action is needed (from customer context) |
| affected\_modules | TEXT\[\] | Which AOS modules are impacted |
| plan\_body | JSONB | Structured specification of the action |
| cc\_prompt | TEXT | If code\_change: the Claude Code prompt (includes HARNESS\_RULES.md reference) |
| status | ENUM | pending | approved | rejected | executed | failed |
| created\_at | TIMESTAMP | When the plan was generated |
| approved\_by | TEXT | Who approved (null if pending) |
| executed\_at | TIMESTAMP | When the plan was executed (null if pending) |
| result\_summary | TEXT | Outcome after execution |

# **6\. Module Interface Contracts**

Each module exposes REST endpoints for Maestra. These respect RACI boundaries: Maestra calls into modules, never the reverse. Modules remain authoritative for their domain.

All endpoints are designed as MCP-compatible tool definitions (name, description, parameters, return schema) but implemented as REST for this cycle. MCP transport wrapping is a mechanical refactoring when ready.

## **6.1 Read Endpoints (Status)**

| Module | Endpoint | Returns |
| :---- | :---- | :---- |
| AOD | GET /maestra/status | Discovery phase, systems found, shadows, governance pending, fabric availability |
| AAM | GET /maestra/status | Manifest count, execution status, SSO pending, connection health, idempotency stats |
| Farm | GET /maestra/status | Active tenant, personas active, generation progress, data quality flags |
| DCL | GET /maestra/status | Concept count, dimension coverage, extraction rule status, entity resolution state, gaps |
| NLQ | GET /maestra/status | Recent queries, success/fail rates, unresolved queries, persona usage |

## **6.2 Write Endpoints (Actions)**

| Module | Endpoint | Action | Tier |
| :---- | :---- | :---- | :---- |
| AOD | POST /maestra/configure-scope | Modify discovery scope, thresholds, exclusions | Write (safe) |
| AOD | POST /maestra/run-discovery | Trigger discovery run for specific system or full scope | Write (critical) |
| AOD | POST /maestra/create-ingest | Create manual ingest path for customer data | Write (critical) |
| AAM | POST /maestra/configure-priorities | Reorder connection priorities | Write (safe) |
| AAM | POST /maestra/retry-manifest | Re-dispatch specific failed manifest | Write (critical) |
| DCL | POST /maestra/create-extraction-rule | Add/modify extraction rules for customer metrics | Write (critical) |
| DCL | POST /maestra/create-concept-mapping | Map customer vocabulary to platform concepts | Write (critical) |
| DCL | POST /maestra/create-pipe | Build new pipe definitions for missing data paths | Write (critical) |
| NLQ | POST /maestra/create-dashboard | Create/save custom dashboard configurations | Write (safe) |
| NLQ | POST /maestra/create-triage-rule | Set alerting thresholds and notification workflows | Write (safe) |

# **7\. Maestra Data Model**

Maestra's persistent state lives in a dedicated Supabase schema (maestra). Not a separate database. Not in the NLQ schema. A clean boundary within the existing infrastructure.

| Table | Purpose | Key Fields |
| :---- | :---- | :---- |
| customer\_engagements | One row per customer. Scenario type, phase, onboarding status, CSAT. | customer\_id, scenario\_type, phase, onboarding\_pct, last\_interaction, csat\_score |
| session\_memory | Structured interaction records per customer. Not raw conversation history. | customer\_id, session\_id, interaction\_type, summary, module\_context, created\_at |
| maestra\_plans | Plan mode: pending, approved, and executed action plans. | See Section 5.2 schema |
| customer\_playbooks | Customer-specific context: systems, vocabulary, priorities, pain points. | customer\_id, systems\[\], vocabulary\_map, priorities\[\], updated\_at |
| configuration\_history | Audit log of every config Maestra has made. Supports rollback. | customer\_id, module, action, config\_before, config\_after, created\_at, approved\_by |
| engagement\_signals | CSAT tracking: query success rates, repeat questions, feature adoption. | customer\_id, signal\_type, value, measured\_at |
| module\_state\_cache | Cached module status. Updated by modules via push. Read by Maestra. | module, customer\_id, state\_json, updated\_at, ttl |

# **8\. Inference Logging and Semantic Cache**

Every Maestra interaction is logged for cost visibility, quality monitoring, and future semantic caching.

## **8.1 Interaction Logging (Build Now)**

| Field | Purpose |
| :---- | :---- |
| interaction\_id | Unique identifier |
| customer\_id | Which customer |
| input\_hash | Hash of assembled prompt (for cache key matching) |
| model\_used | Which model tier handled this interaction |
| input\_tokens | Token count of assembled prompt |
| output\_tokens | Token count of response |
| latency\_ms | Total round-trip time |
| interaction\_type | Classification: status, analysis, action, onboarding |
| action\_dispatched | If an action was triggered, which one |
| created\_at | Timestamp |

## **8.2 Semantic Cache (Build Later)**

Once interaction logs reveal repeated patterns (same status questions, same onboarding flow steps), a semantic cache layer eliminates redundant LLM calls. Implementation: embedding similarity on input\_hash, with TTL based on module\_state\_cache freshness. Expected cost reduction: 30-70% of LLM calls for mature deployments.

Do not build the cache now. Build the logging now. The cache is a cost optimization activated by data.

# **9\. Scenario Variants**

The architecture is identical across all four scenarios. What changes is the constitution variant, the engagement state scope, and the available action catalog.

| Scenario | Constitution Variant | Engagement Scope | Action Catalog |
| :---- | :---- | :---- | :---- |
| Single Entity (ContextOS) | ContextOS capabilities, single-entity semantics | One entity onboarding \+ operations | Base module actions only |
| Multi-Entity (non-M\&A) | Entity boundary awareness, comparative analysis | Multiple entities, no deal lifecycle | Base \+ cross-entity comparison |
| M\&A (Convergence) | Deal lifecycle, entity bridge, overlap/conflict | Two entities \+ combined \+ deal phases | Base \+ Convergence-specific actions |
| Portfolio | Cross-deal rollup, benchmarking, value creation | N entities across M deals | Base \+ Convergence \+ portfolio roll-up |

These are prompt variants, not code variants. The dispatch function, context assembly, action catalog, and data model are the same. The constitution document includes scenario-specific sections that are included or excluded based on the customer's scenario\_type in engagement state.

# **10\. Build Sequence**

Each item is a single Claude Code session with a defined test harness. No session is done until 100% pass. Every harness prompt references tests/HARNESS\_RULES.md. Sequencing follows value delivery.

**Hard constraint:** No modifications to the NLQ query pipeline. No changes to DCL extraction rules. No new resolution logic. No changes to existing Convergence multi-entity work. Demo mode stays as-is (separate code path, self-contained).

## **Session 1: Module Status Endpoints**

Add GET /maestra/status endpoint to AOD, AAM, Farm, DCL. Returns structured JSON: what has been done, what is pending, what is broken, last updated timestamp.

**Harness:** Call each endpoint for demo tenant. Assert schema. Assert non-empty data. Assert response time \< 500ms.

**Value:** Platform observability regardless of Maestra. Foundation for all subsequent sessions.

## **Session 2: Engagement State Schema \+ API**

Create maestra schema in Supabase. Build tables: customer\_engagements, session\_memory, maestra\_plans, module\_state\_cache. Thin API layer in existing reports service: GET/POST engagement state per customer, GET/POST plans.

**Harness:** CRUD operations on all tables. Assert state persistence across calls. Assert schema validation rejects bad data.

**Value:** Maestra has persistent memory. Foundation for stateful engagement.

## **Session 3: Constitution \+ Context Assembly**

Write the Maestra constitution document (identity, capabilities, action catalog, scenario variants). Build the context assembly function: given customer\_id \+ message, pull constitution \+ engagement state \+ module status from cache, assemble prompt, call LLM, return response.

**Harness:** Send 10 representative messages (status checks, action requests, analysis questions). Assert Maestra responds in character. Assert response incorporates accurate platform state. Assert token count logging works.

**Value:** Maestra is alive. She knows what is happening across the platform and responds intelligently.

## **Session 4: Action Dispatch (Read-Only)**

Wire Maestra's action catalog to module read endpoints. Show me discovery results dispatches to AOD status. Show me connection map dispatches to AAM status. Generate overlap report dispatches to existing report generation.

**Harness:** Send natural language action requests. Assert correct module endpoint is called. Assert response incorporates the result. Assert no write actions are executed.

**Value:** Maestra can answer and act on read requests across the entire platform.

## **Session 5: Plan Mode for Write Actions**

Build plan generation and approval flow. When Maestra identifies a write action, she generates a plan document instead of executing. Plan persists to maestra\_plans. For code\_change plans, the plan body includes a Claude Code prompt with HARNESS\_RULES.md reference.

**Harness:** Send write-action requests. Assert plan is generated and persisted. Assert Maestra does NOT execute without approval. Assert approved plans dispatch correctly. Assert code\_change plans include valid CC prompts.

**Value:** Maestra can propose changes safely. Human stays in the loop for critical actions.

## **Session 6: Wire to Report Portal**

Replace hardcoded demo flow in report portal with live Maestra system. Demo mode stays as-is (separate code path). Live mode uses context assembly, LLM call, action dispatch. Customer-facing UI surface is the report portal chat.

**Harness:** E2E test through portal UI surface. Assert Maestra responds with live module state. Assert action dispatch works through the UI. Assert demo mode still works independently.

**Value:** Maestra is live. Customers interact with her through the portal. The NLQ query box is no longer the primary interaction surface.

# **11\. What Does Not Change**

**RACI boundaries.** Maestra calls into modules via their APIs. She does not bypass module authority. Farm remains sole authority for tenant\_id. DCL remains authoritative for semantic resolution. Each module owns its domain.

**Demo mode stays self-contained.** The existing Meridian/Cascadia demo remains a separate code path with zero external dependencies. It does not get migrated into the live Maestra system.

**Convergence architecture.** Maestra does not introduce split-brain or separate resolution logic for multi-entity. She uses the existing bridge pattern where Target pipes join Acquirer pipes into one DCL.

**No silent fallbacks.** If Maestra cannot answer or act, she says so. No fallback to fact\_base.json, no hallucination, no guessing.

**NLQ query pipeline untouched.** No modifications to NLQ internals. Maestra sits above NLQ, not inside it. NLQ's regex, keyword, ambiguity, and LLM resolution tiers remain exactly as they are.

**fact\_base.json rules unchanged.** Demo mode only. Live mode: if DCL cannot resolve, show null with 'Data unavailable.' No silent fallback.

# **12\. Deferred (Not In This Build)**

| Item | Why Deferred | When |
| :---- | :---- | :---- |
| MCP transport | REST achieves same function; MCP protocol still stabilizing (2026 roadmap published March 9\) | When MCP enterprise auth and gateway patterns are stable |
| Model routing implementation | Sonnet-for-everything is correct for MVP/demo; routing is a cost lever for scale | When customer volume creates measurable cost pressure |
| Semantic cache | Need interaction log data to identify patterns first | After 30-60 days of production logging reveals cache-worthy patterns |
| Codebase RAG / oracle mode | Structured module status covers 80%+ of questions; codebase scanning is a complexity leap | After live Maestra reveals question patterns that status endpoints cannot answer |
| Separate Maestra service | Option C (logic in reports surface, state in Supabase) is sufficient for this phase | If engagement state complexity outgrows shared infrastructure |
| Drift detection | Requires baseline snapshots that do not exist yet | After customers have 90+ days of data flowing through the pipeline |
| Multi-model provider routing | Claude is primary; Gemini/others are fallback resilience | When provider-specific failure modes or cost differences justify the complexity |
| Proactive insight surfacing | Requires stable metric baselines and change detection infrastructure | After drift detection baselines exist |

# **Appendix A: Tag Analysis**

Counting tags across all capabilities (revised inventory: 63 capabilities across 8 sections):

| Tag | Count | % of Total | Architectural Implication |
| :---- | :---- | :---- | :---- |
| READ | 48 | 76% | Needs status endpoints on every module (Session 1\) |
| LLM | 42 | 67% | LLM reasoning is core, not optional. Constitution must be comprehensive. |
| STATEFUL | 35 | 56% | Engagement state in Supabase is required (Session 2\) |
| WRITE | 17 | 27% | Action dispatch with plan mode for critical writes (Sessions 4-5) |
| PLAN | 9 | 14% | Human-in-the-loop approval for irreversible actions (Session 5\) |

The STATEFUL count (56%) confirms that Maestra cannot be a stateless prompt framework. She must persist engagement context across interactions. Option C (dedicated Supabase schema, not separate service) is the minimum viable architecture that supports this.

The PLAN tag (14%) is new in v2. It identifies capabilities where human approval is architecturally required, not optional. This is the action dispatch safety boundary.

# ***Maestra strategy. The vision is that she is an onboarding agent for all scenarios (single, multi, m\&a, Portfolio). whats built is a pretty good onboarding demo for meridian/cascadia deal. she lives in /nlq/reports. taking her role further, she is the engagement manager e2e for all, and she can do customizations, and customer success \- this is natural. She is integrated and integral to every implementation.***

# ***This chat is about how she materializes throughout the AOS platform modules. Now she is pigeonholed in a corner, doing only m\&a***

# **Maestra: From Corner Office to Command Center**

Let me think through this properly. Right now Maestra is essentially a feature inside NLQ/reports, scoped to one deal demo. The vision is she's the persistent AI engagement lead across the entire AOS lifecycle. The gap between those two things is architectural, not just product.

## **Where She Is Now**

She lives in `/nlq/reports`, runs a self-contained demo mode for Meridian/Cascadia, and does onboarding walkthroughs for that specific M\&A scenario. She has no awareness of AOD, AAM, Farm, or DCL as live systems. She can't reach into them, can't react to their state, can't drive them. She's a narrator sitting on top of NLQ, not an operator woven through the stack.

## **Where She Needs to Be**

Maestra should be the consistent human-facing surface across every AOS module. Not a chatbot bolted onto each one — a single agent identity that has context about what's happening everywhere and can act accordingly.

Here's how I'd think about her presence in each module:

**AOD (Discovery)** This is where Maestra first meets the customer. When AOD is discovering systems, she's the one explaining what was found, what's surprising, what needs attention. She can surface governance decisions ("We found 3 CRM systems — which is authoritative?"). She's translating AOD's technical discovery into business decisions. Right now AOD just produces outputs. Maestra makes those outputs conversational and actionable.

**AAM (Action & Mapping)** Once AOD hands off to AAM, Maestra tracks manifest generation and connection mapping. She knows which manifests succeeded, which failed, which are pending SSO confirmation. She can proactively flag issues instead of waiting for someone to check a dashboard. For the customer, she's the project manager who says "14 of 16 connections are live, here are the two that need your attention."

**Farm (Data Generation / Dev-Test)** In dev/test, Maestra orchestrates the synthetic data story. She knows the financial model, knows the personas, can explain what's being generated and why. In production, where Farm is replaced by real iPaaS execution, she's monitoring manifest execution status and surfacing completion or failures. She's the bridge between the manifest contract and the human who needs to know what happened.

**DCL (Semantic Layer)** This is where Maestra gets really interesting. DCL is the brain — 107 concepts, 325 pairings, entity resolution, extraction rules. Maestra should be able to explain what DCL knows, what it doesn't know yet, where there are gaps. When a new data source comes online and DCL maps it, Maestra tells the customer "We now have visibility into X that we didn't have yesterday." She's the semantic layer's voice. She can also surface conflicts — "Revenue from Source A and Source B disagree by 12%. Here's what we see."

**NLQ (Where she already lives)** This stays her primary interaction surface, but it stops being her only home. NLQ is where the customer asks questions and gets answers. Maestra's role here expands from onboarding guide to ongoing engagement lead — she remembers what you asked last week, she notices when metrics shift, she proactively suggests queries based on what's changed in the underlying data.

## **The Architectural Question**

The real question is: does Maestra become a service, or does she remain embedded logic?

Right now she's embedded logic in NLQ. To fulfill this vision, she probably needs to be one of two things:

**Option A — Maestra as a thin orchestration layer.** She's not a separate service. She's a prompt/context framework that every module can invoke. Each module has Maestra-aware endpoints that provide her with module-specific state. NLQ remains her primary UI surface, but she pulls context from all modules via internal APIs. This is lighter to build and consistent with the current architecture where modules are separate repos.

**Option B — Maestra as her own service.** A dedicated `maestra` repo/service that subscribes to events from all modules, maintains engagement state (what has the customer seen, what's new, what needs attention), and exposes a unified API that NLQ and the report portal consume. Heavier, but cleaner separation.

My instinct is Option A is the right near-term path. It doesn't require a new service, it respects RACI boundaries, and it scales naturally. Each module exposes a `/maestra/status` or similar endpoint that returns structured state Maestra can narrate. NLQ remains the rendering surface.

## **Scenario Coverage**

The four scenarios you named each change her posture:

**Single entity (ContextOS):** Maestra is the implementation guide and ongoing CS lead. She walks you through discovery, celebrates when data sources come online, explains what the semantic layer can now answer, and becomes your ongoing analyst-advisor.

**Multi-entity (non-M\&A):** Same as single but she understands entity boundaries. She can compare across entities without conflating them. "Entity A's revenue recognition looks different from Entity B — here's why."

**M\&A (Convergence):** What's built today, but expanded. She handles the full deal lifecycle — diligence discovery, integration tracking, combined entity reporting, and ongoing monitoring. The bridge where Target meets Acquirer is her natural territory.

**Portfolio (PE/holding company):** Maestra manages across multiple deals or portfolio companies simultaneously. She's the roll-up view. "Across your 6 portfolio companies, 3 have completed integration, 2 are in diligence, 1 hasn't started." This is the Scale tier.

## **What This Means Practically**

To move Maestra from pigeonholed to platform-integrated, the concrete steps are:

Each module needs to expose state that Maestra can consume — what's been discovered, what's connected, what's mapped, what's queryable, what's changed. This isn't a massive lift per module, it's a status/summary endpoint.

NLQ's Maestra logic needs to be refactored from hardcoded demo flow into a context-driven engagement engine that assembles its narrative from live module state.

The demo mode stays as-is (self-contained, separate code path per your existing rule), but live mode Maestra becomes the real thing — pulling real state from real modules.

Want me to draft the module-by-module endpoint specs, or would a Gamma prompt be more useful to visualize the full Maestra platform integration architecture?

***“Maestra, re-run the AOD discovery for the target's Salesforce instance.” \- lightbulb, i was always mindful that we drifted from the insight to action loop in terms of action.  M is action\!***  

***Ok, so what about architecture.  Does she learn about the codebase as she goes along or does she do a complete pass of the codebase, is she a live LLM at all times, does she need training, is she really a small language model, etc***

Maestra Architecture: The Engine Behind the Engagement Lead

The "re-run AOD discovery" moment is exactly right. She's not just narrating — she's the action surface. The customer never needs to know which module does what. They tell Maestra what they need, she dispatches it. That's the whole point.

Now, the hard architectural questions.

## **She Is Not a Trained Model**

Let me kill this one immediately. Maestra is not a fine-tuned model, not a small language model, not something you train. She's a **prompt-engineered persona running on a frontier LLM** (Claude, in your case) with structured context injection. This is exactly what AOS already does in NLQ's Tier 3 — you send Claude a carefully constructed prompt with system context, and it responds in character.

The difference is scope of context. Today her context is a hardcoded demo script. Tomorrow her context is live platform state.

## **How She Knows Things**

Maestra doesn't "learn the codebase." She doesn't need to. She needs to know **platform state and capability**, not implementation details. Think of it this way — a great engagement manager at a consulting firm doesn't know how the backend of every tool works. She knows what each team can do, what's been done, what's pending, and what to ask for next.

Maestra's knowledge comes from three sources, assembled at runtime:

**1\. The Maestra Constitution (static, versioned)** This is her identity document. Who she is, how she speaks, what her role boundaries are, what she can and can't do. It includes the catalog of actions she can dispatch — "run AOD discovery," "check AAM connection status," "pull DCL semantic summary," "generate overlap report." This is a markdown file that evolves with the product. Think of it as her CLAUDE.md equivalent.

**2\. Engagement State (persistent, per-customer)** This is what makes her feel continuous. It tracks: what onboarding steps have been completed, what the customer has seen, what questions they've asked, what's been flagged, what's outstanding. This lives in Supabase (you already use it for DCL receipt durability). It's not conversation history — it's structured state. "Customer has connected 4 of 6 data sources. Last interaction was 3 days ago. Revenue reconciliation flagged a 12% discrepancy that hasn't been resolved."

**3\. Live Module State (dynamic, pulled at query time)** When Maestra needs to answer or act, she calls module endpoints to get current state. AOD tells her what's been discovered. AAM tells her what's connected and what manifests are pending. DCL tells her what's semantically mapped and where gaps exist. NLQ tells her what queries have been run and what failed. She assembles this into her context window before responding.

## **The Runtime Flow**

Customer says something to Maestra. Here's what happens:

The NLQ layer (her UI surface) receives the message. Before sending it to the LLM, it assembles the prompt: Maestra constitution \+ engagement state for this customer \+ relevant live module state (pulled via internal API calls to whichever modules are relevant to the query) \+ the customer's message.

The LLM responds as Maestra. If her response includes an action ("I'll re-run that discovery"), the response includes a structured action block that NLQ parses and dispatches to the appropriate module. The result comes back, Maestra narrates it, engagement state updates.

She's a **live LLM call every time**, not a persistent running process. Stateless compute, stateful context. Same pattern as NLQ today, just with a richer context assembly step.

## **The Action Dispatch Layer**

This is the new piece that doesn't exist yet and it's the thing that makes your lightbulb moment real. Today NLQ can answer questions. Maestra needs to **do things**. That means:

Each module exposes an action catalog — not just status endpoints, but triggerable operations. AOD: "run discovery for \[system\]." AAM: "retry manifest \[id\]." DCL: "show semantic gaps for \[domain\]." NLQ: "generate report \[type\]."

Maestra's constitution includes the action catalog with descriptions of when each action is appropriate. The LLM decides which action to invoke based on the conversation. NLQ parses the LLM's structured output and makes the API call.

This is tool-use / function-calling, which Claude already supports natively. You're essentially giving Maestra a toolkit where the tools are AOS module operations.

## **Does She Do a Full Codebase Pass?**

No. Never. She doesn't read code. She reads **contracts** — the API specs, the action catalogs, the status response schemas. These are curated documents that describe what each module can do and what it reports, written in business terms, not code terms.

If you add a new capability to AOD, you update Maestra's action catalog entry for AOD. That's it. She doesn't need to know you refactored a function or changed a database schema.

## **The Persona Layer vs. The Plumbing**

Important separation. Maestra the persona — her name, her voice, how she introduces herself, her engagement style — that's all in the constitution prompt. You could theoretically swap her persona for a different one (say, a more technical voice for developer-facing deployments) without changing any of the plumbing.

The plumbing is: context assembly, action dispatch, engagement state persistence, module status APIs. That's the infrastructure. Maestra is the character sheet that rides on top of it.

## **What This Means for the Four Scenarios**

The beauty is that the architecture is identical across all four. What changes per scenario is:

**The constitution variant.** Single-entity Maestra knows about ContextOS capabilities. M\&A Maestra knows about entity bridges, overlap reports, conflict registers. Portfolio Maestra knows about cross-deal rollups. These are prompt variants, not code variants.

**The engagement state schema.** Single-entity tracks onboarding for one entity. M\&A tracks two entities plus combined. Portfolio tracks N entities. Same Supabase tables, different scope.

**The action catalog.** M\&A Maestra can trigger overlap reports and entity resolution. Portfolio Maestra can trigger cross-portfolio comparisons. Same dispatch mechanism, different available tools.

## **What You Don't Need**

You don't need a separate Maestra service or repo. You don't need model training or fine-tuning. You don't need RAG over the codebase. You don't need a vector database. You don't need a separate LLM.

You need: a constitution document, an engagement state table in Supabase, status \+ action endpoints on each module, and a context assembly function in NLQ that pulls it all together before each LLM call.

The demo mode you've already built is honestly 60% of the persona work. The remaining 40% is replacing hardcoded demo state with live state and adding the action dispatch layer.

Want me to draft the Maestra constitution document, the engagement state schema, or the module action catalog specs?

***First update your knowledge of AI tools, architectures etc up to this minute. Put on a different hat \- you are an experienced engineer, lifelong Enterprise CIO / CTO, now AOS CTO. Critique this entire plan and architecture in a balanced way, identifying alternatives, inference cost implications in a live enterprise environment, and so on.***

Let me research the current state of AI agent architectures, agentic frameworks, and enterprise AI deployment patterns before giving you the CTO critique.Now I have a solid picture of the current landscape. Let me put on the CTO hat.

---

# **CTO Critique: Maestra Architecture**

Ilya, I'm going to be direct. The vision is strong. The proposed architecture has real merit. But there are meaningful risks, cost traps, and alternative approaches that need to be on the table before you commit engineering cycles. I'm going to go through this the way I would in a board-level architecture review.

## **What the Plan Gets Right**

The decision to keep Maestra as a prompt-engineered persona on a frontier LLM rather than a fine-tuned or trained model is correct. In March 2026, this is the consensus best practice. Fine-tuning is expensive, brittle, and creates a maintenance burden every time the underlying model improves. You'd be locking yourself into a snapshot of capability instead of riding the improvement curve. The "constitution \+ live state \+ engagement persistence" pattern is essentially what the industry now calls the agentic engagement pattern, and it works.

The decision not to create a separate Maestra service is also sound for your stage. You're a startup shipping product, not an enterprise building internal platform infrastructure. Adding a service means adding a deployment, health checks, monitoring, and inter-service auth — overhead you don't need right now.

## **The Inference Cost Problem**

Here's where I'd push back hard. Let me do the math.

Every Maestra interaction requires assembling context before the LLM call. You described: constitution document \+ engagement state \+ live module state from multiple services \+ the user's message. Let's estimate conservatively.

The constitution document: probably 2,000–4,000 tokens once it's complete across all scenario variants. Engagement state for a customer: 500–2,000 tokens depending on history depth. Live module state pulled from AOD, AAM, DCL, NLQ: if you're pulling meaningful status from 4–5 modules, you're looking at 1,000–3,000 tokens per module, so 4,000–15,000 tokens. User message and conversation history for multi-turn: 500–2,000 tokens. Total input context per Maestra call: **8,000–23,000 tokens**.

Output will vary, but engagement responses tend to run 500–2,000 tokens. At current Claude Sonnet 4.6 pricing — roughly $3/M input, $15/M output — a single Maestra interaction costs somewhere between $0.03 and $0.10. That doesn't sound like much until you model it at enterprise scale.

A customer with 10 active users making 20 Maestra interactions per day each: 200 calls/day × $0.07 average \= $14/day \= **\~$420/month per customer** just in inference. If you have 20 customers in production, that's $8,400/month in Maestra inference alone, before any NLQ query costs.

And that's the optimistic scenario. If Maestra is truly the primary interaction surface — if customers are talking to her instead of clicking dashboards — interaction volume could be 5–10x higher. You could be looking at $50,000–$100,000/year in inference costs for a modest customer base.

The Plan-and-Execute pattern, where a capable model creates a strategy that cheaper models execute, can reduce costs by 90% compared to using frontier models for everything. The 2026 trend is treating agent cost optimization as a first-class architectural concern, similar to how cloud cost optimization became essential in the microservices era.

**What I'd do instead:** Implement model routing from day one. Not every Maestra interaction needs Claude Opus or even Sonnet. A tiered approach:

* **Status checks, greetings, simple navigation** ("What's the status of our integration?"): Route to Haiku or an equivalent small model. This is probably 60–70% of interactions.  
* **Analysis, synthesis, multi-module reasoning** ("Compare revenue recognition across both entities and flag discrepancies"): Route to Sonnet.  
* **Complex action planning, conflict resolution, strategic recommendations**: Route to the frontier model.

One team's agents were running every task through Sonnet by default. After adding routing rules, the expensive model still handles everything complex — it just doesn't do the busywork anymore. Research from model routing studies shows that intelligent routing of 90% of requests to budget models with only 10% going to frontier models can reduce costs by 86% without meaningful quality degradation.

A simple heuristic router — not even an ML-based one — could cut your Maestra inference bill by 70–80%.

## **The Context Assembly Latency Problem**

You proposed that Maestra pulls live state from multiple modules via internal API calls before each LLM call. In theory, clean. In practice, this is a latency bomb.

You already know your pipeline has latency issues — DCL push latency on 44k rows was identified as a bottleneck, Step 8 AAM dispatch was 126 seconds before optimization. If Maestra has to call AOD, AAM, Farm, DCL, and NLQ status endpoints sequentially before she can respond, you're adding potentially seconds of pre-LLM latency on top of the LLM inference time itself.

**Alternative: Event-driven state cache.** Instead of pulling state on every interaction, each module publishes state changes to a lightweight event bus (could be as simple as a Supabase table or Redis pub/sub). Maestra's context assembler reads from the cache, which is always current. The modules push; Maestra never waits. This also solves a scaling problem — you're not hitting module endpoints with N × M requests where N is customers and M is interactions.

This is essentially the pattern where the enterprise agentic AI stack spans three tiers: engagement, capabilities, and data, with each tier containing specific layers essential for production deployment. The data tier maintains state; the engagement tier consumes it. They don't synchronously depend on each other.

## **The MCP Question**

You haven't mentioned MCP anywhere in the Maestra architecture, and I think that's a mistake worth examining.

MCP defines a standardized framework for integrating AI systems with external data sources and tools. It includes specifications for data ingestion and transformation, contextual metadata tagging, and AI interoperability across different platforms. MCP's current spec release came out in November 2025\. Over the past year MCP has moved well past its origins as a way to wire up local tools. It now runs in production at companies large and small, powers agent workflows, and is shaped by a growing community.

Each AOS module could expose an MCP server. Maestra becomes an MCP client. The benefit isn't just standardization — it's that the entire ecosystem of tooling, debugging, observability, and security infrastructure being built around MCP becomes available to you for free. You'd also future-proof the architecture for when a customer wants to plug their own tools into Maestra's action catalog.

The counter-argument is complexity. MCP adds a protocol layer you'd need to implement and maintain. For your current stage, simple REST endpoints with a defined contract might be sufficient. But if you're building Maestra to be the long-term engagement surface, MCP alignment is worth considering now rather than retrofitting later.

## **The Action Dispatch Risk**

The "Maestra as action surface" vision — where she can re-run AOD discovery, retry AAM manifests, trigger reports — is the most exciting part and the most dangerous.

Every action Maestra can take is a potential failure mode, a security surface, and a billing event. An enterprise CIO is going to ask: "Who authorized this AI to re-run discovery on our Salesforce instance? What's the audit trail? Can I scope her permissions by role?"

Every agent action requires comprehensive logging with traceable reasoning chains. Compliance teams must be able to see why an agent made specific decisions, what data it used, and which rules it applied.

**What I'd require before shipping actions:**

* Every Maestra-dispatched action gets a unique trace ID logged with: who requested it, what Maestra decided to do, what module endpoint was called, what the result was.  
* Action tiers: read-only actions (status checks, report generation) ship first. Write actions (re-running discovery, modifying configurations) require explicit customer opt-in and possibly human-in-the-loop confirmation.  
* Rate limiting per customer, per action type. You don't want a prompt injection or hallucination causing Maestra to fire off 50 AOD discovery runs.

Effective human-in-the-loop architectures are moving beyond simple approval gates to more sophisticated patterns. Agents handle routine cases on their own while flagging edge cases for human review.

## **The Semantic Caching Opportunity You're Missing**

Semantic caching can cut API costs by up to 73%, while prompt optimization, context engineering, and RAG tuning provide additional savings.

Maestra interactions are going to be heavily repetitive across customers and within customers. "What's our integration status?" "Show me the revenue reconciliation." "Where are we in the onboarding process?" These are near-identical queries that will produce near-identical context assembly patterns. A semantic cache layer — even a simple one using embedding similarity — could eliminate a huge percentage of LLM calls entirely.

This is low-hanging fruit that directly impacts your unit economics.

## **The "Option A vs Option B" Decision**

You framed this as Maestra-as-orchestration-layer (Option A) vs Maestra-as-service (Option B) and recommended A. I agree for now, but I'd add a third option to consider:

**Option C — Maestra as MCP Client \+ Engagement State Service.** Maestra's persona and routing logic lives in NLQ (like Option A). But engagement state — the persistent memory of what each customer has seen, done, and needs — lives in a thin dedicated service (or even just a dedicated Supabase schema with its own API). Modules expose MCP servers for action dispatch.

This gives you the lightweight feel of Option A but separates the concern that will grow most complex over time (engagement state management) into its own boundary. When you eventually need to support Portfolio mode with N entities across M deals, that state management will be the hardest part, and you'll want it cleanly isolated.

## **What I'd Actually Prioritize**

If I'm your CTO and I'm looking at this against everything else on the roadmap — Phase 1 Part 2, NLQ pipeline hardening, the Maestra demo bugs, active commercial conversations — here's my sequencing:

**Phase 1 (Now, low effort, high signal):** Fix the three existing Maestra demo bugs. They're embarrassing in any demo. Ship the demo mode clean.

**Phase 2 (Next 4–6 weeks):** Build the module status endpoints. This is useful regardless of Maestra — you need platform observability anyway. Simple JSON responses: what's been discovered, what's connected, what's mapped, what's queryable.

**Phase 3 (Following 4–6 weeks):** Build engagement state in Supabase. Replace hardcoded demo flow with state-driven flow. Maestra reads from live module status instead of canned scripts. This is the moment she becomes real.

**Phase 4 (After first customer feedback):** Add action dispatch for read-only operations. Model routing for cost control. Semantic caching. Then and only then, write actions with HITL gates.

## **The Bottom Line**

The vision is right. Maestra as the persistent, cross-module engagement lead is a genuine differentiator — most enterprise software makes you learn the software. AOS would have the software learn you and talk to you. That's a real wedge.

But the proposed architecture is over-rotated on the persona layer and under-rotated on the economics layer. In a live enterprise deployment, inference cost and latency will kill you faster than a missing feature. Model routing, semantic caching, and event-driven state aren't optimizations — they're table stakes for an always-on AI engagement lead at enterprise scale.

Build the vision. But build the economics into the architecture from day one, not as a retrofit.

***I'm talking to both personas now. Each should respond as needed.***

1. ***great points and before calling the CTO I literally wrote on my notepad 'this is an ontology knowledge graph use case' and ontology RAG as application, and this is MCP in both senses \- AOS tool calls and external tool calls. correct my terminology if needed. However, if its too complex and REST is easier I'd choose REST for this cycle.***  
2. ***i get the cto point on costs, but 50-100k in inference is not a lot for enteprrise, and the implicaiton (if true) of days of not debugging heuristics hell for me is worthwhile tradeoff, particularlyi as that can be done by someone else over time. for MVP demo, its good to call LLM all the time, much more intelligent sounding. If tiered approach is one-shot, sure. tell me if i'm right or wrong. I do want tiered LLM use, and multi-model. at least now I have 3 models to choose from when i'm bumping against limits. and each has tiers.***  
3. ***action dispatch risk \- agreed. also if the action is code modification, then a call goes out to HQ (me) and plan mode is on until plan is approved; i.e. basically claude code (how would that work?)***  
4. ***Semantic cache, \- yes***  
5. ***Option C is fine, with potential REST substitution as a temporary measure.***  
6. ***The plan and critique have to move off the 'weeks' of dev. this isn't the case today, March 2026\. code building is different now. whatever sequencing is proposed has to be muchmore one-shot and test harness on CC specific, i.e.. like now. ONE CRITICAL OVERARCHING CATCHALL \- if any part of the future revised plan involves NLQ like programming I would be against it. NLQ sucks, I hate it, and all the complexity is not worth it \- particularly given that the obvious future T is that Maestra also powers NLQ query in a larger way than now.***

Good. Let me address each point directly, wearing both hats simultaneously.

## **1\. Ontology / Knowledge Graph / MCP Terminology**

**What Maestra needs to know about AOS** — the module catalog, action catalog, capability map, entity relationships, engagement state — this is a **knowledge graph** problem. Not a full formal ontology in the academic sense (OWL, RDF triples, etc.) but a structured, queryable representation of "what can AOS do, what has it done for this customer, and what's the current state." Think of it as a lightweight domain graph. You could implement it as a JSON-LD document, a set of Supabase tables with relationships, or even a well-structured markdown constitution. The word "ontology" is fine for positioning but don't let anyone tell you that you need Protégé or a triple store to build this. You need structured knowledge, not a PhD project.

**How Maestra talks to modules** — this is the MCP / tool-calling question. MCP in the Anthropic/industry sense is a protocol for how an LLM client discovers and invokes tools on external servers. Your AOS modules would each be an MCP server exposing their capabilities. Maestra (via NLQ or whatever her runtime surface is) would be the MCP client. But MCP is also literally what Claude already does with function calling — when Claude Code calls a tool, that's the same pattern.

Your instinct to use REST for this cycle is the right call. Here's why: MCP's 2026 roadmap literally just published days ago and they're still working on enterprise auth, gateway patterns, and horizontal scaling. The protocol is maturing fast but you'd be building on a moving target. REST endpoints with a clean contract give you the same functional result. When MCP stabilizes further, wrapping those REST endpoints in MCP servers is a mechanical refactoring, not an architectural one. The shape of the data and the contract don't change — only the transport protocol.

So: build REST status \+ action endpoints on each module now. Document them as if they were an MCP tool catalog (name, description, parameters, return schema). When you're ready to go MCP, the catalog *is* the MCP server definition.

## **2\. Inference Costs and Tiered Models**

You're right and the CTO is also right. Here's why both hold:

**You're right that $50–100K/year is noise for enterprise.** If a customer is paying you $200K+ ARR for Convergence, $5K/year in inference cost per customer is a rounding error. And you're absolutely right that for MVP/demo, having Maestra always be maximally intelligent is the correct choice. A Haiku-powered Maestra that gives a flat response in a demo is worse than an Opus-powered one that costs $0.10 per call. The demo needs to sell. Cost optimization is a scaling problem, not a selling problem.

**Where the CTO is right:** the tiered approach doesn't have to be complex. It can be essentially one-shot. Here's the simplest possible version:

You already use Claude's tiered intent resolver in NLQ: regex → keyword → ambiguity → LLM. Apply the same logic to Maestra. Before sending to the LLM, classify the interaction type with a simple heuristic (not an LLM call):

* Message contains a question mark \+ status keywords → **status inquiry** → Haiku  
* Message contains action verbs (run, retry, generate, trigger) → **action request** → Sonnet  
* Message is complex, multi-entity, comparative, or strategic → **analysis** → Opus/Sonnet

That's a dictionary lookup and a few regex patterns. No heuristic hell. No debugging. You write it once in an afternoon. If the heuristic is wrong, the worst case is the user gets a slightly less intelligent response on a status check, or you spend an extra $0.05 on an Opus call for a simple question. The failure mode is graceful in both directions.

For now, for demo: Sonnet for everything. Ship it. When you have paying customers generating real volume, add the routing as a cost lever. The architecture just needs to not preclude it — meaning the LLM call should go through a single dispatch function where you can later swap the model parameter. That's it.

On multi-model: you're right that having Claude, Gemini, and whatever else as options is strategic resilience. The dispatch function takes a model parameter. Today it's always `claude-sonnet-4-6`. Tomorrow it could route. The abstraction costs you one function signature.

## **3\. Action Dispatch \+ Code Modification → Plan Mode**

This is a really interesting idea and it maps directly to a pattern the industry is converging on. Let me describe how it would actually work:

**The pattern is "Human-in-the-Loop with Approval Gates."** When Maestra determines that an action requires code modification or any high-risk write operation, instead of executing, she generates a **plan document** — a structured proposal describing what she wants to do, why, what modules are affected, and what the expected outcome is.

How this maps to Claude Code in practice:

Maestra generates a plan (this is an LLM output, structured as a JSON or markdown spec). The plan gets persisted to a queue (Supabase table: `maestra_plans`). You get notified (webhook to Slack, email, whatever). You review the plan. If approved, one of two things happens:

**Option A — Maestra executes via action dispatch.** If the action is a module operation (re-run discovery, regenerate manifests), she calls the REST endpoint. No code changes. This is the common case.

**Option B — Code changes required.** The plan document becomes a Claude Code prompt. Literally. Maestra writes the prompt, including the HARNESS\_RULES.md reference, the CLAUDE.md constraints, the specific module context. You (or Daniel) open a terminal, paste the prompt (or it's already queued in a task manager), CC executes it, runs the harness, you review the diff. Maestra then updates engagement state: "Code change deployed, here's what changed."

The key insight: Maestra never touches code directly. She generates the *intent* and the *specification*. Claude Code (or Gemini CLI) is the *executor*. You are the *approval gate*. This is exactly the plan-and-execute pattern, except the "planner" is Maestra (frontier model, high reasoning) and the "executor" is a coding agent (which could be a cheaper model for simple changes, or the same model for complex ones).

This also maps to your existing workflow. You're already the orchestrator between Claude Code agents. Maestra just formalizes the intake — instead of you diagnosing what needs to happen, she proposes it based on platform state and customer feedback.

For the `maestra_plans` table: `id`, `customer_id`, `plan_type` (action\_dispatch | code\_change | configuration), `plan_body` (the structured proposal), `status` (pending | approved | rejected | executed), `created_at`, `approved_by`, `executed_at`, `result_summary`. Simple.

## **4\. Semantic Cache — Agreed, Moving On**

This is a later optimization. Note it as a design decision: Maestra's dispatch function should log every interaction (input hash, model used, response, latency, token count). This logging is the foundation for the cache — once you have the data, you can identify the repeated patterns and cache them. Don't build the cache now. Build the logging now.

## **5\. Option C with REST — Confirmed**

Option C (Maestra logic in NLQ surface, engagement state in dedicated Supabase schema, REST endpoints on modules) with REST instead of MCP for this cycle. Clean.

## **6\. Sequencing — Adjusted for 2026 Development Speed**

You're right to push back on "weeks." With Claude Code and Gemini CLI, the unit of work isn't weeks anymore, it's sessions. Let me re-sequence in terms of actual CC sessions, each being a focused prompt with a test harness.

And on your critical catchall about NLQ: **heard loud and clear.** The revised plan keeps Maestra's runtime surface in the reports/portal layer, not entangled in the NLQ query pipeline. NLQ as it exists today is the semantic query engine. Maestra *uses* NLQ when she needs data, but she's not *inside* NLQ. She's a layer above it. Eventually, yes, Maestra subsumes the NLQ interaction — the customer talks to Maestra, and if the question requires a data query, Maestra dispatches it to the NLQ engine internally. The customer never knows or cares about NLQ. But that's the end state, not what you build now.

Here's the revised sequence. Each item is a CC session with a harness:

**Session 1: Module Status Endpoints** Add a `/maestra/status` GET endpoint to each module (AOD, AAM, Farm, DCL). Returns structured JSON: what's been done, what's pending, what's broken, last updated timestamp. Harness: call each endpoint, assert schema, assert non-empty data for demo tenant. This is useful infrastructure regardless of Maestra — you need it for platform observability.

**Session 2: Engagement State Schema \+ API** Create `maestra_engagement` and `maestra_plans` tables in Supabase. Build a thin API layer (could live in the existing reports service since Maestra already lives there): GET/POST engagement state per customer, GET/POST plans. Harness: CRUD operations, assert state persistence across calls.

**Session 3: Maestra Constitution \+ Context Assembly** Write the Maestra constitution document (her identity, capabilities, action catalog, scenario variants). Build the context assembly function: given a customer ID and a message, pull constitution \+ engagement state \+ module status from the Session 1/2 endpoints, assemble the prompt, call the LLM, return the response. Harness: send 10 representative messages (status checks, action requests, analysis questions), assert Maestra responds in character with accurate platform state.

**Session 4: Action Dispatch (Read-Only)** Wire up Maestra's action catalog to actual module endpoints. Start with read-only: "show me discovery results" dispatches to AOD status, "show me connection map" dispatches to AAM status, "generate overlap report" dispatches to existing report generation. Harness: send natural language action requests, assert correct module endpoint is called, assert response incorporates the result.

**Session 5: Plan Mode for Write Actions** Build the plan generation and approval flow. When Maestra identifies a write action ("re-run discovery," "retry this manifest"), she generates a plan document instead of executing. Plan gets persisted to `maestra_plans`. Harness: send write-action requests, assert plan is generated and persisted, assert Maestra does NOT execute without approval, assert approved plans execute correctly.

**Session 6: Wire to Report Portal** Replace the existing hardcoded demo flow in the report portal with the live Maestra system. Demo mode stays as-is (separate code path, self-contained). Live mode uses the new context assembly → LLM → action dispatch flow. Harness: end-to-end test through the portal UI surface, asserting Maestra responds with live module state.

Each of these is a single CC session. Not weeks. Sessions. The harness for each one is defined upfront and references `tests/HARNESS_RULES.md`. No session is done until 100% pass.

**What's explicitly NOT in this plan:**

* No modifications to NLQ query pipeline  
* No changes to DCL extraction rules  
* No new resolution logic  
* No changes to the existing Convergence multi-entity work  
* No model routing (Sonnet for everything, optimize later)  
* No semantic caching (logging only, cache later)  
* No MCP (REST now, MCP-shaped contracts for later)

The demo mode Maestra you've already built continues to work exactly as-is for demos. Live mode Maestra is the new build. They share the persona but nothing else.

One more thing on the NLQ point. You said Maestra also powers NLQ query in a larger way in the future. I think the correct framing is: **Maestra replaces the NLQ *interaction surface* but preserves the NLQ *engine*.** The customer stops talking to a query box and starts talking to Maestra. When the question is a data question, Maestra internally calls the NLQ engine (which still does regex → keyword → ambiguity → LLM resolution against DCL). But the customer never sees NLQ. They see Maestra. This means NLQ's complexity becomes an internal implementation detail that Maestra abstracts away, which is exactly what you want — the complexity doesn't go away, but the customer (and you, when building new features) never has to think about it directly.

That's the path. What do you want to drill into first?

***Redraft the spec you wrote originally with reference to all the subsequent decisions and rationale.***

