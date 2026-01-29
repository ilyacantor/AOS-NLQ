# Self-Developing Dashboard: Implementation Documentation

## Overview

The Self-Developing Dashboard feature extends the AOS NLQ module to enable users to create, render, and iteratively refine visual dashboards using natural language. Instead of manually configuring dashboards, users describe what they want to see, and the system generates a complete dashboard schema that the frontend renders dynamically.

## Architecture

```
User NL Query
     │
     ▼
┌─────────────────────────────────────┐
│  Visualization Intent Detector      │
│  (visualization_intent.py)          │
│  - Detects viz vs answer intent     │
│  - Extracts metrics, dimensions     │
│  - Identifies chart preferences     │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  Dashboard Schema Generator         │
│  (dashboard_generator.py)           │
│  - Generates widget configurations  │
│  - Sets up data bindings            │
│  - Configures interactions          │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  DashboardSchema JSON               │
│  (Pydantic model)                   │
│  - Widgets, layout, data bindings   │
│  - Interactions, styling            │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  Frontend DashboardRenderer         │
│  (React + Recharts)                 │
│  - Schema-driven rendering          │
│  - Interactive refinement           │
└─────────────────────────────────────┘
```

## Dashboard Schema Specification

### Schema Structure

```json
{
  "id": "dash_abc12345",
  "title": "Revenue by Region",
  "description": "Generated from: Show me revenue by region over time",
  "source_query": "Show me revenue by region over time",
  "layout": {
    "columns": 12,
    "row_height": 80,
    "gap": 16,
    "padding": 24
  },
  "widgets": [...],
  "time_range": {
    "period": "2025",
    "granularity": "quarterly"
  },
  "confidence": 0.92,
  "version": 1,
  "refinement_history": []
}
```

### Widget Types

| Type | Description | Use Case |
|------|-------------|----------|
| `line_chart` | Time series visualization | Trends over time |
| `bar_chart` | Vertical bar chart | Category comparisons |
| `horizontal_bar` | Horizontal bar chart | Ranked lists |
| `stacked_bar` | Stacked bar chart | Part-to-whole over categories |
| `donut_chart` | Donut/pie chart | Composition breakdown |
| `area_chart` | Area chart | Cumulative trends |
| `kpi_card` | Single metric KPI | Key performance indicators |
| `data_table` | Tabular data | Detailed breakdowns |
| `sparkline` | Mini trend line | Inline trends |

### Widget Configuration

```json
{
  "id": "revenue_trend",
  "type": "line_chart",
  "title": "Revenue Over Time",
  "data": {
    "metrics": [
      {
        "metric": "revenue",
        "format": "$0.0M",
        "aggregation": "sum"
      }
    ],
    "dimensions": [],
    "time": {
      "period": "last 8 quarters",
      "granularity": "quarterly"
    }
  },
  "position": {
    "column": 1,
    "row": 1,
    "col_span": 12,
    "row_span": 4
  },
  "chart_config": {
    "show_legend": true,
    "show_grid": true,
    "animate": true
  },
  "interactions": [
    {
      "type": "drill_down",
      "enabled": true,
      "drill_down": {
        "target_dimension": "rep",
        "query_template": "Show me revenue for {value} by rep"
      }
    }
  ]
}
```

## API Endpoints

### POST /v1/query/dashboard

Generate a dashboard schema from a natural language query.

**Request:**
```json
{
  "question": "Show me revenue by region over time",
  "reference_date": "2026-01-29"
}
```

**Response:**
```json
{
  "success": true,
  "dashboard": { ... DashboardSchema ... },
  "query": "Show me revenue by region over time",
  "intent_detected": "breakdown_chart",
  "confidence": 0.92,
  "suggestions": [
    "Add a pipeline KPI: 'Add a pipeline card'",
    "Try a bar chart: 'Make that a bar chart'",
    "Add drill-down: 'Let me drill into reps'"
  ]
}
```

### POST /v1/dashboard/refine

Refine an existing dashboard with a natural language request.

**Request:**
```json
{
  "dashboard_id": "dash_abc12345",
  "refinement_query": "Add a pipeline KPI card"
}
```

**Response:**
```json
{
  "success": true,
  "dashboard": { ... updated DashboardSchema ... },
  "changes_made": ["Added kpi_card: Pipeline"],
  "confidence": 0.85
}
```

### GET /v1/dashboard/intent/check

Check if a query would generate a visualization (useful for UI hints).

**Request:**
```
GET /v1/dashboard/intent/check?question=Show%20me%20revenue%20trend
```

**Response:**
```json
{
  "query": "Show me revenue trend",
  "should_visualize": true,
  "intent": "single_metric_trend",
  "chart_hint": "auto",
  "metrics": ["revenue"],
  "dimensions": [],
  "time_dimension": true,
  "confidence": 0.85
}
```

## Visualization Intent Detection

The system uses keyword-based heuristics to detect visualization intent:

### Visualization Triggers (prioritized)
- "show me" → 0.9
- "visualize" → 0.95
- "dashboard" → 0.99
- "trend", "over time" → 0.85-0.9
- "by region", "breakdown" → 0.85-0.9
- "compare" → 0.85

### Answer Triggers
- "what is/was" → 0.6
- "how much/many" → 0.5
- "are we", "did we" → 0.7
- "who is" → 0.9

### Intent Types

| Intent | Description | Example Query |
|--------|-------------|---------------|
| `SIMPLE_ANSWER` | Just needs a number/answer | "What was revenue in 2024?" |
| `SINGLE_METRIC_TREND` | One metric over time | "Show revenue trend" |
| `BREAKDOWN_CHART` | Metric by dimension | "Revenue by region" |
| `COMPARISON_CHART` | Multiple metrics | "Compare revenue vs margin" |
| `DRILL_DOWN_VIEW` | With drill capability | "Revenue by region, drill into reps" |
| `MULTI_METRIC_DASHBOARD` | Multiple KPIs | "Show me revenue, margin, and pipeline" |
| `FULL_DASHBOARD` | Complete dashboard | "Create a CFO dashboard" |

## Frontend Components

### DashboardRenderer

The main component that renders a dashboard from a schema.

```tsx
<DashboardRenderer
  initialSchema={schema}
  onDrillDown={(query) => handleDrillDown(query)}
  onRefinement={(newSchema) => setSchema(newSchema)}
  showRefinementInput={true}
/>
```

**Props:**
- `initialSchema`: Pre-existing schema to render
- `sourceQuery`: Query to generate dashboard from (if no initialSchema)
- `onDrillDown`: Callback when user clicks drill-down
- `onRefinement`: Callback when dashboard is refined
- `showRefinementInput`: Show the natural language refinement input

### WidgetRenderer

Renders individual widgets based on their type and data.

```tsx
<WidgetRenderer
  widget={widgetConfig}
  data={widgetData}
  onClick={(value) => handleClick(value)}
  rowHeight={80}
/>
```

## Supported Refinement Commands

The system understands these natural language refinements:

| Command Pattern | Action |
|-----------------|--------|
| "Add a {metric} KPI" | Adds a new KPI card |
| "Make that a bar chart" | Changes chart type to bar |
| "Make that a line chart" | Changes chart type to line |
| "Add comparison to last quarter" | Enables period comparison |
| "Filter to {value} only" | Adds static filter |
| "Remove the {widget}" | Removes a widget |
| "Let me drill into {dimension}" | Adds drill-down interaction |

## File Structure

```
src/
├── nlq/
│   ├── api/
│   │   └── dashboard_routes.py      # API endpoints
│   ├── core/
│   │   ├── visualization_intent.py  # Intent detection
│   │   └── dashboard_generator.py   # Schema generation
│   └── models/
│       └── dashboard_schema.py      # Pydantic models
└── (frontend)
    ├── types/
    │   └── generated-dashboard.ts   # TypeScript types
    └── components/
        └── generated-dashboard/
            ├── index.ts
            ├── DashboardRenderer.tsx  # Main renderer
            └── WidgetRenderer.tsx     # Widget renderer
```

## What's Next

### V2 Features (Not Yet Implemented)
1. **Saveable/Shareable Dashboards**: Persist dashboards to database
2. **Real Data Fetching**: Connect widgets to actual data APIs
3. **Claude-Powered Intent**: Use LLM for more accurate intent extraction
4. **Filter Controls**: Interactive filter widgets that propagate
5. **Time Range Controls**: Global time range selector
6. **Dashboard Templates**: Pre-built templates for common use cases
7. **Undo/Redo**: Version history for refinements
8. **Export**: PDF/PNG export of dashboards

### Integration Points
- The dashboard API uses the same fact base as existing NLQ queries
- Drill-down queries switch to the existing Text View
- Design system colors and styling match the existing app

## Example Queries

Try these queries in the Builder view:

1. **Simple Trend**: "Show me revenue over time"
2. **Breakdown**: "Revenue by region"
3. **With Drill-Down**: "Show me revenue by region with ability to drill into reps"
4. **Multi-Metric**: "Create a dashboard with revenue, margin, and pipeline KPIs"
5. **Full Dashboard**: "Build a CFO dashboard"
6. **Comparison**: "Compare revenue vs gross margin quarterly"

## Testing the Feature

1. Start the backend: `uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000`
2. Start the frontend: `npm run dev`
3. Navigate to the app and click "Builder" in the view mode toggle
4. Enter a visualization query like "Show me revenue by region"
5. Use the refinement input to iterate: "Add a pipeline KPI card"
