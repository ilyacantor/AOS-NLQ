/**
 * WidgetRenderer - Renders individual widgets based on their type
 *
 * This component takes a Widget definition and its data, then renders
 * the appropriate visualization component (chart, KPI, table, etc.)
 */

import { useRef, useCallback } from 'react';
import { Widget, WidgetData } from '../../types/generated-dashboard';
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
  rowHeight: number;
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

export function WidgetRenderer({ widget, data, onClick, onDoubleClick, rowHeight }: WidgetRendererProps) {
  // Calculate widget dimensions
  const height = widget.position.row_span * rowHeight - 16; // Account for gap

  // Grid positioning style
  const style = {
    gridColumn: `${widget.position.column} / span ${widget.position.col_span}`,
    gridRow: `${widget.position.row} / span ${widget.position.row_span}`,
  };

  // Handle click vs double-click for KPI cards
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isKPI = widget.type === 'kpi_card';
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  // Single click handler - delayed to allow double-click to cancel
  const handleClick = useCallback(() => {
    if (isKPI && onDoubleClick) {
      // For KPIs, delay single-click to allow double-click detection
      clickTimeoutRef.current = setTimeout(() => {
        clickTimeoutRef.current = null;
        if (hasDrillDown) onClick?.();
      }, 300);
    } else if (hasDrillDown) {
      onClick?.();
    }
  }, [isKPI, hasDrillDown, onClick, onDoubleClick]);

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
      <div style={style} className="bg-slate-900 border border-slate-800 rounded-xl p-4 animate-pulse">
        <div className="h-4 w-1/3 bg-slate-800 rounded mb-4" />
        <div className="h-full bg-slate-800/50 rounded" />
      </div>
    );
  }

  // Error state
  if (data.error) {
    return (
      <div style={style} className="bg-slate-900 border border-red-800/50 rounded-xl p-4">
        <h3 className="text-sm font-medium text-slate-400 mb-2">{widget.title}</h3>
        <p className="text-red-400 text-sm">{data.error}</p>
      </div>
    );
  }

  // Render based on widget type
  const content = renderWidgetContent(widget, data, onClick, height);

  return (
    <div
      className={`h-full bg-slate-900 border border-slate-800 rounded-xl overflow-hidden ${
        hasDrillDown || isKPI ? 'cursor-pointer hover:border-cyan-500/50 transition-colors' : ''
      }`}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      title={isKPI ? 'Double-click to view trend chart' : undefined}
    >
      {content}
    </div>
  );
}

function renderWidgetContent(
  widget: Widget,
  data: WidgetData,
  onClick?: (value?: string) => void,
  height: number = 200
): React.ReactNode {
  switch (widget.type) {
    case 'kpi_card':
      return <KPICardContent widget={widget} data={data} />;
    case 'line_chart':
      return <LineChartContent widget={widget} data={data} height={height} onClick={onClick} />;
    case 'bar_chart':
      return <BarChartContent widget={widget} data={data} height={height} onClick={onClick} />;
    case 'horizontal_bar':
      return <HorizontalBarContent widget={widget} data={data} height={height} onClick={onClick} />;
    case 'area_chart':
      return <AreaChartContent widget={widget} data={data} height={height} />;
    case 'donut_chart':
      return <DonutChartContent widget={widget} data={data} height={height} onClick={onClick} />;
    case 'stacked_bar':
      return <StackedBarContent widget={widget} data={data} height={height} onClick={onClick} />;
    case 'data_table':
      return <DataTableContent widget={widget} data={data} onClick={onClick} />;
    case 'sparkline':
      return <SparklineContent widget={widget} data={data} />;
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
    <div className="p-4 h-full flex flex-col justify-between">
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-1">{widget.title}</h3>
        <div className="flex items-baseline gap-3">
          <span className="text-3xl font-bold text-white">{data.formatted_value}</span>
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
        <div className="h-12 mt-2">
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
  height,
  onClick: _onClick,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const showLegend = widget.chart_config?.show_legend && (data.series?.length || 0) > 1;

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
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
                activeDot={{ r: 6 }}
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
  height,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
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
  height,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
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
  height,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
}) {
  const chartData = data.series?.[0]?.data || [];

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
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
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#0BCAD9"
              fill="#0BCAD9"
              fillOpacity={0.2}
              strokeWidth={2}
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
  height,
  onClick,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
  onClick?: (value?: string) => void;
}) {
  const chartData = data.series?.[0]?.data || [];
  const hasDrillDown = widget.interactions.some(i => i.type === 'drill_down' && i.enabled);

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
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
  height,
  onClick: _onClick,
}: {
  widget: Widget;
  data: WidgetData;
  height: number;
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

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
      <div className="flex-1" style={{ minHeight: height - 80 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
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
        <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
        <p className="text-slate-500 text-sm">No data available</p>
      </div>
    );
  }

  const columns = Object.keys(rows[0]);

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-medium text-slate-400 mb-3">{widget.title}</h3>
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
    <div className="p-4 h-full flex flex-col">
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
