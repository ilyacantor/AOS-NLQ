/**
 * DashboardRenderer - Schema-driven dashboard rendering
 *
 * This component takes a DashboardSchema and renders it dynamically,
 * supporting conversational refinement through natural language.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  DashboardSchema,
  Widget,
  WidgetData,
  DashboardGenerationResponse,
  DashboardRefinementResponse,
} from '../../types/generated-dashboard';
import { WidgetRenderer } from './WidgetRenderer';

interface DashboardRendererProps {
  /** Initial schema to render (optional - can start empty) */
  initialSchema?: DashboardSchema;
  /** Query that generated the dashboard */
  sourceQuery?: string;
  /** Callback when a drill-down is triggered */
  onDrillDown?: (query: string) => void;
  /** Callback when dashboard is refined */
  onRefinement?: (newSchema: DashboardSchema) => void;
  /** Show refinement input */
  showRefinementInput?: boolean;
}

export function DashboardRenderer({
  initialSchema,
  sourceQuery,
  onDrillDown,
  onRefinement,
  showRefinementInput = true,
}: DashboardRendererProps) {
  const [schema, setSchema] = useState<DashboardSchema | null>(initialSchema || null);
  const [widgetData, setWidgetData] = useState<Record<string, WidgetData>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refinementQuery, setRefinementQuery] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isRefining, setIsRefining] = useState(false);

  // Generate dashboard from query
  const generateDashboard = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/query/dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query }),
      });

      const data: DashboardGenerationResponse = await response.json();

      if (data.success && data.dashboard) {
        setSchema(data.dashboard);
        setSuggestions(data.suggestions || []);
        // Initialize widget data states
        const initialData: Record<string, WidgetData> = {};
        data.dashboard.widgets.forEach(widget => {
          initialData[widget.id] = { loading: true };
        });
        setWidgetData(initialData);
        // Fetch actual data for widgets
        fetchWidgetData(data.dashboard);
      } else {
        setError(data.error || 'Failed to generate dashboard');
        setSuggestions(data.suggestions || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate dashboard');
    } finally {
      setLoading(false);
    }
  }, []);

  // Refine existing dashboard
  const refineDashboard = useCallback(async (query: string) => {
    if (!schema) return;

    setIsRefining(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/dashboard/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dashboard_id: schema.id,
          refinement_query: query,
        }),
      });

      const data: DashboardRefinementResponse = await response.json();

      if (data.success && data.dashboard) {
        setSchema(data.dashboard);
        onRefinement?.(data.dashboard);
        // Re-fetch widget data for updated dashboard
        fetchWidgetData(data.dashboard);
      } else {
        setError(data.error || 'Failed to refine dashboard');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine dashboard');
    } finally {
      setIsRefining(false);
      setRefinementQuery('');
    }
  }, [schema, onRefinement]);

  // Fetch data for all widgets
  const fetchWidgetData = useCallback(async (dashboard: DashboardSchema) => {
    // For MVP, generate mock data based on widget configuration
    // In production, this would query the actual data API
    const newData: Record<string, WidgetData> = {};

    for (const widget of dashboard.widgets) {
      newData[widget.id] = await generateMockWidgetData(widget);
    }

    setWidgetData(newData);
  }, []);

  // Handle widget click (drill-down)
  const handleWidgetClick = useCallback((widget: Widget, value?: string) => {
    const drillDown = widget.interactions.find(i => i.type === 'drill_down' && i.enabled);
    if (drillDown?.drill_down && onDrillDown) {
      const query = drillDown.drill_down.query_template.replace('{value}', value || '');
      onDrillDown(query);
    }
  }, [onDrillDown]);

  // Handle refinement submit
  const handleRefinementSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (refinementQuery.trim()) {
      refineDashboard(refinementQuery.trim());
    }
  };

  // Handle suggestion click
  const handleSuggestionClick = (suggestion: string) => {
    // Extract the query part from the suggestion (after the colon)
    const parts = suggestion.split(':');
    const query = parts.length > 1 ? parts[1].trim().replace(/^'|'$/g, '') : suggestion;
    setRefinementQuery(query);
  };

  // Generate dashboard on mount if sourceQuery provided
  useEffect(() => {
    if (sourceQuery && !schema) {
      generateDashboard(sourceQuery);
    }
  }, [sourceQuery, schema, generateDashboard]);

  // Calculate grid dimensions
  const gridStyle = schema ? {
    display: 'grid',
    gridTemplateColumns: `repeat(${schema.layout.columns}, 1fr)`,
    gap: `${schema.layout.gap}px`,
    padding: `${schema.layout.padding}px`,
  } : {};

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Dashboard Header */}
      {schema && (
        <div className="px-6 py-4 border-b border-slate-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">{schema.title}</h2>
              {schema.description && (
                <p className="text-sm text-slate-400 mt-1">{schema.description}</p>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-slate-500">
                Confidence: <span className="text-cyan-400">{Math.round(schema.confidence * 100)}%</span>
              </span>
              <span className="text-slate-500">
                v{schema.version}
              </span>
              {schema.widgets.length > 0 && (
                <span className="text-slate-500">
                  {schema.widgets.length} widgets
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <svg className="w-8 h-8 animate-spin text-cyan-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p className="text-slate-400">Generating dashboard...</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="m-6 p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
          <p className="text-red-400">{error}</p>
          {suggestions.length > 0 && (
            <div className="mt-3">
              <p className="text-slate-400 text-sm mb-2">Try one of these:</p>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => handleSuggestionClick(s)}
                    className="px-3 py-1 bg-slate-800 border border-slate-700 rounded text-slate-300 text-xs hover:bg-slate-700"
                  >
                    {s.split(':')[0]}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Dashboard Grid */}
      {schema && !loading && (
        <div className="flex-1 overflow-auto">
          <div style={gridStyle}>
            {schema.widgets.map(widget => (
              <WidgetRenderer
                key={widget.id}
                widget={widget}
                data={widgetData[widget.id] || { loading: true }}
                onClick={(value) => handleWidgetClick(widget, value)}
                rowHeight={schema.layout.row_height}
              />
            ))}
          </div>
        </div>
      )}

      {/* Refinement Input */}
      {schema && showRefinementInput && (
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/50">
          <form onSubmit={handleRefinementSubmit} className="flex gap-3">
            <input
              type="text"
              value={refinementQuery}
              onChange={(e) => setRefinementQuery(e.target.value)}
              placeholder="Refine this dashboard... (e.g., 'Add a pipeline KPI', 'Make that a bar chart')"
              className="flex-1 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
              disabled={isRefining}
            />
            <button
              type="submit"
              disabled={isRefining || !refinementQuery.trim()}
              className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isRefining ? 'Refining...' : 'Refine'}
            </button>
          </form>

          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestionClick(suggestion)}
                  className="px-3 py-1 bg-slate-800/50 border border-slate-700/50 rounded-full text-slate-400 text-xs hover:bg-slate-700 hover:text-slate-200 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {/* Refinement History */}
          {schema.refinement_history.length > 0 && (
            <div className="mt-3 text-xs text-slate-500">
              <span>Refinements: </span>
              {schema.refinement_history.map((r, i) => (
                <span key={i}>
                  {i > 0 && ' → '}
                  <span className="text-slate-400">"{r}"</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!schema && !loading && !error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <h3 className="text-lg font-medium text-white mb-2">
              Create a Dashboard with Natural Language
            </h3>
            <p className="text-slate-400 mb-4">
              Describe what you want to see, and I'll build it for you.
            </p>
            <div className="space-y-2 text-sm text-slate-500">
              <p>"Show me revenue by region over time"</p>
              <p>"Create a dashboard with revenue, margin, and pipeline KPIs"</p>
              <p>"Visualize sales trends with ability to drill into reps"</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Mock Data Generation (for MVP)
// =============================================================================

async function generateMockWidgetData(widget: Widget): Promise<WidgetData> {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 300 + Math.random() * 200));

  const metric = widget.data.metrics[0]?.metric || 'revenue';

  // Generate data based on widget type
  switch (widget.type) {
    case 'kpi_card':
      return generateKPIData(metric);
    case 'line_chart':
    case 'area_chart':
      return generateTimeSeriesData(metric, widget.data.time?.granularity || 'quarterly');
    case 'bar_chart':
    case 'horizontal_bar':
      return generateCategoryData(metric, widget.data.dimensions[0]?.dimension);
    case 'stacked_bar':
      return generateStackedData(widget.data.metrics, widget.data.dimensions[0]?.dimension);
    case 'donut_chart':
      return generateDonutData(metric, widget.data.dimensions[0]?.dimension);
    case 'data_table':
      return generateTableData(widget.data.metrics, widget.data.dimensions);
    default:
      return { loading: false };
  }
}

function generateKPIData(metric: string): WidgetData {
  const values: Record<string, { value: number; format: string; trend: number }> = {
    revenue: { value: 200, format: '$200M', trend: 15.2 },
    gross_margin_pct: { value: 65, format: '65.0%', trend: 2.3 },
    net_income: { value: 45, format: '$45M', trend: 18.5 },
    pipeline: { value: 575, format: '$575M', trend: 8.7 },
    churn: { value: 2.5, format: '2.5%', trend: -0.3 },
    nrr: { value: 118, format: '118%', trend: 3.0 },
    headcount: { value: 450, format: '450', trend: 12.5 },
    win_rate: { value: 32, format: '32%', trend: 4.2 },
    quota_attainment: { value: 95.8, format: '95.8%', trend: 5.1 },
    magic_number: { value: 0.9, format: '0.9x', trend: 0.1 },
    ltv_cac: { value: 4.2, format: '4.2x', trend: 0.3 },
    uptime_pct: { value: 99.95, format: '99.95%', trend: 0.02 },
    p1_incidents: { value: 3, format: '3', trend: -2 },
  };

  const data = values[metric] || { value: 100, format: '100', trend: 5.0 };
  const isPositive = data.trend > 0;

  return {
    loading: false,
    value: data.value,
    formatted_value: data.format,
    trend: {
      direction: isPositive ? 'up' : data.trend < 0 ? 'down' : 'flat',
      percent_change: Math.abs(data.trend),
      comparison_label: 'vs prior period',
    },
    sparkline_data: Array.from({ length: 8 }, () => data.value * (0.8 + Math.random() * 0.4)),
  };
}

function generateTimeSeriesData(metric: string, granularity: string): WidgetData {
  const periods = granularity === 'quarterly'
    ? ['Q1 2024', 'Q2 2024', 'Q3 2024', 'Q4 2024', 'Q1 2025', 'Q2 2025', 'Q3 2025', 'Q4 2025']
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const baseValue = metric === 'revenue' ? 40 : metric.includes('pct') ? 60 : 100;
  const growth = 1.05;

  return {
    loading: false,
    categories: periods,
    series: [{
      name: metric,
      data: periods.map((label, i) => ({
        label,
        value: Math.round(baseValue * Math.pow(growth, i) * (0.9 + Math.random() * 0.2) * 10) / 10,
      })),
    }],
  };
}

function generateCategoryData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  const baseValue = metric === 'revenue' ? 50 : 20;

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round(baseValue * (1 - i * 0.15) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    }],
  };
}

function generateStackedData(metrics: Array<{ metric: string }>, _dimension?: string): WidgetData {
  const categories = ['Q1', 'Q2', 'Q3', 'Q4'];

  return {
    loading: false,
    categories,
    series: metrics.slice(0, 3).map((m, mi) => ({
      name: m.metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((30 - mi * 5) * (1 + i * 0.1) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    })),
  };
}

function generateDonutData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((40 - i * 8) * (0.8 + Math.random() * 0.4)),
      })),
    }],
  };
}

function generateTableData(
  metrics: Array<{ metric: string }>,
  dimensions: Array<{ dimension: string }>
): WidgetData {
  const dimension = dimensions[0]?.dimension || 'region';
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    rows: categories.map(cat => {
      const row: Record<string, any> = { [dimension]: cat };
      metrics.forEach(m => {
        const baseValue = m.metric === 'revenue' ? 50 : 20;
        row[m.metric] = Math.round(baseValue * (0.8 + Math.random() * 0.4) * 10) / 10;
      });
      return row;
    }),
  };
}

export default DashboardRenderer;
