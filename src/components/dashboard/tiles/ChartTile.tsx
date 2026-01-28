import React from 'react';
import { ChartType } from '../../../types/dashboard';

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
    <div className="space-y-2">
      {data.map((item, index) => (
        <div
          key={item.label}
          className="flex items-center gap-3 cursor-pointer hover:bg-slate-700/30 rounded p-1 -mx-1 transition-colors"
          onClick={() => onClick?.(item.label)}
        >
          <span className="text-slate-400 text-xs w-24 truncate">{item.label}</span>
          <div className="flex-1 h-4 bg-slate-700 rounded overflow-hidden">
            <div
              className="h-full rounded transition-all duration-300"
              style={{
                width: `${(item.value / maxValue) * 100}%`,
                backgroundColor: colors[index % colors.length],
              }}
            />
          </div>
          <span className="text-slate-300 text-xs font-mono w-16 text-right">
            {formatNumber(item.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

/**
 * Simple vertical bar chart implementation
 */
const BarChart: React.FC<{
  data: Array<{ label: string; value: number }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  const maxValue = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="flex items-end justify-around h-32 gap-1">
      {data.map((item, index) => (
        <div
          key={item.label}
          className="flex flex-col items-center flex-1 cursor-pointer group"
          onClick={() => onClick?.(item.label)}
        >
          <span className="text-slate-400 text-xs mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {formatNumber(item.value)}
          </span>
          <div
            className="w-full rounded-t transition-all duration-300 group-hover:opacity-80"
            style={{
              height: `${(item.value / maxValue) * 100}%`,
              backgroundColor: colors[index % colors.length],
              minHeight: '4px',
            }}
          />
          <span className="text-slate-500 text-xs mt-1 truncate max-w-full">
            {item.label}
          </span>
        </div>
      ))}
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
 * Simple waterfall chart implementation
 */
const WaterfallChart: React.FC<{
  data: Array<{ label: string; value: number; type?: 'increase' | 'decrease' | 'total' }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  // Calculate running total and positions
  let runningTotal = 0;
  const chartData = data.map((item, index) => {
    const isTotal = item.type === 'total' || index === 0 || index === data.length - 1;
    const start = isTotal ? 0 : runningTotal;
    const height = Math.abs(item.value);

    if (!isTotal) {
      runningTotal += item.value;
    } else if (index === 0) {
      runningTotal = item.value;
    }

    return {
      ...item,
      start,
      height,
      isPositive: item.value >= 0,
      isTotal,
    };
  });

  const maxValue = Math.max(...chartData.map((d) => d.start + d.height), 1);

  return (
    <div className="flex items-end justify-around h-32 gap-1">
      {chartData.map((item) => (
        <div
          key={item.label}
          className="flex flex-col items-center flex-1 cursor-pointer group relative h-full"
          onClick={() => onClick?.(item.label)}
        >
          <div className="absolute bottom-6 w-full flex flex-col-reverse" style={{ height: 'calc(100% - 24px)' }}>
            <div
              className="w-full rounded transition-all duration-300 group-hover:opacity-80"
              style={{
                marginBottom: `${(item.start / maxValue) * 100}%`,
                height: `${(item.height / maxValue) * 100}%`,
                backgroundColor: item.isTotal
                  ? colors[0]
                  : item.isPositive
                    ? '#10B981'
                    : '#EF4444',
                minHeight: '4px',
              }}
            />
          </div>
          <span className="absolute bottom-0 text-slate-500 text-xs truncate max-w-full">
            {item.label}
          </span>
        </div>
      ))}
    </div>
  );
};

/**
 * Simple stacked bar chart implementation
 */
const StackedBarChart: React.FC<{
  data: Array<{ label: string; values: Array<{ name: string; value: number }> }>;
  onClick?: (label: string) => void;
  colors: string[];
}> = ({ data, onClick, colors }) => {
  const maxTotal = Math.max(
    ...data.map((d) => d.values.reduce((sum, v) => sum + v.value, 0)),
    1
  );

  return (
    <div className="flex items-end justify-around h-32 gap-1">
      {data.map((item) => {
        const total = item.values.reduce((sum, v) => sum + v.value, 0);
        return (
          <div
            key={item.label}
            className="flex flex-col items-center flex-1 cursor-pointer group"
            onClick={() => onClick?.(item.label)}
          >
            <div
              className="w-full flex flex-col-reverse rounded-t overflow-hidden transition-all duration-300 group-hover:opacity-80"
              style={{ height: `${(total / maxTotal) * 100}%`, minHeight: '4px' }}
            >
              {item.values.map((segment, segmentIndex) => (
                <div
                  key={segment.name}
                  style={{
                    height: `${(segment.value / total) * 100}%`,
                    backgroundColor: colors[segmentIndex % colors.length],
                  }}
                />
              ))}
            </div>
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
 * Format a number for display
 */
function formatNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(1)}B`;
  } else if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  } else if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}

/**
 * Normalize data from various formats to a standard format
 */
function normalizeChartData(data: any): Array<{ label: string; value: number }> {
  if (!data) return [];

  // Handle array of objects with label/value
  if (Array.isArray(data)) {
    return data.map((item) => ({
      label: item.label || item.name || item.category || String(item.key || ''),
      value: Number(item.value) || 0,
    }));
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
}) => {
  // Show loading skeleton
  if (loading) {
    return <ChartSkeleton height={height} />;
  }

  // Normalize chart data
  const normalizedData = normalizeChartData(data);

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
        // For stacked bar, we need a different data format
        // If the data doesn't match, fall back to regular bar
        if (normalizedData[0] && 'values' in normalizedData[0]) {
          return (
            <StackedBarChart
              data={normalizedData as any}
              onClick={onClick}
              colors={colorPalette}
            />
          );
        }
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
      <h3 className="text-slate-200 font-semibold text-sm mb-4">{title}</h3>
      <div className="flex-1">{renderChart()}</div>
    </div>
  );
};

export default ChartTile;
