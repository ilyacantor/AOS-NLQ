/**
 * WidgetRenderer - Renders individual widgets based on their type
 *
 * This component takes a Widget definition and its data, then renders
 * the appropriate visualization component (chart, KPI, table, etc.)
 */

import React, { useRef, useCallback, Component, ReactNode, Suspense } from 'react';
import { Widget, WidgetData } from '../../types/generated-dashboard';

const MapWidget = React.lazy(() => import('./MapWidget'));
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface WidgetRendererProps {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
  onDoubleClick?: (widget: Widget) => void;
}

// Domain colors matching the design system
const CHART_COLORS = [
  '#0BCAD9', // Cyan (primary)
  '#3B82F6', // Blue
  '#EC4899', // Pink
  '#10B981', // Green
  '#8B5CF6', // Purple
  '#F97316', // Orange
  '#EAB308', // Yellow
];

class WidgetErrorBoundary extends Component<
  { widget: Widget; children: ReactNode },
  { hasError: boolean; errorKey: string }
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, errorKey: '' };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  static getDerivedStateFromProps(
    props: { widget: Widget },
    state: { hasError: boolean; errorKey: string }
  ) {
    const currentKey = `${props.widget.id}_${JSON.stringify(props.widget.position)}`;
    if (state.hasError && currentKey !== state.errorKey) {
      return { hasError: false, errorKey: currentKey };
    }
    if (!state.errorKey) {
      return { errorKey: currentKey };
    }
    return null;
  }

  componentDidCatch(error: Error) {
    const currentKey = `${this.props.widget.id}_${JSON.stringify(this.props.widget.position)}`;
    this.setState({ errorKey: currentKey });
    console.warn(`[Widget ${this.props.widget.id}] Render error:`, error.message);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 h-full flex flex-col justify-center items-center bg-slate-900 border border-slate-800 rounded-xl">
          <p className="text-slate-500 text-sm">Widget temporarily unavailable</p>
        </div>
      );
    }
    return this.props.children;
  }
}

export function WidgetRenderer({ widget, data, onClick, onDoubleClick }: WidgetRendererProps) {

  // Handle click vs double-click for KPI cards
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isKPI = widget.type === 'kpi_card';
  const isChart = ['line_chart', 'bar_chart', 'area_chart', 'pie_chart', 'donut_chart', 'stacked_bar'].includes(widget.type);
  const isClickable = isKPI || isChart || widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  // Single click handler - KPIs always clickable, charts pass clicked value
  const handleClick = useCallback((clickedValue?: string) => {
    if (!onClick) return;
    
    if (isKPI) {
      // For KPIs, pass the metric name for drill-down
      const metricName = widget.data.metrics[0]?.metric || widget.title;
      onClick(metricName);
    } else if (isChart && clickedValue) {
      // For charts, pass the clicked value (e.g., bar label)
      onClick(clickedValue);
    } else if (isClickable) {
      onClick(clickedValue);
    }
  }, [isKPI, isChart, isClickable, onClick, widget]);

  // Native double-click handler - cancels pending single-click
  const handleDoubleClick = useCallback(() => {
    if (clickTimeoutRef.current) {
      clearTimeout(clickTimeoutRef.current);
      clickTimeoutRef.current = null;
    }
    if (isKPI && onDoubleClick) {
      onDoubleClick(widget);
    }
  }, [isKPI, widget, onDoubleClick]);

  // Loading state
  if (data.loading) {
    return (
      <div className="h-full bg-slate-900 border border-slate-800 rounded-xl p-4 animate-pulse">
        <div className="h-4 w-1/3 bg-slate-800 rounded mb-4" />
        <div className="flex-1 bg-slate-800/50 rounded" />
      </div>
    );
  }

  // Error state
  if (data.error) {
    return (
      <div className="h-full bg-slate-900 border border-red-800/50 rounded-xl p-4">
        <h3 className="text-sm font-medium text-slate-400 mb-2">{widget.title}</h3>
        <p className="text-red-400 text-sm">{data.error}</p>
      </div>
    );
  }

  // Render based on widget type
  const content = renderWidgetContent(widget, data, onClick);

  return (
    <WidgetErrorBoundary widget={widget}>
      <div
        className={`h-full bg-slate-900 border border-slate-800 rounded-xl overflow-hidden ${
          isClickable ? 'cursor-pointer hover:border-cyan-500/50 transition-colors' : ''
        }`}
        onClick={() => handleClick()}
        onDoubleClick={handleDoubleClick}
        title={isKPI ? 'Click to drill down, double-click for trend' : undefined}
      >
        {content}
      </div>
    </WidgetErrorBoundary>
  );
}

function renderWidgetContent(
  widget: Widget,
  data: WidgetData,
  onClick?: (value?: string) => void,
): React.ReactNode {
  switch (widget.type) {
    case 'kpi_card':
      return <KPICardContent widget={widget} data={data} />;
    case 'line_chart':
      return <LineChartContent widget={widget} data={data} onClick={onClick} />;
    case 'bar_chart':
      return <BarChartContent widget={widget} data={data} onClick={onClick} />;
    case 'horizontal_bar':
      return <HorizontalBarContent widget={widget} data={data} onClick={onClick} />;
    case 'area_chart':
      return <AreaChartContent widget={widget} data={data} onClick={onClick} />;
    case 'donut_chart':
      return <DonutChartContent widget={widget} data={data} onClick={onClick} />;
    case 'stacked_bar':
      return <StackedBarContent widget={widget} data={data} onClick={onClick} />;
    case 'data_table':
      return <DataTableContent widget={widget} data={data} onClick={onClick} />;
    case 'sparkline':
      return <SparklineContent widget={widget} data={data} />;
    case 'map':
      return (
        <Suspense fallback={<div className="animate-pulse h-full bg-slate-800 rounded" />}>
          <MapWidget widget={widget} data={data} height={200} onClick={onClick} />
        </Suspense>
      );
    default:
      return (
        <div className="p-4">
          <p className="text-slate-400">Unsupported widget type: {widget.type}</p>
        </div>
      );
  }
}

// =============================================================================
// KPI Card Component
// =============================================================================

function KPICardContent({ widget, data }: { widget: Widget; data: WidgetData }) {
  const trend = data.trend;
  const showSparkline = widget.kpi_config?.show_sparkline && data.sparkline_data;

  return (
    <div className="p-3 h-full flex flex-col justify-between">
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-1">{widget.title}</h3>
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-bold text-white">{data.formatted_value}</span>
          {trend && widget.kpi_config?.show_trend && (
            <span className={`text-sm font-medium flex items-center gap-1 ${
              trend.direction === 'up' ? 'text-emerald-400' :
              trend.direction === 'down' ? 'text-red-400' : 'text-slate-400'
            }`}>
              {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→'}
              {trend.percent_change.toFixed(1)}%
            </span>
          )}
        </div>
        {trend && (
          <span className="text-xs text-slate-500">{trend.comparison_label}</span>
        )}
      </div>

      {showSparkline && (
        <div className="h-8 mt-1">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.sparkline_data?.map((v, i) => ({ value: v, i }))}>
              <Area
                type="monotone"
                dataKey="value"
                stroke="#0BCAD9"
                fill="#0BCAD9"
                fillOpacity={0.2}
                strokeWidth={1.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Line Chart Component
// =============================================================================

function LineChartContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const showLegend = widget.chart_config?.show_legend && (data.series?.length || 0) > 1;
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart 
            data={chartData}
            onClick={(e) => {
              if (hasDrillDown && e?.activeLabel) {
                onClick?.(String(e.activeLabel));
              }
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
              cursor={hasDrillDown ? { stroke: '#0BCAD9', strokeWidth: 2 } : undefined}
            />
            {showLegend && <Legend />}
            {data.series?.map((series, i) => (
              <Line
                key={series.name}
                type="monotone"
                dataKey="value"
                data={series.data}
                name={series.name}
                stroke={series.color || CHART_COLORS[i % CHART_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 4, fill: series.color || CHART_COLORS[i % CHART_COLORS.length] }}
                activeDot={hasDrillDown ? { r: 8, stroke: '#0BCAD9', strokeWidth: 2, cursor: 'pointer' } : { r: 6 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Bar Chart Component
// =============================================================================

function BarChartContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
              cursor={{ fill: 'rgba(11, 202, 217, 0.1)' }}
            />
            <Bar
              dataKey="value"
              fill="#0BCAD9"
              radius={[4, 4, 0, 0]}
              onClick={(data: { payload?: { label?: string } }) => hasDrillDown && onClick?.(data.payload?.label)}
              cursor={hasDrillDown ? 'pointer' : undefined}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Horizontal Bar Chart Component
// =============================================================================

function HorizontalBarContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <YAxis
              type="category"
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
              width={80}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
            />
            <Bar
              dataKey="value"
              fill="#0BCAD9"
              radius={[0, 4, 4, 0]}
              onClick={(data: { payload?: { label?: string } }) => hasDrillDown && onClick?.(data.payload?.label)}
              cursor={hasDrillDown ? 'pointer' : undefined}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Area Chart Component
// =============================================================================

function AreaChartContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart 
            data={chartData}
            onClick={(e) => {
              if (hasDrillDown && e?.activeLabel) {
                onClick?.(String(e.activeLabel));
              }
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="label"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
              cursor={hasDrillDown ? { stroke: '#0BCAD9', strokeWidth: 2 } : undefined}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#0BCAD9"
              fill="#0BCAD9"
              fillOpacity={0.2}
              strokeWidth={2}
              activeDot={hasDrillDown ? { r: 8, stroke: '#0BCAD9', strokeWidth: 2, cursor: 'pointer' } : undefined}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Donut Chart Component
// =============================================================================

function DonutChartContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius="50%"
              outerRadius="80%"
              paddingAngle={2}
              onClick={(data) => hasDrillDown && onClick?.(data.label)}
              cursor={hasDrillDown ? 'pointer' : undefined}
            >
              {chartData.map((_, index) => (
                <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Stacked Bar Chart Component
// =============================================================================

function StackedBarContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  // Transform series data into stacked format
  const categories = data.categories || [];
  const chartData = categories.map((cat, i) => {
    const point: Record<string, any> = { category: cat };
    data.series?.forEach(series => {
      point[series.name] = series.data[i]?.value || 0;
    });
    return point;
  });
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart 
            data={chartData}
            onClick={(e) => {
              if (hasDrillDown && e?.activeLabel) {
                onClick?.(String(e.activeLabel));
              }
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="category"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#475569' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#f1f5f9' }}
              cursor={hasDrillDown ? { fill: 'rgba(11, 202, 217, 0.1)' } : undefined}
            />
            <Legend
              formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>}
            />
            {data.series?.map((series, i) => (
              <Bar
                key={series.name}
                dataKey={series.name}
                stackId="stack"
                fill={series.color || CHART_COLORS[i % CHART_COLORS.length]}
                radius={i === (data.series?.length || 0) - 1 ? [4, 4, 0, 0] : undefined}
                cursor={hasDrillDown ? 'pointer' : undefined}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// Data Table Component
// =============================================================================

function DataTableContent({
  widget,
  data,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  onClick?: (value?: string) => void;
}) {
  const rows = data.rows || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  if (rows.length === 0) {
    return (
      <div className="p-4">
        <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
        <p className="text-slate-500 text-sm">No data available</p>
      </div>
    );
  }

  const columns = Object.keys(rows[0]);

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-xs font-medium text-slate-400 mb-1.5">{widget.title}</h3>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              {columns.map(col => (
                <th key={col} className="px-3 py-2 text-left text-slate-400 font-medium capitalize">
                  {col.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-slate-800 ${
                  hasDrillDown ? 'hover:bg-slate-800/50 cursor-pointer' : ''
                }`}
                onClick={() => hasDrillDown && onClick?.(row[columns[0]])}
              >
                {columns.map(col => (
                  <td key={col} className="px-3 py-2 text-slate-300">
                    {typeof row[col] === 'number' ? row[col].toFixed(1) : row[col]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =============================================================================
// Sparkline Component
// =============================================================================

function SparklineContent({ widget, data }: { widget: Widget; data: WidgetData }) {
  const sparklineData = data.sparkline_data?.map((v, i) => ({ value: v, i })) || [];

  return (
    <div className="p-3 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-2">{widget.title}</h3>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sparklineData}>
            <Area
              type="monotone"
              dataKey="value"
              stroke="#0BCAD9"
              fill="#0BCAD9"
              fillOpacity={0.2}
              strokeWidth={1.5}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default WidgetRenderer;
