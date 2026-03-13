*Last updated: 2026-02-07*

# NLQ - Natural Language Query Engine

## What This Application Does

NLQ is a conversational interface that allows users to ask business and financial questions in plain English. Instead of writing SQL queries or navigating complex dashboards, users simply type questions like "what's the margin?" or "how's pipeline looking?" and receive immediate, intelligent responses.

### Key Capabilities

**Natural Language Understanding**
- Interprets casual business questions (e.g., "churn?", "are we profitable")
- Understands context and intent without requiring precise terminology
- Supports questions across multiple business domains (Finance, Sales, Operations, HR)

**Galaxy View (Visual Intent Mapping)**
- Displays query results as an interactive node-based visualization
- Shows the primary answer along with semantically related metrics
- Color-coded confidence indicators (green = high, yellow = medium, red = low)
- Visualizes relationships between different data points

**Text View (Traditional Response)**
- Returns structured answers with values, units, and time periods
- Shows confidence scores and metric definitions
- Displays parsed intent for transparency

**Query History & Debugging**
- Collapsible right panel tracks all queries in the session
- Debug tab shows raw API response data for technical users
- Click any history item to re-run that query

### Supported Question Types

| Domain | Example Questions |
|--------|------------------|
| CFO/Finance | "what's the margin", "are we profitable", "revenue?" |
| CRO/Sales | "how's pipeline looking", "churn?", "bookings" |
| COO/Operations | "are we efficient", "magic number" |
| CTO/Engineering | "platform stable?", "how's velocity" |
| HR/People | "who is the CEO", "pto days", "401k match" |
| Dashboard | "2025 KPIs", "2025 results" |

### User Interface

- **Header**: NLQ branding with view mode toggle (Galaxy/Text)
- **Query Input**: Central search bar with quick action buttons
- **Results Area**: Galaxy visualization or text response
- **Side Panel**: Collapsible History/Debug panel (collapsed by default)

---

## Technical Architecture

### Technology Stack
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS v4
- **Backend**: FastAPI (Python) with Anthropic Claude integration
- **Database**: Supabase PostgreSQL (external)
- **Deployment**: Single-server architecture (FastAPI serves React static build)

### Project Structure
```
src/
├── App.tsx                 # Main React application
├── index.css               # Tailwind v4 styles
├── components/
│   ├── galaxy/             # Galaxy view visualization components
│   │   ├── index.ts        # Exports
│   │   ├── GalaxyView.tsx  # Main galaxy visualization
│   │   └── types.ts        # TypeScript interfaces
│   └── generated-dashboard/  # Dashboard rendering system
│       └── DashboardRenderer.tsx  # Main dashboard UI (1287 lines)
├── hooks/
│   ├── useDashboardRefinement.ts  # Refinement queue, API calls, messages
│   ├── useDashboardLayout.ts      # Grid layout, resize, auto-arrange
│   └── useDashboardPersistence.ts # Save/load/template localStorage ops
├── types/
│   └── generated-dashboard.ts     # Dashboard TypeScript interfaces
└── nlq/
    ├── main.py             # FastAPI application entry point
    ├── api/
    │   ├── routes.py       # API endpoints (/v1/query, /v1/intent-map)
    │   └── dashboard_routes.py  # Dashboard API endpoints
    ├── core/
    │   └── dashboard_generator.py  # Dashboard schema generation & refinement
    ├── db/
    │   ├── schema.sql      # Supabase table definitions with RLS
    │   └── supabase_persistence.py  # Tenant-aware persistence service
    └── services/
        ├── intent_mapper.py    # Claude-powered intent mapping logic
        └── llm_call_counter.py # Session statistics with persistence
```

### API Endpoints
- `POST /v1/query` - Traditional NLQ response (text view)
- `POST /v1/intent-map` - Galaxy view response with related metrics
- `POST /api/v1/*` - Alias routes for production compatibility

### Design System (AutonomOS)
- **Primary**: Cyan (#0bcad9)
- **Success**: Green (#22c55e)
- **Info**: Blue (#3b82f6)
- **AI/Intelligence**: Purple (#a855f7)
- **Background**: Slate (#020617, #0f172a)
- **Typography**: Quicksand (Google Fonts)

---

## Running the Application

### Development Mode
```bash
# Terminal 1: Start Vite dev server (port 5000)
npm run dev

# Terminal 2: Start FastAPI backend (port 8000)
uvicorn src.nlq.main:app --port 8000
```

### Production (Deployment)
```bash
./start.sh   # Builds React, then starts FastAPI on port 5000
```

The production build serves:
- Static React app at `/`
- API routes at `/v1/*` and `/api/v1/*`

---

## Configuration

### Environment Variables
- `SESSION_SECRET` - Session encryption key
- `AI_INTEGRATIONS_OPENAI_API_KEY` - OpenAI/Anthropic API access (managed by Replit)
- `SUPABASE_URL` - Supabase project URL (optional, for persistence)
- `SUPABASE_KEY` - Supabase service role key (optional, for persistence)

---

## Multi-Tenant Persistence

### Overview
AOS-NLQ includes optional Supabase PostgreSQL persistence for RAG session management. When configured, sessions persist across server restarts and support multi-tenant deployments.

### Tables (src/nlq/db/schema.sql)
| Table | Purpose |
|-------|---------|
| `rag_sessions` | Browser session statistics (LLM calls, cached queries) |
| `rag_cache_entries` | Query-to-intent cache with embeddings |
| `rag_learning_log` | Query execution history for ML training |
| `rag_feedback` | User feedback (thumbs up/down) |

### Tenant Isolation
- Default tenant: `00000000-0000-0000-0000-000000000001` (single-tenant mode)
- All queries include explicit `tenant_id` filtering
- RLS policies defined for future JWT-based multi-tenant auth
- Service role key bypasses RLS (server-side ops)

### Graceful Fallback
When Supabase credentials are not configured:
- System logs warning and continues with in-memory storage
- All functionality works, but sessions don't persist across restarts
- No errors shown to users (graceful degradation)

### Key Files
- `vite.config.ts` - Vite dev server with proxy to backend
- `postcss.config.js` - Tailwind v4 PostCSS configuration
- `pyproject.toml` - Python dependencies and hatchling build config
- `start.sh` - Production startup script

---

## User Preferences
- Dark mode only (no light mode toggle)
- Sidebar collapsed by default on page load
- Default query "2025 results" loads automatically in Galaxy view
- React + Tailwind frontend (NOT Streamlit)

---

## Recent Changes (2026-02-17)
- **Added Data Mode selector**: Navbar dropdown lets users switch between Live (DCL) and Demo (fact_base.json) modes
- **Backend force_local support**: All API endpoints accept `data_mode` parameter; demo mode uses contextvars to bypass DCL and serve local fact_base data
- **Pipeline status adapts to mode**: Shows "Demo" grey dot with local metric count in demo mode, polls DCL in live mode
- **Mobile support**: Data Mode selector also appears in mobile hamburger menu

## Recent Changes (2026-02-07)
- **Fixed REFINEMENT_NO_OP crash**: `refine_dashboard_schema` now returns `(schema, 'noop', reason)` tuple instead of raising exception — treats no-op as success
- **Added refinement_status to API response**: Backend returns `refinement_status` ('applied'|'noop'|'error') and `refinement_reason` fields; frontend handles noop gracefully
- **Normalized widget IDs**: All widget IDs now use `trend_{metric}` convention (fixed remaining `{metric}_trend` pattern in `_generate_full_dashboard`)
- **Extracted useDashboardRefinement hook** (163 lines): Refinement queue, API calls, message handling extracted from DashboardRenderer
- **Extracted useDashboardLayout hook** (223 lines): Grid layout, container resize, auto-arrange with queueMicrotask pattern
- **Extracted useDashboardPersistence hook** (234 lines): Save/load/template localStorage operations
- **DashboardRenderer reduced from 1743 to 1287 lines** via hook extraction
- **Fixed all LSP errors**: Resolved TypeScript unused vars, Python Optional[str] typing issues
- **Fixed KPI triple-click blank screen bug**: Added concurrency guard to `refineDashboard` — KPI clicks now queue and process sequentially instead of firing concurrent requests
- **Fixed nested setState anti-pattern**: Moved `setLayoutMap` out of `setSchema` updater in `handleAutoArrange` using `queueMicrotask` to prevent layout/schema mismatch
- **Added DashboardErrorBoundary**: React error boundary wraps the dashboard grid, showing a "Reload Dashboard" button instead of a blank screen on rendering errors
- **Improved startup reliability**: Auto-query now waits up to 20 seconds for backend readiness before firing, preventing "Failed to connect to backend" errors

## Recent Changes (2026-02-01)
- **Added API retry logic**: Frontend now retries failed API calls up to 3 times with increasing delays (500ms, 1000ms, 1500ms) to handle backend startup race conditions
- **Fixed dimension pattern**: Added "by sales stage" to DIMENSION_PATTERNS so queries like "show pipeline by sales stage" work correctly
- **Fixed percentage metric aggregation**: Dimensional breakdown data now correctly averages percentage metrics (win_rate, margin, churn, etc.) instead of summing them
- **Implemented Edit Mode toggle**: Dashboard widgets are now clickable/drillable by default; users must click "Edit" to enable drag/resize mode, eliminating the conflict between drag and click interactions

## Recent Changes (2026-01-29)
- **Fixed Supabase persistence connection**: Resolved import path mismatch between `src.nlq...` and `nlq...` paths that caused separate module globals
- **Fixed SUPABASE_API_URL preference**: Both `supabase_persistence.py` and `rag_learning_log.py` now correctly prefer SUPABASE_API_URL over SUPABASE_URL (which may be PostgreSQL connection string)
- Added persona-specific dashboards: CRO (Revenue), COO (Operations), CTO (Technology)
- Created PredictiveLineChart component with Recharts for shadow forecasts
- Added InsightCard component for anomaly storytelling with AI-generated explanations
- Implemented "Chat with this Chart" buttons on KPITile and ChartTile for conversational drill-down
- Added ScenarioModelingPanel for CFO dashboard with interactive sliders and live KPI impact preview
- Fixed all LSP/TypeScript errors in ChartTile (removed unused functions, fixed type issues)
- Integrated all new components into the dashboard rendering pipeline
- **Fixed BREAKDOWN_QUERY issues**: Added fallback metric derivation in executor for "What is driving..." style questions
- Updated LLM prompts with driver-style breakdown query examples
- Added BREAKDOWN_MAPPINGS for revenue, bookings, expenses, margins, pipeline, churn, and other key metrics
- **Improved KPI sparklines**: Replaced squiggly line charts with clean quarterly bar charts (last 4 quarters, current quarter highlighted)
- **Compacted Revenue Bridge**: Reduced from 8x4 to 6x2 grid position, moved insights panel alongside for better space utilization
- **Updated CFO metrics for profitable company**: Replaced startup metrics (Burn Rate, Runway, LTV/CAC, Rule of 40) with Revenue, Gross Margin %, Operating Profit %, Net Income %
- **Refactored Scenario Modeling Panel**: Now shows Revenue, Growth, Gross Margin, Operating Margin with sliders for Revenue Growth, Pricing/Mix, Headcount, OpEx Change

## Recent Changes (2026-01-28)
- Added collapsible sidebar with toggle button
- Set sidebar to collapse by default on load
- Changed heading to "NLQ Natural Language Query"
- Removed dataset reference text
- Fixed API routing for production deployment
- Added dual route prefixes (/v1/* and /api/v1/*)

## Recent Changes (2026-01-27)
- Rebuilt with React + Vite + Tailwind v4 (migrated from Streamlit)
- Implemented single server architecture (FastAPI serves React build)
- Added Galaxy view visualization
- Configured production deployment

---

## Dashboard Personas

| Persona | Focus Area | Key KPIs |
|---------|------------|----------|
| CFO | Finance Overview | Revenue, Gross Margin, Burn Rate, Cash Runway, Rule of 40, LTV/CAC |
| CRO | Revenue Overview | Bookings, Pipeline, Win Rate, Net Revenue Retention |
| COO | Operations Overview | Headcount, Magic Number, LTV/CAC, NPS |
| CTO | Technology Overview | Uptime, Velocity, Deploys/Week, Tech Debt |

### Dashboard Components

- **KPITile**: Key metric cards with sparklines, trend indicators, and chat drill-down
- **ChartTile**: Visualization tiles supporting bar, line, pie, area, stacked-bar, waterfall, and predictive-line charts
- **InsightsTile**: AI-generated insights with anomaly storytelling (enhanced mode uses InsightCard)
- **PredictiveLineChart**: Recharts-based chart with historical (cyan) and forecast (purple dashed) data
- **ScenarioModelingPanel**: CFO-only collapsible panel with sliders for scenario modeling

---

*Last updated: 2026-02-07*
