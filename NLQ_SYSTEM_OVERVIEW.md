*Last updated: 2026-02-07*

# NLQ System Overview

## What Is NLQ?

NLQ (Natural Language Query) is a conversational interface for business data. Users type plain-English questions like "what's revenue?" or "how's pipeline looking?" and receive instant, intelligent answers with visualizations. No SQL, no dashboards to navigate, no training required.

The system understands casual phrasing, handles ambiguity, learns from usage, and never shows raw errors to users.

---

## How It Works (Plain English)

### Asking a Question

1. User types a question in the search bar (e.g., "revenue by region")
2. The system figures out what they're asking (intent detection)
3. It checks if it's seen a similar question before (semantic cache)
4. If not cached, it asks an AI model to parse the question
5. It pulls the data from the data layer (DCL)
6. It formats the answer and shows it in the appropriate view

### Three Ways to See Answers

**Galaxy View** - An interactive node-based visualization. The main answer appears as a central node, with related metrics orbiting around it. Color-coded by confidence (green = high, yellow = medium, red = low). Best for exploring how metrics relate to each other.

**Dashboard View** - Full executive dashboards with KPI cards, charts, maps, and tables. Supports multiple personas (CFO, CRO, COO, CTO, CHRO) with pre-built layouts. Dashboards can be refined with follow-up commands like "add pipeline KPI" or "filter to AMER."

**User Guide** - Built-in help explaining how to use the system, accessible via the Guide tab.

### Personas

Each persona sees data through their own lens:

| Persona | Focus | Example KPIs |
|---------|-------|--------------|
| CFO | Finance | Revenue, Gross Margin %, Operating Margin, Net Income |
| CRO | Revenue/Sales | Bookings, Pipeline, Win Rate, Net Revenue Retention |
| COO | Operations | Headcount, Magic Number, LTV/CAC, NPS |
| CTO | Technology | Uptime, Velocity, Deploys/Week, Tech Debt |
| CHRO | People | Headcount, PTO Days, 401k Match, CEO Identity |

The system auto-detects persona from the question content and adjusts its voice accordingly (e.g., CRO says "We're crushing it!" for good news, CFO says "The board will be pleased.").

### Personality System

The system has character. Each persona has distinct voices for:
- Greetings
- Good news delivery
- Bad news delivery
- Uncertain responses
- Off-topic redirects

It also handles:
- **Off-topic queries**: Greetings ("hi"), self-reference ("who are you"), philosophy, small talk
- **Easter eggs**: Business jargon jokes ("synergy" -> "We don't track synergy. We track revenue."), tech humor, pop culture references
- **Stumped responses**: When the system can't find an answer, it admits it with personality rather than showing errors

### Smart Question Understanding

The system handles casual, incomplete, and ambiguous questions:

| What You Type | What It Understands |
|--------------|---------------------|
| "revenue?" | Point query for revenue, current year |
| "margin vs last year" | Comparison query, gross margin, YoY |
| "churn" | Point query for revenue churn |
| "show pipeline by sales stage" | Breakdown query with dimension |
| "2025 KPIs" | Full dashboard generation request |
| "are we profitable" | Maps to net income / operating profit |
| "hi" | Off-topic greeting, responds with personality |

### Dashboard Features

Dashboards are generated dynamically from natural language and include:

- **KPI Cards**: Key metrics with sparklines (quarterly bar charts), trend arrows, and "Chat with this Chart" drill-down
- **Charts**: Line, bar, horizontal bar, stacked bar, area, donut, and predictive line charts
- **Maps**: Interactive world map with revenue bubbles by region (AMER, EMEA, APAC)
- **Data Tables**: Tabular data views
- **Scenario Modeling**: CFO-only panel with sliders for revenue growth, pricing, headcount, and OpEx scenarios
- **Insight Cards**: AI-generated anomaly storytelling
- **Cross-Widget Filtering**: Click a region bar to filter all widgets to that region
- **Edit Mode**: Toggle between view mode (clickable/drillable) and edit mode (drag/resize widgets)
- **Refinement**: Natural language commands to modify existing dashboards

### What It Learns

The system improves over time through:
- **Semantic caching**: Remembers how it parsed previous questions so similar questions are answered instantly without calling the AI
- **Learning log**: Records every query, its parse result, and success/failure for analysis
- **Insufficient data tracking**: Logs when it can't confidently answer a question for future improvement
- **Feedback collection**: Users can give thumbs up/down on answers

---

## Technical Architecture

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS v4 |
| Backend | Python FastAPI |
| LLM | Anthropic Claude (claude-sonnet-4-20250514) |
| Semantic Cache | Pinecone (vector DB) + OpenAI Embeddings (text-embedding-3-small) |
| Persistence | Supabase PostgreSQL (external) |
| Data Layer | DCL v2 (Data Control Layer) with local fact_base.json fallback |
| Charts | Recharts |
| Maps | Leaflet.js with GeoJSON |
| Layout | react-grid-layout (drag/resize in edit mode) |

### Design System (AutonomOS)

| Element | Value |
|---------|-------|
| Primary | Cyan (#0bcad9) |
| Success | Green (#22c55e) |
| Info | Blue (#3b82f6) |
| AI/Intelligence | Purple (#a855f7) |
| Background | Slate (#020617, #0f172a) |
| Font | Quicksand (Google Fonts) |
| Mode | Dark only |

### Project Structure

```
src/
├── App.tsx                          # Main React app, view routing, state management
├── main.tsx                         # React entry point
├── index.css                        # Tailwind v4 global styles
├── vite-env.d.ts                    # Vite type declarations
│
├── hooks/
│   └── useQueryRouter.ts            # Frontend query routing (galaxy vs dashboard)
│
├── types/
│   └── generated-dashboard.ts       # TypeScript types for dashboard schema
│
├── components/
│   ├── UserGuide.tsx                # Built-in user guide
│   │
│   ├── galaxy/                      # Galaxy View components
│   │   ├── GalaxyView.tsx           # Main galaxy node visualization
│   │   ├── GalaxyHeader.tsx         # Galaxy view header
│   │   ├── GalaxyLegend.tsx         # Color-coded confidence legend
│   │   ├── NodeDetailPanel.tsx      # Detail panel for selected node
│   │   ├── NodeTooltip.tsx          # Hover tooltips on nodes
│   │   ├── DashboardModal.tsx       # Modal for dashboard drilldown
│   │   ├── DataTable.tsx            # Tabular data display
│   │   ├── types.ts                 # Galaxy-specific TypeScript types
│   │   └── index.ts                 # Barrel exports
│   │
│   ├── generated-dashboard/         # Dashboard View components
│   │   ├── DashboardRenderer.tsx    # Main dashboard layout + generation/refinement
│   │   ├── WidgetRenderer.tsx       # Routes widget type to chart component
│   │   ├── MapWidget.tsx            # Leaflet world map with revenue bubbles
│   │   └── index.ts                 # Barrel exports
│   │
│   ├── dashboard/                   # Shared dashboard components
│   │   ├── Dashboard.tsx            # Legacy dashboard container
│   │   ├── DashboardGrid.tsx        # Grid layout manager
│   │   ├── charts/                  # Chart components
│   │   │   ├── DonutChart.tsx
│   │   │   ├── HorizontalBarChart.tsx
│   │   │   ├── PredictiveLineChart.tsx
│   │   │   ├── StackedBarChart.tsx
│   │   │   ├── WaterfallChart.tsx
│   │   │   └── index.ts
│   │   ├── shared/                  # Shared UI components
│   │   │   ├── ConfidenceIndicator.tsx
│   │   │   ├── InsightCard.tsx
│   │   │   ├── ScenarioModelingPanel.tsx
│   │   │   ├── Sparkline.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   ├── TimeRangeSelector.tsx
│   │   │   ├── TrendIndicator.tsx
│   │   │   └── index.ts
│   │   ├── tiles/                   # Dashboard tile components
│   │   │   ├── ChartTile.tsx
│   │   │   ├── InsightsTile.tsx
│   │   │   ├── KPITile.tsx
│   │   │   └── NLQBar.tsx
│   │   └── index.ts
│   │
│   └── rag/                         # RAG monitoring components
│       ├── LLMCallCounter.tsx       # Session LLM call statistics
│       ├── InsufficientDataPanel.tsx # Low-confidence query tracker
│       └── index.ts
│
└── nlq/                             # Python backend
    ├── main.py                      # FastAPI entry point, static file serving
    ├── config.py                    # Environment configuration
    ├── __init__.py
    │
    ├── api/                         # API route handlers
    │   ├── routes.py                # Core NLQ endpoints (/v1/query, /v1/query/galaxy, /v1/health, /v1/schema)
    │   ├── dashboard_routes.py      # Dashboard endpoints (/v1/query/dashboard, /v1/dashboard/refine, /v1/dashboard/filter)
    │   ├── rag_routes.py            # RAG cache management endpoints (/rag/*)
    │   └── query_helpers.py         # Shared query processing utilities
    │
    ├── core/                        # Core processing logic
    │   ├── parser.py                # Claude-powered query parsing (NL -> structured ParsedQuery)
    │   ├── executor.py              # Query execution against DCL (ParsedQuery -> QueryResult)
    │   ├── resolver.py              # Metric and period resolution
    │   ├── personality.py           # Persona voices, off-topic handling, easter eggs
    │   ├── ambiguity.py             # Ambiguity detection and clarification prompts
    │   ├── confidence.py            # Confidence scoring for responses
    │   ├── semantic_labels.py       # Semantic labeling for metrics
    │   ├── node_generator.py        # Galaxy view node generation
    │   ├── visualization_intent.py  # Detects "show me a chart" vs "what is X"
    │   ├── dashboard_generator.py   # Generates DashboardSchema from VisualizationRequirements
    │   ├── dashboard_data_resolver.py # Resolves actual data for dashboard widgets
    │   ├── refinement_intent.py     # Parses dashboard refinement commands
    │   ├── superlative_intent.py    # "best", "worst", "top" query handling
    │   └── debug_info.py           # Dashboard generation decision tracking
    │
    ├── knowledge/                   # Static knowledge base
    │   ├── synonyms.py              # Metric & period synonym dictionaries + normalization
    │   ├── schema.py                # Financial metric definitions (type, unit, description)
    │   ├── relations.py             # Metric relationships (related + context metrics for Galaxy)
    │   ├── display.py               # Human-readable display names + domain classification
    │   └── quality.py               # Data quality scores + freshness intervals per metric
    │
    ├── llm/                         # LLM integration
    │   ├── client.py                # ClaudeClient wrapper for Anthropic API
    │   └── prompts.py               # System prompts for query parsing
    │
    ├── models/                      # Pydantic data models
    │   ├── query.py                 # NLQRequest, ParsedQuery, QueryIntent, PeriodType, QueryMode
    │   ├── response.py              # NLQResponse, IntentMapResponse, IntentNode, RelatedMetric
    │   └── dashboard_schema.py      # DashboardSchema, Widget, WidgetData, ChartConfig
    │
    ├── services/                    # Business logic services
    │   ├── dcl_semantic_client.py   # DCL v2 client (data access, metric catalog, resolution)
    │   ├── query_cache_service.py   # Pinecone-based semantic cache (RAG)
    │   ├── tiered_intent.py         # 3-tier intent resolution (cache -> embedding -> LLM)
    │   ├── query_router.py          # Backend query routing logic
    │   ├── metric_embedding_index.py # OpenAI embedding index for metric matching
    │   ├── llm_call_counter.py      # LLM usage tracking per session
    │   ├── rag_learning_log.py      # Query learning log for ML improvement
    │   └── insufficient_data_tracker.py # Tracks low-confidence queries
    │
    └── db/                          # Database layer
        ├── schema.sql               # Supabase table definitions with RLS policies
        └── supabase_persistence.py  # Multi-tenant CRUD operations
```

### API Endpoints

#### Core NLQ

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/query` | Text-mode NLQ response (structured answer with value, unit, confidence) |
| POST | `/v1/query/galaxy` | Galaxy-mode response (central node + related metric nodes) |
| GET | `/v1/health` | System health check (backend, cache, persistence status) |
| GET | `/v1/schema` | Available metrics and periods from DCL catalog |

#### Dashboard

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/query/dashboard` | Generate dashboard schema from natural language |
| POST | `/v1/dashboard/refine` | Refine existing dashboard with NL command |
| GET | `/v1/dashboard/{id}` | Retrieve cached dashboard by ID |
| POST | `/v1/dashboard/filter` | Apply cross-widget filters (e.g., click AMER region) |
| GET | `/v1/dashboard/intent/check` | Check if query would generate visualization (UI hint) |

#### RAG Cache Management

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/rag/session/stats` | LLM call stats for a browser session |
| GET | `/rag/global/stats` | Global LLM call statistics |
| POST | `/rag/session/reset` | Reset session counter |
| GET | `/rag/learning/log` | Recent learning log entries |
| GET | `/rag/learning/stats` | Learning statistics |
| GET | `/rag/learning/log/db` | Learning log from Supabase |
| GET | `/rag/cache/stats` | Pinecone cache statistics |
| DELETE | `/rag/cache/entry` | Delete specific cache entry |
| POST | `/rag/cache/seed` | Seed cache with common queries |
| DELETE | `/rag/cache/clear` | Clear all cached queries |
| GET | `/rag/status` | Combined RAG system status |
| GET | `/rag/insufficient-data/log` | Recent low-confidence queries |
| GET | `/rag/insufficient-data/stats` | Insufficient data statistics |
| DELETE | `/rag/insufficient-data/clear` | Clear insufficient data log |

All core endpoints are also available under `/api/v1/*` prefix for production compatibility.

### Query Processing Pipeline

```
User Question
    │
    ├─1─ Off-topic / Easter Egg Detection
    │    └─ If match → return personality response (no LLM call)
    │
    ├─2─ Frontend Query Router (useQueryRouter)
    │    └─ Pattern matching → route to Galaxy or Dashboard
    │
    ├─3─ Tiered Intent Resolution (backend)
    │    ├─ Tier 1 (Free): Cache lookup, exact metric match, off-topic check
    │    ├─ Tier 2 (Cheap): Embedding similarity against metric index
    │    └─ Tier 3 (Expensive): Full Claude LLM parse
    │
    ├─4─ Query Parsing (if Tier 3)
    │    ├─ Claude extracts: intent, metric, period, comparison
    │    ├─ Synonym normalization (metric + period)
    │    └─ Confidence scoring
    │
    ├─5─ Ambiguity Detection
    │    └─ If ambiguous → return candidates + clarification prompt
    │
    ├─6─ Visualization Intent Detection (for dashboard requests)
    │    ├─ Trigger word scoring (viz vs answer)
    │    ├─ Chart type hinting (line, bar, pie, map, etc.)
    │    └─ Metric/dimension extraction
    │
    ├─7─ Execution
    │    ├─ Galaxy: DCL query → node generation → IntentMapResponse
    │    ├─ Dashboard: Schema generation → data resolution → DashboardSchema
    │    └─ Text: DCL query → personality formatting → NLQResponse
    │
    └─8─ Post-Processing
         ├─ Cache store (if new parse, AI mode)
         ├─ Learning log entry
         ├─ LLM call counter update
         └─ Insufficient data tracking (if low confidence)
```

### Query Intent Types

| Intent | Description | Example |
|--------|-------------|---------|
| POINT_QUERY | Single metric, single period | "What was revenue in 2024?" |
| COMPARISON_QUERY | Compare two periods or growth | "Revenue YoY growth" |
| TREND_QUERY | Metric over multiple periods | "Revenue trend last 4 quarters" |
| AGGREGATION_QUERY | Sum or average over periods | "Total bookings YTD" |
| BREAKDOWN_QUERY | Metric split by dimension | "Revenue by region" |

### Visualization Intent Types

| Intent | Description | Example |
|--------|-------------|---------|
| SINGLE_METRIC_TREND | One metric over time | "Show revenue trend" |
| BREAKDOWN_CHART | Metric by dimension | "Revenue by region" |
| COMPARISON_CHART | Side-by-side comparison | "Compare Q1 vs Q2" |
| DRILL_DOWN_VIEW | Hierarchical exploration | "Drill into AMER revenue" |
| FULL_DASHBOARD | Multi-widget executive view | "Build me a CFO dashboard" |
| SIMPLE_ANSWER | Not a visualization request | "What is margin?" |

### Dashboard Widget Types

| Type | Rendering | Description |
|------|-----------|-------------|
| `kpi_card` | KPICardContent | Key metric with value, trend arrow, sparkline |
| `line_chart` | LineChartContent (Recharts) | Time series line chart |
| `bar_chart` | BarChartContent (Recharts) | Vertical bar chart |
| `horizontal_bar` | HorizontalBarContent (Recharts) | Horizontal bar chart |
| `stacked_bar` | StackedBarContent (Recharts) | Multi-series stacked bar |
| `area_chart` | AreaChartContent (Recharts) | Filled area chart |
| `donut_chart` | DonutChartContent (Recharts) | Pie/donut chart |
| `predictive_line` | PredictiveLineChart | Historical (cyan) + forecast (purple dashed) |
| `map` | MapWidget (Leaflet) | World map with regional revenue bubbles |
| `data_table` | DataTableContent | Sortable tabular data |
| `sparkline` | Sparkline | Compact inline chart |
| `text_block` | TextBlockContent | Free-text or AI insight |
| `filter_control` | FilterControl | Interactive filter widget |
| `time_range_selector` | TimeRangeSelector | Period picker |

### MapWidget Details

- Rendering engine: Leaflet.js
- GeoJSON source: Natural Earth countries (fetched from CDN)
- Ocean background: Solid blue (#1e6091)
- Country fill: Neutral green (#2d4a3e) with region-based tooltip
- Revenue bubbles: L.circleMarker per region
  - Colors: AMER (blue #3b82f6), EMEA (purple #8b5cf6), APAC (amber #f59e0b), LATAM (emerald #10b981)
  - Size: Scaled 10-28px radius proportional to value
  - Opacity: 30% fill
  - White 2px border
  - Custom z-index pane (450) to render above countries
- Tooltips: Region name, formatted revenue, percentage of total
- Drill-down: Click bubble or legend to filter dashboard to that region

### Semantic Cache (RAG)

The system uses Pinecone vector database for semantic caching of parsed queries:

1. **Embedding**: Each query is normalized and embedded using OpenAI's `text-embedding-3-small` model (1536 dimensions)
2. **Storage**: Embeddings stored in Pinecone with metadata (parsed intent, persona, confidence, query text)
3. **Lookup**: New queries are embedded and compared via cosine similarity
4. **Hit Classification**:
   - EXACT (>= 0.97): Use cached parse directly
   - HIGH (>= 0.90): Use cached parse with high confidence
   - PARTIAL (>= 0.80): Use as context for LLM
   - MISS (< 0.80): Full LLM parse required
5. **Modes**:
   - Static: Read-only cache (seed data only)
   - AI: Read + write (learns from new queries)

### Knowledge Base

Static knowledge files that power synonym resolution and metric metadata:

| File | Purpose | Examples |
|------|---------|---------|
| `synonyms.py` | Maps user terms to canonical metric names | "sales" -> "revenue", "top line" -> "revenue" |
| `schema.py` | Metric definitions with type and unit | revenue: currency/USD, gross_margin_pct: percentage |
| `relations.py` | Metric relationships for Galaxy view | revenue relates to bookings, net_income, yoy_growth |
| `display.py` | Human-readable names + domain colors | "gross_margin_pct" -> "Gross Margin", domain: FINANCE |
| `quality.py` | Data quality scores + refresh frequency | revenue: 0.95 quality, 24h freshness |

### Multi-Tenant Persistence (Supabase)

#### Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `tenants` | Organization/tenant registry | id (UUID), name, slug, settings (JSONB) |
| `rag_sessions` | Browser session statistics | tenant_id, session_id, call_count, queries_cached, queries_learned |
| `rag_cache_entries` | Query-to-intent cache | tenant_id, query_hash, original_query, parsed_intent (JSONB), confidence, hit_count |
| `rag_learning_log` | Query execution history | tenant_id, query, success, source, learned, parsed_intent, execution_time_ms |
| `rag_feedback` | User thumbs up/down feedback | tenant_id, session_id, query, rating, comment |

#### Tenant Isolation

- Default tenant: `00000000-0000-0000-0000-000000000001` (single-tenant mode)
- All queries include explicit `tenant_id` filtering at the application level
- Row-Level Security (RLS) policies defined for future JWT-based multi-tenant auth
- Service role key bypasses RLS for server-side operations
- `updated_at` triggers auto-maintain timestamps

#### Graceful Fallback

When Supabase credentials are not configured:
- System logs a warning and continues with in-memory storage
- All functionality works, sessions just don't persist across restarts
- No errors shown to users

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `SESSION_SECRET` | Session encryption key | Yes |
| `SUPABASE_API_URL` | Supabase project REST API URL | Optional (persistence) |
| `SUPABASE_KEY` | Supabase service role key | Optional (persistence) |
| `PINECONE_API_KEY` | Pinecone vector DB key | Optional (semantic cache) |
| `OPENAI_API_KEY` | OpenAI API key for embeddings | Optional (semantic cache) |
| `DCL_API_URL` | DCL v2 API endpoint | Optional (falls back to local fact_base.json) |

### Running the Application

#### Development

```bash
# Terminal 1: Frontend dev server (port 5000, proxies API to 8000)
npm run dev

# Terminal 2: Backend API server (port 8000)
uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000
```

#### Production

```bash
./start.sh   # Builds React -> dist/, then FastAPI serves everything on port 5000
```

Production serves:
- Static React app at `/`
- API routes at `/v1/*` and `/api/v1/*`
- RAG routes at `/rag/*`

### Key Configuration Files

| File | Purpose |
|------|---------|
| `vite.config.ts` | Vite dev server config with proxy to FastAPI backend |
| `postcss.config.js` | Tailwind CSS v4 PostCSS configuration |
| `pyproject.toml` | Python dependencies and hatchling build config |
| `start.sh` | Production startup script (build + serve) |
| `tsconfig.json` | TypeScript configuration |
| `tailwind.config.ts` | Tailwind theme customization |

### Error Handling Philosophy

The system follows a strict "never show errors to users" policy:

1. **API retry**: Frontend retries failed API calls up to 3 times with increasing delays (500ms, 1000ms, 1500ms)
2. **Graceful degradation**: Missing Supabase/Pinecone credentials result in in-memory fallback, not errors
3. **Personality-driven failures**: When the system can't answer, it uses the "stumped" voice ("I don't have that metric right now") rather than error messages
4. **Debug info**: Technical details are captured in debug objects returned alongside responses, visible only in the Debug tab
5. **Strict mode**: Development uses strict mode (fail loudly for debugging); production falls back gracefully

---

*Last updated: 2026-02-07*
