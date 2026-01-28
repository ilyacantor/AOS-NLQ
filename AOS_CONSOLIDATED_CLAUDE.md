# AutonomOS (AOS) Platform - Consolidated Technical Reference

> **Last Updated**: 2026-01-28
> **Purpose**: Unified technical documentation across all AOS modules
> **Repos Reviewed**: All 8 modules (NLQ, Farm, DCLv2, AODv3, AAM, autonomos-platform/AOA, RevOps Agent, FinOps Agent)

---

## Table of Contents
1. [Platform Overview](#platform-overview)
2. [Canonical Glossary](#canonical-glossary)
3. [Module Index](#module-index)
4. [Architecture Layers](#architecture-layers)
5. [Data Flow](#data-flow)
6. [Tech Stack](#tech-stack)
7. [Design System](#design-system)
8. [Personas](#personas)
9. [Platform Integration Patterns](#platform-integration-patterns)
10. [Identified Inconsistencies](#identified-inconsistencies)
11. [Module Details](#module-details)
12. [Recommendations](#recommendations)

---

## Platform Overview

**AutonomOS (AOS)** is an AI-native "operating system" for the enterprise data/agent stack. It sits between chaotic source systems and domain agents, providing:

1. **Discover & classify** everything that runs in your estate (AOD)
2. **Connect & normalize** business data into a canonical ontology (AAM + DCL)
3. **Feed agents & humans** clean, persona-specific streams of information (FinOps, RevOps, etc.)

### Core Philosophy

| Principle | Description |
|-----------|-------------|
| **No "Green-Test Theater"** | Tests must validate real behavior, not cosmetic passes |
| **Fail Loudly** | Surface errors explicitly - no silent fallbacks |
| **Semantics over Syntax** | Behavior must match real-world meaning |
| **Determinism** | Same inputs = same outputs for reproducible testing |
| **Foundational Fixes Only** | No workarounds - fix root causes |

### The Moat

> **"The Moat is NOT the Runtime. The Moat is the Data."**

**What AOS builds (differentiators):**
- Introspective data tools exposing DCL/AAM/AOD to agents
- Semantic schema discovery
- Cross-system lineage tracking
- Enterprise governance controls

**What AOS buys/integrates (commodity):**
- Agent execution (LangGraph)
- Tool protocol (MCP)
- LLM routing (AI Gateway)

---

## Canonical Glossary

### Core Concepts

| Term | Definition |
|------|------------|
| **Asset** | Anything that RUNS: has a runtime/process, can be up or down, consumes CPU/RAM/IO. NOT assets: CSV files, table definitions, repos, docs |
| **Source** | Logical system-of-record for business entities in DCL. About business meaning, not infrastructure |
| **Ontology** | Formal definition of business entities (Account, Opportunity, Revenue, Cost, Usage, Health) and relationships |
| **Canonical Entity** | Unified, deduplicated representation of a real-world thing across multiple Sources |
| **Canonical Stream** | Time-ordered stream of canonical entities produced by DCL for Agents and dashboards |
| **Fabric Plane** | Integration "motherships" (MuleSoft, Workato, Snowflake, Kafka, Kong) that aggregate connections |

### Source Types

| Type | Role | Is DCL Source? |
|------|------|----------------|
| SYSTEM_OF_RECORD | Where events originate (Salesforce, Stripe) | Yes |
| CURATED | Cleaned/modeled warehouse tables (dim_customer) | Yes |
| AGGREGATED | Rollups for reporting (MRR by segment) | Usually No |
| CONSUMER_ONLY | Read-only visualization (Tableau, Looker) | No |

### Governance Trinity

An asset is **governed** if it has:
- **Visibility**: In CMDB
- **Validation**: SSO/IdP enabled
- **Control**: Vendor-managed lifecycle

---

## Module Index

| Module | Full Name | Purpose | Status |
|--------|-----------|---------|--------|
| **AOA** | Agentic Orchestration Architecture | AI agent workflows & orchestration | In Development |
| **AOD** | Asset Observation & Discovery | Discover, catalog, and score all enterprise assets | Production Ready |
| **AAM** | Adaptive API Mesh | Self-healing integration mesh for data pipes | Production Ready |
| **DCL** | Data Connectivity Layer | Multi-source schema unification & ontology | Production Ready |
| **NLQ** | Natural Language Query | Conversational business intelligence | Production Ready |
| **Farm** | Test Oracle Platform | Synthetic data & ground truth validation | Production Ready |
| **RevOps** | Revenue Operations Agent | CRM integrity & pipeline health | In Development |
| **FinOps** | Financial Operations Agent | Cloud cost optimization | In Development |

---

## Architecture Layers

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TAILORED APPLICATIONS                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   FinOps     │  │   RevOps     │  │   Custom Agents      │  │
│  │   Agent      │  │   Agent      │  │   (Domain-specific)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    PLATFORM SERVICES                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   AOA        │  │   NLQ        │  │   Control Center     │  │
│  │   (Orchestr) │  │   (Query)    │  │   (Intent Routing)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                 OPERATIONAL INFRASTRUCTURE                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   AOD        │  │   AAM        │  │   DCL                │  │
│  │   (Discover) │  │   (Connect)  │  │   (Unify)            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| Infrastructure | **AOD** | Discovers, catalogs, scores everything running in the environment |
| Infrastructure | **AAM** | Connection & auth layer, manages connectors, mediates authentication |
| Infrastructure | **DCL** | Ontology engine, maps source fields to canonical fields, entity resolution |
| Platform | **AOA** | Workflow orchestration for cross-domain playbooks |
| Platform | **NLQ** | Natural language interface with persona classification |
| Applications | **FinOps/RevOps** | Domain-specific agents consuming DCL canonical streams |

---

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Source    │     │    AOD      │     │    AAM      │     │    DCL      │
│   Systems   │────▶│  (Discover) │────▶│  (Connect)  │────▶│  (Unify)    │
│             │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                    ┌──────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agents    │◀────│  Canonical  │◀────│    NLQ      │
│  (FinOps,   │     │   Streams   │     │  (Query)    │
│   RevOps)   │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
```

**Flow Summary:**
1. **AOD** discovers what exists (shadow IT, zombies, governed assets)
2. **AAM** connects to fabric planes and manages authentication
3. **DCL** unifies data into canonical ontology
4. **NLQ** provides natural language query interface
5. **Agents** consume canonical streams and take actions

---

## Tech Stack

### Frontend Stack

| Module | React | Build | CSS | UI Library | Notes |
|--------|-------|-------|-----|------------|-------|
| NLQ | 18 | Vite | Tailwind v4 | Custom | Galaxy visualization |
| DCL | 18 | Vite | CSS Modules | D3.js | Sankey diagrams |
| AOD | - | - | Tailwind | Vanilla JS | Static/Jinja2 |
| AAM | - | - | Tailwind | Vanilla JS | Static/Jinja2 |
| RevOps | 19 | Vite 7 | Tailwind v4 | Custom + Recharts | ⚠️ React 19 |
| FinOps | 18 | Vite | Tailwind | Shadcn/Radix | TanStack Query |
| Platform | 18 | Vite | Tailwind | Custom | Iframe embeds |
| Farm | - | - | Tailwind | Vanilla JS | Static/Jinja2 |

### Backend Stack

| Module | Framework | Language | Database | Cache |
|--------|-----------|----------|----------|-------|
| NLQ | FastAPI | Python | Supabase PG | - |
| DCL | FastAPI | Python | Supabase PG | Pinecone |
| AOD | FastAPI | Python | Supabase PG | - |
| AAM | FastAPI | Python | SQLite | - |
| Farm | FastAPI | Python | Supabase PG | - |
| RevOps | FastAPI | Python | Supabase PG | - |
| FinOps | Express | TypeScript | Neon PG | Pinecone |
| Platform | FastAPI | Python | Supabase PG | Redis |

### AI/LLM Integrations

| Module | Primary LLM | Vector DB | RAG |
|--------|-------------|-----------|-----|
| NLQ | Anthropic Claude | - | No |
| DCL | Gemini 2.5 Flash / OpenAI | Pinecone | Yes |
| AOA | Claude/Gemini (via Portkey) | pgvector | Yes |
| FinOps | Gemini 2.5 Flash | Pinecone | Yes |
| Platform | Gemini / OpenAI | pgvector | Yes |

---

## Design System

### Canonical Color Palette

```css
/* Primary Accent - THE BRAND COLOR */
--aos-cyan: #0BCAD9;           /* Teal/Cyan - Interactive elements */

/* Backgrounds */
--aos-bg-black: #000000;        /* Pure black - Main bg */
--aos-bg-slate-950: #020617;    /* Slate 950 - Alt dark bg */
--aos-bg-slate-900: #0f172a;    /* Slate 900 - Lighter dark bg */
--aos-bg-enterprise: #0A2540;   /* Enterprise blue - Cards */

/* Borders */
--aos-border-blue: #1E4A6F;     /* Blue border - Cards */
--aos-border-slate: #334155;    /* Slate 700 - Subtle */

/* Text */
--aos-text-white: #FFFFFF;      /* Primary text */
--aos-text-secondary: #A0AEC0;  /* Secondary text */
--aos-text-muted: #64748b;      /* Muted text */

/* Domain/Persona Colors */
--aos-finance: #3B82F6;         /* Blue - CFO */
--aos-growth: #EC4899;          /* Pink - CRO */
--aos-ops: #10B981;             /* Green - COO */
--aos-product: #8B5CF6;         /* Purple - CTO */
--aos-people: #F97316;          /* Orange - HR */

/* Status Colors */
--aos-success: #22c55e;         /* Green */
--aos-warning: #f59e0b;         /* Amber */
--aos-error: #ef4444;           /* Red */
--aos-info: #3b82f6;            /* Blue */
```

### Typography
- **Primary Font**: Quicksand (Google Fonts)
- **Monospace**: System monospace for code/values

### Visual Effects
- **Glow**: `0 0 12px rgba(11, 202, 217, 0.3)`
- **Card Shadow**: `0 4px 12px rgba(11, 202, 217, 0.1)`
- **Transitions**: `all 0.2s ease`

---

## Personas

### Supported Personas

| Persona | Primary Entities | Modules |
|---------|-----------------|---------|
| **CFO** | Revenue, Cost, Margin, Cash, Risk | All |
| **CRO** | Account, Opportunity, Pipeline, Churn | All except FinOps |
| **COO** | Usage, Health, SLAs, Incidents | NLQ, DCL, Platform |
| **CTO** | Assets, CloudResources, TechDebt | All |
| **People/HR** | Headcount, Benefits, Org Structure | NLQ only |

### Persona Metrics by Module

**CFO (All Modules):**
Revenue, Gross Margin, Operating Margin, Net Income, Cash, ARR, Burn Multiple

**CRO (Most Modules):**
Pipeline, Win Rate, Churn, NRR, Sales Cycle, Quota Attainment

**COO (NLQ, DCL):**
Headcount, Rev/Employee, Magic Number, CAC Payback, LTV/CAC

**CTO (All Modules):**
Uptime, Deploy Frequency, MTTR, Velocity, Tech Debt, Code Coverage

**People (NLQ Only):**
Headcount, Hires, Attrition, Benefits, PTO, Org Structure

---

## Platform Integration Patterns

### AOA Architecture (LangGraph + MCP)

```python
# Agent execution via LangGraph
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

workflow = StateGraph(AgentState)
workflow.add_node("reason", reasoning_node)
workflow.add_node("tools", tool_node)
workflow.add_node("human_review", human_interrupt_node)

app = workflow.compile(
    checkpointer=PostgresSaver.from_conn_string(DATABASE_URL),
    interrupt_before=["human_review"]
)
```

### MCP Servers (The Data Moat)

AOS exposes data services as MCP servers:

```python
# aos-dcl MCP server
@server.list_tools()
async def list_tools():
    return [
        Tool(name="query_data", ...),
        Tool(name="get_schema", ...),
        Tool(name="explain_field", ...),
        Tool(name="trace_lineage", ...),
    ]

# aos-aam MCP server
@server.list_tools()
async def list_tools():
    return [
        Tool(name="list_connections", ...),
        Tool(name="get_connection_health", ...),
        Tool(name="trigger_sync", _aos_requires_approval=True, ...),
        Tool(name="get_drift_report", ...),
    ]
```

### HITL (Human-in-the-Loop) Pattern

```python
# Recommendations with safety flags
{
    "execution_mode": "hitl" | "autonomous",
    "explain_only": True,   # Show explanation, don't execute
    "dry_run": True         # Simulate, don't commit
}
```

### Feature Flags

| Flag | Module | Purpose |
|------|--------|---------|
| `VITE_USE_PLATFORM_VIEWS` | RevOps | Enable platform Views/Intents |
| `VITE_USE_PLATFORM` | FinOps | General platform flag |
| `USE_AAM_AS_SOURCE` | Platform | Redis-backed feature flag |
| `VITE_CONNECTIONS_V2` | Platform | Frontend connection features |

---

## Identified Inconsistencies

### Critical Issues

| Issue | Modules | Description | Impact | Fix |
|-------|---------|-------------|--------|-----|
| **Backend Language** | FinOps | Node.js vs Python | Code sharing, maintenance | Migrate to FastAPI |
| **React Version** | RevOps | React 19 vs 18 | Stability, compatibility | Downgrade to React 18 |
| **Database Provider** | FinOps | Neon vs Supabase | Unified data access | Standardize on Supabase |
| **People Persona** | DCL, RevOps, FinOps | Missing from most modules | Incomplete coverage | Add People support |

### Module Name Inconsistencies

| Inconsistency | Where | Canonical |
|---------------|-------|-----------|
| AOD = "Asset Observation & Discovery" | AODv3 | ✓ Correct |
| AOD = "AutonomOS Discover" | Farm, some docs | ✗ Outdated |
| DCL = "Data Connectivity Layer" | Most places | ✓ Correct |
| DCL = "Data Contract Library" | Some old refs | ✗ Outdated |

### Architectural Drift

| Pattern | Canonical | Deviations |
|---------|-----------|------------|
| State Management | React hooks | FinOps: TanStack Query |
| Routing | React Router | FinOps: Wouter |
| Charts | Recharts | DCL: D3.js |
| WebSocket | Platform has SSE | FinOps has WebSocket |

### AAM Boundary Issues

Per AAM docs: "AAM does not move or transform data" - but some modules may have blurred this boundary. AAM should:
- ✓ Observe and document integration fabrics
- ✓ Self-heal connectivity issues
- ✗ NOT act as iPaaS replacement
- ✗ NOT build per-app SaaS connectors

---

## Module Details

### AOD - Asset Observation & Discovery

**Purpose**: Discovery engine answering "What software assets does this organization actually use?"

**Core Capabilities**:
- Multi-source discovery (IdP, expense, browser, network, CMDB, cloud)
- Governance classification (Governed, Shadow IT, Zombie)
- Finding generation (Identity Gap, Finance Gap, Data Conflict, Stale Activity)
- Triage workflow (Sanction, Ban, Deprovision)
- System of Record detection
- Fabric Plane detection
- AAM handoff with execution signaling

**Key APIs**:
- `/api/catalog/runs/{run_id}` - Fetch assets
- `/api/triage/data/{run_id}` - Get triage workqueue
- `/api/handoff/aam/candidates` - Export to AAM

---

### AAM - Adaptive API Mesh

**Purpose**: Self-healing integration mesh for enterprise data pipes.

**Core Capabilities**:
- Fabric Plane connectivity (iPaaS, API Gateway, Event Bus, Data Warehouse)
- Pipe discovery and inference
- Schema drift detection
- Self-healing connectivity
- Enterprise maturity presets
- Candidate workflow for new sources

**What AAM Does NOT Do**:
- Move or transform data
- Replace iPaaS
- Build per-app SaaS connectors
- Handle infrastructure operations

**Key Integrations**:
- Workato, MuleSoft (iPaaS)
- Kong, Apigee, AWS API Gateway
- Kafka, EventBridge, Pulsar
- Snowflake, BigQuery, Redshift

---

### DCL - Data Connectivity Layer

**Purpose**: Multi-source schema ingestion, AI-powered ontology unification.

**Core Capabilities**:
- Multi-source schema ingestion (9 legacy + Farm synthetic)
- AI-powered mapping (Gemini, OpenAI)
- RAG with Pinecone
- Interactive Sankey visualization
- Source normalization (34 canonical sources)
- Dev/Prod modes

**Key Concepts**:
- Ontology: Account, Opportunity, Revenue, Cost, Usage, Health
- Entity resolution and canonical streams
- Schema drift detection and repair

---

### NLQ - Natural Language Query

**Purpose**: Conversational interface for business questions.

**Core Capabilities**:
- Natural language understanding
- Galaxy View (visual intent mapping)
- Text View (structured responses)
- Multi-persona dashboards (CFO, CRO, COO, CTO, People)
- Query history and debugging

**Key APIs**:
- `POST /v1/query` - Text response
- `POST /v1/query/galaxy` - Galaxy view

---

### AOA - Agentic Orchestration Architecture

**Purpose**: High-level workflow orchestration for cross-domain playbooks.

**Architecture** (v2.0 - Approved):
- **Runtime**: LangGraph (durable execution, checkpointing)
- **Tools**: Model Context Protocol (MCP)
- **Router**: Reasoning Router (LLM-based, not keyword matching)
- **State**: PostgreSQL via LangGraph Checkpointer
- **Sandbox**: E2B / Firecracker MicroVMs
- **Auth**: On-Behalf-Of (OBO) flows

**MCP Servers**:
- `aos-dcl` - Data queries, schema, lineage
- `aos-aam` - Connections, health, drift
- `aos-aod` - Asset discovery, metadata

---

### Farm - Test Oracle Platform

**Purpose**: Generate synthetic data with known correct answers.

**Modules Served**:
- **AOD**: Enterprise snapshots with intentional anomalies
- **AOA**: Agent fleets and workflow stress scenarios
- **NLQ**: Ground truth scenarios and 100-question bank
- **DCL**: Toxic data streams for ingestion resilience

**Key Features**:
- Deterministic generation (seed-based)
- Chaos injection for stress testing
- Reconciliation scoring

---

### RevOps Agent

**Purpose**: CRM data validation and pipeline health monitoring.

**Core Capabilities**:
- BANT framework validation
- Multi-source joining (Salesforce + Supabase + MongoDB)
- Real-time dashboard with risk analysis
- Slack alerting
- HITL approval workflows

---

### FinOps Agent

**Purpose**: AWS resource analysis and cost-saving recommendations.

**Core Capabilities**:
- Real-time AWS monitoring
- Automated recommendation engine (80% autonomous / 20% HITL)
- Multi-stage approval workflows
- Executive dashboards
- RAG-powered insights

**AWS Integrations**: Cost Explorer, CloudWatch, Trusted Advisor

---

## Recommendations

### Immediate (P0)

1. **Standardize Backend**: Migrate FinOps from Node.js to FastAPI
2. **Unify React**: Lock all modules to React 18.x
3. **Add People Persona**: To DCL, RevOps, FinOps for consistency
4. **Fix Module Names**: AOD = "Asset Observation & Discovery", DCL = "Data Connectivity Layer"

### Short-term (P1)

1. **Shared Design System Package**: Create `@aos/design-system` npm package
2. **Shared Types Package**: Create `@aos/types` for common interfaces
3. **Platform API SDK**: Formalize aosClient into `@aos/platform-sdk`
4. **Unified Testing**: Standardize on pytest + Playwright

### Long-term (P2)

1. **Monorepo**: Consider Turborepo/Nx for shared code
2. **API Gateway**: Unified entry point for all modules
3. **Shared Auth**: Single SSO across modules
4. **Observability**: Unified logging/metrics/tracing

---

## Quick Reference

### Default Ports
| Service | Port |
|---------|------|
| Frontend dev | 5000 |
| Backend API | 8000 |
| Farm API | https://autonomos.farm/ |

### Environment Variables (Common)
```bash
# Database
SUPABASE_URL=
SUPABASE_KEY=
DATABASE_URL=

# AI
ANTHROPIC_API_KEY=      # NLQ
GEMINI_API_KEY=         # DCL, FinOps, Platform
OPENAI_API_KEY=         # DCL, Platform
PINECONE_API_KEY=       # DCL, FinOps

# Integrations
SALESFORCE_USERNAME=
SALESFORCE_PASSWORD=
SALESFORCE_SECURITY_TOKEN=
SLACK_WEBHOOK_URL=
FARM_API_URL=https://autonomos.farm

# Redis (Platform)
UPSTASH_REDIS_URL=
```

### Run Commands
```bash
# Development (Python modules)
npm run dev              # Frontend (port 5000)
uvicorn src.main:app --port 8000  # Backend

# Development (FinOps - Node)
npm run dev              # Full stack

# Production
./start.sh               # Builds frontend, serves via backend
```

---

## Document History

| Date | Change |
|------|--------|
| 2026-01-28 | Initial consolidated document |
| 2026-01-28 | Added AOD, AAM, Platform details after repos made public |
