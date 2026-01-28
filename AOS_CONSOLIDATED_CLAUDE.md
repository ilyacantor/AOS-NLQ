# AutonomOS (AOS) Platform - Consolidated Technical Reference

> **Last Updated**: 2026-01-28
> **Purpose**: Unified technical documentation across all AOS modules
> **Repos Reviewed**: NLQ, Farm, DCLv2, RevOps Agent, FinOps Agent, autonomos-platform (partial)

---

## Table of Contents
1. [Platform Overview](#platform-overview)
2. [Module Index](#module-index)
3. [Architecture & Tech Stack](#architecture--tech-stack)
4. [Design System](#design-system)
5. [Personas](#personas)
6. [Platform Integration Patterns](#platform-integration-patterns)
7. [Identified Inconsistencies](#identified-inconsistencies)
8. [Module Details](#module-details)
9. [Recommendations](#recommendations)

---

## Platform Overview

**AutonomOS (AOS)** is an enterprise AI-powered operating system for autonomous business operations. The platform consists of interconnected modules that work together to provide data discovery, natural language querying, agent orchestration, data connectivity, and domain-specific AI agents.

### Core Philosophy
- **No "Green-Test Theater"**: Tests must validate real behavior, not cosmetic passes
- **Fail Loudly**: When data is bad, surface errors explicitly (no silent fallbacks)
- **Semantics over Syntax**: Behavior must match real-world meaning
- **Determinism**: Same inputs = same outputs for reproducible testing

---

## Module Index

| Module | Full Name | Purpose | Repo |
|--------|-----------|---------|------|
| **AOA** | AutonomOS Agents | AI agent orchestration & workflows | autonomos-platform |
| **AOD** | AutonomOS Discover | Data discovery & relationship detection | AODv3 |
| **NLQ** | Natural Language Query | Conversational business intelligence | AOS-NLQ |
| **DCL** | Data Connectivity Layer | Multi-source data ingestion & unification | AOS-DCLv2 |
| **AAM** | AutonomOS Asset Manager | Enterprise asset management | AOS_AAM |
| **Farm** | Test Oracle Platform | Synthetic data & ground truth validation | Farmv2 |
| **RevOps Agent** | Revenue Operations Agent | CRM integrity & pipeline health | AOSRevOpsAgent |
| **FinOps Agent** | Financial Operations Agent | Cloud cost optimization | AOSFinOpsAgent |

---

## Architecture & Tech Stack

### Frontend Stack Variations

| Module | React | Build Tool | CSS Framework | UI Library |
|--------|-------|------------|---------------|------------|
| NLQ | 18 | Vite | Tailwind v4 | Custom |
| DCL | 18 | Vite | CSS Modules | D3.js |
| RevOps | 19 | Vite 7 | Tailwind v4 | Custom |
| FinOps | 18 | Vite | Tailwind | Shadcn/Radix |
| Farm | - | - | Tailwind | Vanilla JS |

### Backend Stack Variations

| Module | Framework | Language | Database |
|--------|-----------|----------|----------|
| NLQ | FastAPI | Python | Supabase PostgreSQL |
| DCL | FastAPI | Python | Supabase PostgreSQL + Pinecone |
| Farm | FastAPI | Python | Supabase PostgreSQL |
| RevOps | FastAPI | Python | Supabase PostgreSQL |
| FinOps | Express.js | TypeScript/Node | Neon PostgreSQL |

### AI/LLM Integrations

| Module | Primary LLM | Vector DB | RAG |
|--------|-------------|-----------|-----|
| NLQ | Anthropic Claude | - | No |
| DCL | Gemini 2.5 Flash / OpenAI | Pinecone | Yes |
| FinOps | Gemini 2.5 Flash | Pinecone | Yes |
| Farm | - | - | No |

---

## Design System

### Primary Color Palette (Canonical)

```css
/* Primary Accent */
--aos-cyan: #0BCAD9;        /* Teal/Cyan - Primary interactive color */

/* Backgrounds */
--aos-bg-primary: #000000;   /* Pure black - Main background */
--aos-bg-card: #0A2540;      /* Enterprise blue - Card backgrounds */
--aos-bg-slate: #020617;     /* Slate 950 - Alternative dark bg */
--aos-bg-slate-alt: #0f172a; /* Slate 900 - Lighter dark bg */

/* Borders */
--aos-border: #1E4A6F;       /* Blue border for cards */
--aos-border-slate: #334155; /* Slate 700 - Subtle borders */

/* Text */
--aos-text-primary: #FFFFFF;  /* White - Primary text */
--aos-text-secondary: #A0AEC0; /* Gray - Secondary text */
--aos-text-muted: #64748B;     /* Slate 500 - Muted text */

/* Domain Colors (for multi-persona views) */
--aos-finance: #3B82F6;   /* Blue - CFO */
--aos-growth: #EC4899;    /* Pink - CRO */
--aos-ops: #10B981;       /* Green - COO */
--aos-product: #8B5CF6;   /* Purple - CTO */
--aos-people: #F97316;    /* Orange - People/HR */

/* Status Colors */
--aos-success: #22c55e;   /* Green */
--aos-warning: #f59e0b;   /* Amber */
--aos-error: #ef4444;     /* Red */
--aos-info: #3b82f6;      /* Blue */
```

### Typography
- **Font Family**: Quicksand (Google Fonts) - Primary
- **Monospace**: System monospace for code/values

### Visual Effects
- **Glow Shadows**: `0 0 12px rgba(11, 202, 217, 0.3)` on hover/active
- **Card Shadows**: `0 4px 12px rgba(11, 202, 217, 0.1)`
- **Transitions**: `all 0.2s ease` for interactive elements

---

## Personas

### Supported Personas by Module

| Persona | NLQ | DCL | RevOps | FinOps | Description |
|---------|-----|-----|--------|--------|-------------|
| **CFO** | Yes | Yes | Yes | Yes | Finance, revenue, margins, cash |
| **CRO** | Yes | Yes | Yes | - | Sales, pipeline, churn, NRR |
| **COO** | Yes | Yes | - | - | Operations, efficiency, headcount |
| **CTO** | Yes | Yes | - | - | Engineering, uptime, velocity |
| **People/HR** | Yes | No | - | - | HR, benefits, org structure |

### Persona-Specific Metrics

**CFO**: Revenue, Gross Margin, Operating Margin, Net Income, Cash, ARR, Burn Multiple
**CRO**: Pipeline, Win Rate, Churn, NRR, Sales Cycle, Quota Attainment
**COO**: Headcount, Rev/Employee, Magic Number, CAC Payback, LTV/CAC
**CTO**: Uptime, Deploy Frequency, MTTR, Velocity, Tech Debt, Code Coverage
**People**: Headcount, Hires, Attrition, Benefits, PTO, Org Structure

---

## Platform Integration Patterns

### autonomOS Platform API (agent-kit)

Used by RevOps and FinOps agents for platform-level integration:

```typescript
// Client pattern from aosClient.ts
const client = new AosClient();

// Fetch data via Views
const data = await client.getView('pipeline_health');

// Execute actions via Intents
const result = await client.postIntent('escalate_deal', {
  deal_id: '123',
  reason: 'High risk score',
  idempotency_key: 'unique-key-123'
});
```

### Feature Flags
- `VITE_USE_PLATFORM_VIEWS` - Enable platform Views/Intents integration
- `VITE_USE_PLATFORM` - General platform feature flag

### HITL (Human-in-the-Loop) Pattern
```typescript
// Recommendations with safety flags
{
  execution_mode: 'hitl' | 'autonomous',
  explain_only: true,  // Show explanation, don't execute
  dry_run: true        // Simulate, don't commit changes
}
```

---

## Identified Inconsistencies

### Critical Issues

| Issue | Modules Affected | Description | Recommended Fix |
|-------|-----------------|-------------|-----------------|
| **Backend Language** | FinOps | Uses Node.js while others use Python | Consider migrating to FastAPI for consistency |
| **React Version** | RevOps | Uses React 19 while others use React 18 | Standardize on React 18 (stable) |
| **Tailwind Version** | Various | Mix of Tailwind v3 and v4 | Standardize on Tailwind v4 |
| **Database Provider** | FinOps | Uses Neon while others use Supabase | Document why different or migrate |
| **People Persona** | DCL | Missing People/HR persona | Add People persona support |

### Minor Inconsistencies

| Issue | Details |
|-------|---------|
| **Color naming** | Some use `cyan`, others `teal` - they're the same (#0BCAD9) |
| **Port conventions** | Frontend: 5000, Backend: 8000 (mostly consistent) |
| **Sidebar default** | NLQ collapsed by default, others vary |
| **Font** | Quicksand mentioned in NLQ, others may use system fonts |

### Architectural Drift

| Pattern | Canonical | Deviations |
|---------|-----------|------------|
| **State Management** | React hooks | FinOps uses TanStack Query |
| **Routing** | React Router | FinOps uses Wouter |
| **API Style** | REST | All consistent |
| **Real-time** | WebSocket | FinOps has it, others don't |

---

## Module Details

### NLQ - Natural Language Query Engine

**Purpose**: Conversational interface for business questions in plain English.

**Key Features**:
- Natural language understanding across business domains
- Galaxy View (visual intent mapping with node-based visualization)
- Text View (traditional structured responses)
- Query history and debugging panel
- Multi-persona dashboards

**Tech Stack**: React 18 + Vite + Tailwind v4 + FastAPI + Anthropic Claude

**API Endpoints**:
- `POST /v1/query` - Text response
- `POST /v1/query/galaxy` - Galaxy view with related metrics

---

### Farm - Test Oracle Platform

**Purpose**: Generate synthetic data with known correct answers for testing.

**Modules Served**:
- **AOD Testing**: Enterprise snapshots with intentional anomalies
- **AOA Testing**: Agent fleets and workflow stress scenarios
- **NLQ Testing**: Ground truth business scenarios and question bank
- **DCL Testing**: Toxic data streams for ingestion resilience

**Key Features**:
- Deterministic generation (seed-based reproducibility)
- 100-question test bank for NLQ validation
- Chaos injection for stress testing
- Reconciliation scoring (precision/recall/accuracy)

**Tech Stack**: FastAPI + Python + Supabase PostgreSQL + Vanilla JS

---

### DCL - Data Connectivity Layer

**Purpose**: Multi-source schema ingestion, AI-powered ontology unification, and data flow visualization.

**Key Features**:
- Multi-source schema ingestion (9 legacy + Farm synthetic)
- AI-powered mapping (Gemini, OpenAI)
- RAG with Pinecone for intelligent mapping
- Interactive Sankey diagram visualization
- Source normalization (34 canonical sources)
- Dev/Prod modes (heuristics only vs LLM-enhanced)

**Tech Stack**: React 18 + Vite + D3.js + FastAPI + Pinecone

**Data Modes**:
- **Demo**: Local schemas (Salesforce, HubSpot, MongoDB, etc.)
- **Farm**: Synthetic data from Farm API

---

### RevOps Agent - Revenue Operations Monitor

**Purpose**: CRM data validation and pipeline health monitoring.

**Key Features**:
- BANT framework validation
- Multi-source joining (Salesforce + Supabase + MongoDB)
- Real-time dashboard with risk analysis
- Slack alerting for escalations
- Human-in-the-loop approval workflows

**Tech Stack**: React 19 + Vite 7 + Tailwind v4 + FastAPI

**Data Sources**:
- Salesforce (CRM data)
- Supabase (health scores)
- MongoDB (engagement data - mock)

---

### FinOps Agent - Cloud Cost Optimization

**Purpose**: AWS resource analysis and cost-saving recommendations.

**Key Features**:
- Real-time AWS monitoring
- Automated recommendation engine (80% autonomous / 20% HITL)
- Multi-stage approval workflows
- Executive dashboards
- RAG-powered insights

**Tech Stack**: React 18 + Vite + Shadcn/Radix + Node.js Express + Neon PostgreSQL + Pinecone

**AWS Integrations**:
- Cost Explorer
- CloudWatch
- Trusted Advisor

---

## Recommendations

### Immediate Actions

1. **Standardize Backend**: Migrate FinOps from Node.js to FastAPI for consistency
2. **Unify React Version**: Lock all modules to React 18.x
3. **Design System Package**: Create shared `@aos/design-system` npm package
4. **Add People Persona to DCL**: For consistency with NLQ

### Short-term

1. **Shared Types Package**: Create `@aos/types` for common interfaces
2. **Platform API SDK**: Formalize aosClient into `@aos/platform-sdk`
3. **Unified Testing Framework**: Standardize on pytest + Playwright
4. **Common Deployment Pattern**: Docker + single-server architecture

### Long-term

1. **Monorepo Migration**: Consider Turborepo/Nx for shared code
2. **API Gateway**: Unified entry point for all modules
3. **Shared Auth**: Single SSO across modules
4. **Observability Stack**: Unified logging/metrics/tracing

---

## Quick Reference

### Default Ports
- Frontend dev: 5000
- Backend API: 8000
- Farm API: https://autonomos.farm/

### Environment Variables (Common)
```bash
# Database
SUPABASE_URL=
SUPABASE_KEY=
DATABASE_URL=

# AI
ANTHROPIC_API_KEY=      # NLQ
GEMINI_API_KEY=         # DCL, FinOps
OPENAI_API_KEY=         # DCL
PINECONE_API_KEY=       # DCL, FinOps

# Integrations
SALESFORCE_USERNAME=
SALESFORCE_PASSWORD=
SALESFORCE_SECURITY_TOKEN=
SLACK_WEBHOOK_URL=
FARM_API_URL=https://autonomos.farm
```

### Run Commands
```bash
# Development (most modules)
npm run dev          # Frontend (port 5000)
uvicorn src.main:app --port 8000  # Backend

# Production
./start.sh           # Builds frontend, serves via FastAPI
```

---

## Repos Unable to Access

The following repos returned 404 errors (may be private):
- `autonomos-platform` - AOA (agentic orchestration)
- `AODv3` - AOD (data discovery)
- `AOS_AAM` - Asset management

If these become accessible, this document should be updated with their specifics.
