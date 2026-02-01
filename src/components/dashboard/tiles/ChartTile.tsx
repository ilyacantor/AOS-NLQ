import React from 'react';
import { ChartType } from '../../../types/dashboard';
import ExternalStackedBarChart from '../charts/StackedBarChart';
import PredictiveLineChart from '../charts/PredictiveLineChart';
import { formatCurrency, formatNumber } from '../../../utils/formatters';

/**
 * Props for the ChartTile component
 */
export interface ChartTileProps {
  /** Type of chart to render */
  type: ChartType;
  /** Chart title */
  title: string;
  /** Chart data from API response */
  data: any;
  /** Click handler when a segment/bar is clicked */
  onClick?: (segment: string) => void;
  /** Whether the chart is loading */
  loading?: boolean;
  /** Chart height in pixels */
  height?: number;
  /** Whether to show legend */
  showLegend?: boolean;
  /** Custom color palette */
  colorPalette?: string[];
  /** Callback when chat button is clicked */
  onChat?: (query: string) => void;
  /** Pre-filled chat query for this chart */
  chatQuery?: string;
}

/**
 * Default color palette for charts
 */
const DEFAULT_COLORS = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
];

/**
 * Loading skeleton for charts
 */
const ChartSkeleton: React.FC<{ height: number }> = ({ height }) => (
  <div
    className="bg-slate-800 rounded-xl animate-pulse"
    style={{ height }}
  >
    <div className="p-4">
      <div className="h-5 w-40 bg-slate-700 rounded mb-4" />
      <div className="flex items-end justify-around h-32 gap-2">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="bg-slate-700 rounded-t flex-1"
            style={{ height: `${30 + Math.random() * 70}%` }}
          />
        ))}
      </div>
    </div>
  </div>
);

/**
 * Empty state when no data is available
 */
const EmptyChart: React.FC<{ title: string }> = ({ title }) => (
  <div className="bg-slate-800 rounded-xl p-4 h-full">
    <h3 className="text-slate-200 font-semibold text-sm mb-4">{title}</h3>
    <div className="flex items-center justify-center h-32 text-slate-500 text-sm">
      No data available
    </div>
  </div>
);

/**
 * Simple horizontal bar chart implementation
 */
const HorizontalBarChart: React.FC<{
  data: Array<{ label: string; value: number }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  const maxValue = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="space-y-1 overflow-y-auto h-full" style={{ maxHeight: 'calc(100% - 8px)' }}>
      {data.map((item, index) => (
        <div
          key={item.label}
          className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/30 rounded px-1 py-0.5 -mx-1 transition-colors"
          onClick={() => onClick?.(item.label)}
        >
          <span className="text-slate-400 text-xs w-28 truncate flex-shrink-0">{item.label}</span>
          <div className="flex-1 h-3 bg-slate-700 rounded overflow-hidden min-w-0">
            <div
              className="h-full rounded transition-all duration-300"
              style={{
                width: `${(item.value / maxValue) * 100}%`,
                backgroundColor: colors[index % colors.length],
              }}
            />
          </div>
          <span className="text-slate-300 text-xs font-mono w-14 text-right flex-shrink-0">
            {formatNumber(item.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

/**
 * Simple vertical bar chart implementation
 * Supports optional 'size' property to scale bar heights proportionally
 */
const BarChart: React.FC<{
  data: Array<{ label: string; value: number; size?: number }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  // Check if any item has a 'size' property for proportional height rendering
  const hasSize = data.length > 0 && data.some((d) => typeof d.size === 'number' && d.size > 0);
  const maxSize = hasSize 
    ? Math.max(...data.map((d) => (typeof d.size === 'number' ? d.size : 0)), 1) 
    : Math.max(...data.map((d) => d.value), 1);

  // Calculate the max bar height in pixels (container is 128px minus labels)
  const maxBarHeight = 100; // pixels

  return (
    <div className="flex items-end justify-around h-32 gap-1">
      {data.map((item, index) => {
        const heightValue = hasSize ? (typeof item.size === 'number' ? item.size : 0) : item.value;
        const barHeight = Math.max((heightValue / maxSize) * maxBarHeight, 4); // Min 4px
        
        return (
          <div
            key={item.label}
            className="flex flex-col items-center justify-end flex-1 cursor-pointer group h-full"
            onClick={() => onClick?.(item.label)}
          >
            <span className="text-slate-400 text-xs mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {hasSize ? `${item.value}%` : formatNumber(item.value)}
            </span>
            <div
              className="w-full rounded-t transition-all duration-300 group-hover:opacity-80"
              style={{
                height: `${barHeight}px`,
                backgroundColor: colors[index % colors.length],
              }}
            />
            <span className="text-slate-500 text-xs mt-1 truncate max-w-full">
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Simple donut chart implementation
 */
const DonutChart: React.FC<{
  data: Array<{ label: string; value: number }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  let cumulative = 0;

  // Calculate segments
  const segments = data.map((item, index) => {
    const percentage = (item.value / total) * 100;
    const start = cumulative;
    cumulative += percentage;
    return {
      ...item,
      percentage,
      start,
      end: cumulative,
      color: colors[index % colors.length],
    };
  });

  // Generate SVG arc path
  const createArc = (startAngle: number, endAngle: number, radius: number) => {
    const start = polarToCartesian(50, 50, radius, endAngle);
    const end = polarToCartesian(50, 50, radius, startAngle);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 0 ${end.x} ${end.y}`;
  };

  const polarToCartesian = (cx: number, cy: number, r: number, angle: number) => {
    const rad = ((angle - 90) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  };

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="w-32 h-32">
        {segments.map((segment) => (
          <path
            key={segment.label}
            d={createArc(
              (segment.start / 100) * 360,
              (segment.end / 100) * 360,
              35
            )}
            fill="none"
            stroke={segment.color}
            strokeWidth="20"
            className="cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => onClick?.(segment.label)}
          />
        ))}
        <text
          x="50"
          y="50"
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-slate-200 text-lg font-bold"
          style={{ fontSize: '14px' }}
        >
          {formatNumber(total)}
        </text>
      </svg>
      <div className="flex-1 space-y-1">
        {segments.slice(0, 5).map((segment) => (
          <div
            key={segment.label}
            className="flex items-center gap-2 text-xs cursor-pointer hover:bg-slate-700/30 rounded p-1 -mx-1 transition-colors"
            onClick={() => onClick?.(segment.label)}
          >
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: segment.color }}
            />
            <span className="text-slate-400 flex-1 truncate">{segment.label}</span>
            <span className="text-slate-300 font-mono">
              {segment.percentage.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

/**
 * Waterfall chart colors
 */
const WATERFALL_COLORS = {
  increase: '#10B981', // green
  decrease: '#EF4444', // red
  total: '#3B82F6',    // blue
};

/**
 * Proper waterfall chart implementation with SVG
 * Shows connector lines between bars and proper floating segments
 */
const WaterfallChart: React.FC<{
  data: Array<{ label: string; value: number; type?: 'increase' | 'decrease' | 'total' }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick }) => {
  // Calculate running totals and bar positions
  let runningTotal = 0;
  const chartData = data.map((item, index) => {
    let start: number;
    let end: number;
    const type = (item.type || (item.value >= 0 ? 'increase' : 'decrease')) as 'increase' | 'decrease' | 'total';

    if (type === 'total') {
      start = 0;
      end = item.value;
      runningTotal = item.value;
    } else if (type === 'increase') {
      start = runningTotal;
      end = runningTotal + Math.abs(item.value);
      runningTotal = end;
    } else { // decrease
      end = runningTotal;
      start = runningTotal - Math.abs(item.value);
      runningTotal = start;
    }

    return {
      ...item,
      index,
      type,
      start: Math.min(start, end),
      end: Math.max(start, end),
      barStart: type === 'decrease' ? Math.min(start, end) : Math.min(start, end),
      barEnd: type === 'decrease' ? Math.max(start, end) : Math.max(start, end),
      connectorY: type === 'total' ? end : (type === 'decrease' ? start : end),
    };
  });

  // Calculate scale
  const allValues = chartData.flatMap((d) => [d.start, d.end]);
  const maxValue = Math.max(...allValues, 0);
  const minValue = Math.min(...allValues, 0);
  const range = maxValue - minValue || 1;

  // SVG dimensions
  const padding = { top: 20, right: 10, bottom: 35, left: 10 };
  const chartWidth = 100;
  const chartHeight = 80;
  const barCount = chartData.length;
  const barWidth = (chartWidth - padding.left - padding.right) / barCount;
  const barPadding = barWidth * 0.2;

  const scaleY = (value: number): number => {
    return padding.top + ((maxValue - value) / range) * (chartHeight - padding.top - padding.bottom);
  };


  return (
    <div className="w-full h-full flex flex-col">
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        className="w-full flex-1"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Bars and connectors */}
        {chartData.map((bar, i) => {
          const x = padding.left + i * barWidth + barPadding / 2;
          const width = barWidth - barPadding;
          const y = scaleY(bar.end);
          const height = Math.abs(scaleY(bar.start) - scaleY(bar.end)) || 2;

          return (
            <g key={i}>
              {/* Connector line to next bar */}
              {i < chartData.length - 1 && (
                <line
                  x1={x + width}
                  y1={scaleY(bar.connectorY)}
                  x2={padding.left + (i + 1) * barWidth + barPadding / 2}
                  y2={scaleY(bar.connectorY)}
                  stroke="#475569"
                  strokeWidth="0.3"
                  strokeDasharray="1,0.5"
                />
              )}

              {/* Bar */}
              <rect
                x={x}
                y={y}
                width={width}
                height={height}
                fill={WATERFALL_COLORS[bar.type as keyof typeof WATERFALL_COLORS]}
                rx="0.8"
                className="cursor-pointer hover:opacity-80 transition-opacity"
                onClick={() => onClick?.(bar.label)}
              />

              {/* Value label above bar */}
              <text
                x={x + width / 2}
                y={y - 2}
                textAnchor="middle"
                className="fill-slate-300 font-medium"
                style={{ fontSize: '2.5px' }}
              >
                {bar.type === 'decrease' ? '-' : ''}{formatCurrency(Math.abs(bar.value))}
              </text>

              {/* X-axis label */}
              <text
                x={x + width / 2}
                y={chartHeight - padding.bottom + 5}
                textAnchor="middle"
                className="fill-slate-400"
                style={{ fontSize: '2.5px' }}
              >
                {bar.label.length > 10 ? bar.label.substring(0, 10) : bar.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex justify-center gap-3 mt-1 flex-shrink-0">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded" style={{ backgroundColor: WATERFALL_COLORS.increase }} />
          <span className="text-[10px] text-slate-400">Increase</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded" style={{ backgroundColor: WATERFALL_COLORS.decrease }} />
          <span className="text-[10px] text-slate-400">Decrease</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded" style={{ backgroundColor: WATERFALL_COLORS.total }} />
          <span className="text-[10px] text-slate-400">Total</span>
        </div>
      </div>
    </div>
  );
};



/**
 * Normalize data from various formats to a standard format
 * Preserves special fields like 'type' for waterfall charts and 'size' for proportional bar charts
 */
function normalizeChartData(data: any): Array<{ label: string; value: number; type?: 'increase' | 'decrease' | 'total'; color?: string; size?: number }> {
  if (!data) return [];

  // Handle array of objects with label/value
  if (Array.isArray(data)) {
    return data.map((item) => {
      const normalized: { label: string; value: number; type?: 'increase' | 'decrease' | 'total'; color?: string; size?: number } = {
        label: item.label || item.name || item.category || String(item.key || ''),
        value: Number(item.value) || 0,
      };
      // Preserve type for waterfall charts (increase/decrease/total)
      if (item.type && ['increase', 'decrease', 'total'].includes(item.type)) {
        normalized.type = item.type as 'increase' | 'decrease' | 'total';
      }
      // Preserve color if specified
      if (item.color) {
        normalized.color = item.color;
      }
      // Preserve size for proportional bar charts
      if (item.size !== undefined) {
        normalized.size = Number(item.size) || 0;
      }
      return normalized;
    });
  }

  // Handle object with keys as labels
  if (typeof data === 'object') {
    return Object.entries(data).map(([label, value]) => ({
      label,
      value: Number(value) || 0,
    }));
  }

  return [];
}

/**
 * Check if data is in stacked bar format (has segments array)
 */
function isStackedBarData(data: any): data is Array<{ label: string; segments: Array<{ label: string; value: number }> }> {
  if (!Array.isArray(data) || data.length === 0) return false;
  return data[0] && Array.isArray(data[0].segments);
}


/**
 * ChartTile - Wrapper component that selects the appropriate chart visualization
 *
 * This component receives a chart type and data, then renders the appropriate
 * chart component. It handles loading states, empty data, and provides
 * consistent styling across all chart types.
 */
export const ChartTile: React.FC<ChartTileProps> = ({
  type,
  title,
  data,
  onClick,
  loading = false,
  height = 200,
  // showLegend is available for future use when implementing legend display
  showLegend: _showLegend = true,
  colorPalette = DEFAULT_COLORS,
  onChat,
  chatQuery,
}) => {
  // Show loading skeleton
  if (loading) {
    return <ChartSkeleton height={height} />;
  }

  // Extract chart data from nested structure (rawData may contain { chartData: [...] })
  const rawChartData = data?.chartData || data;

  // Normalize chart data
  const normalizedData = normalizeChartData(rawChartData);

  // Show empty state if no data
  if (!normalizedData || normalizedData.length === 0) {
    return <EmptyChart title={title} />;
  }

  // Render the appropriate chart based on type
  const renderChart = () => {
    switch (type) {
      case 'horizontal-bar':
        return (
          <HorizontalBarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'bar':
        return (
          <BarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'donut':
        return (
          <DonutChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'waterfall':
        return (
          <WaterfallChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'stacked-bar':
        // For stacked bar, use the full-featured external component
        // which supports segments format and has proper tooltips/legend
        if (isStackedBarData(rawChartData)) {
          return (
            <div className="h-full" style={{ minHeight: '200px' }}>
              <ExternalStackedBarChart
                data={rawChartData}
                onClick={onClick}
              />
            </div>
          );
        }
        // Fall back to regular bar if data doesn't have segments
        return (
          <BarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'line':
        // Line chart - render as bar for now (can be enhanced later)
        return (
          <BarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      case 'predictive-line':
        // Check if data contains forecast information
        const hasHistoricalData = Array.isArray(rawChartData) && rawChartData.length > 0;
        const hasForecast = Array.isArray(rawChartData) && rawChartData.some((item: any) => item.forecast !== undefined);
        
        if (hasHistoricalData) {
          const historicalData = Array.isArray(rawChartData) 
            ? rawChartData.map((item: any) => ({
                period: item.period || item.label || item.name || '',
                value: item.value || 0,
              }))
            : [];
          
          const forecastData = hasForecast
            ? rawChartData
                .filter((item: any) => item.forecast !== undefined)
                .map((item: any) => ({
                  period: item.period || item.label || item.name || '',
                  value: item.forecast,
                  confidence: item.confidence,
                }))
            : undefined;

          return (
            <PredictiveLineChart
              title={title}
              historicalData={historicalData}
              forecastData={forecastData}
              onClick={onClick}
              onChat={onChat}
              chatQuery={chatQuery}
              height={height}
              showLegend={true}
            />
          );
        }
        // Fall back to bar chart if no data
        return (
          <BarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );

      default:
        return (
          <BarChart
            data={normalizedData}
            onClick={onClick}
            colors={colorPalette}
          />
        );
    }
  };

  return (
    <div
      className="bg-slate-800 rounded-xl p-4 h-full flex flex-col"
      style={{ minHeight: height }}
    >
      <div className="flex items-center justify-between gap-2 mb-4">
        <h3 className="text-slate-200 font-semibold text-sm">{title}</h3>
        {onChat && chatQuery && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onChat(chatQuery);
            }}
            className="
              px-3
              py-1.5
              text-sm
              text-slate-400
              hover:bg-slate-700/50
              transition-all
              duration-200
              rounded-md
              flex items-center gap-1.5
              focus:outline-none
              flex-shrink-0
            "
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#0bcad9';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'rgb(148, 163, 184)';
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow = '0 0 0 2px rgba(11, 202, 217, 0.5), 0 0 0 4px rgba(1, 6, 23, 1)';
              e.currentTarget.style.outlineStyle = 'none';
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            title="Ask questions about this chart"
            aria-label="Chat about this chart"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span>Chat</span>
          </button>
        )}
      </div>
      <div className="flex-1">{renderChart()}</div>
    </div>
  );
};

export default ChartTile;
