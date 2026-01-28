import React, { useState, useMemo } from 'react';

interface StackedBarChartProps {
  data: Array<{
    label: string;
    segments: Array<{
      label: string;
      value: number;
      color?: string;
    }>;
  }>;
  onClick?: (bucket: string) => void;
  loading?: boolean;
}

// Default colors for AR Aging buckets
const DEFAULT_COLORS = ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6'];

const StackedBarChart: React.FC<StackedBarChartProps> = ({
  data,
  onClick,
  loading = false,
}) => {
  const [hoveredBar, setHoveredBar] = useState<{
    barIndex: number;
    segmentIndex: number;
  } | null>(null);

  const chartData = useMemo(() => {
    if (!data || data.length === 0)
      return { bars: [], maxValue: 0, segmentLabels: [] };

    // Get all unique segment labels
    const segmentLabelsSet = new Set<string>();
    data.forEach((bar) => {
      bar.segments.forEach((seg) => segmentLabelsSet.add(seg.label));
    });
    const segmentLabels = Array.from(segmentLabelsSet);

    // Create color map for segments
    const segmentColors: Record<string, string> = {};
    segmentLabels.forEach((label, i) => {
      segmentColors[label] = DEFAULT_COLORS[i % DEFAULT_COLORS.length];
    });

    const bars = data.map((bar, barIndex) => {
      const total = bar.segments.reduce((sum, seg) => sum + seg.value, 0);
      let currentOffset = 0;

      const segments = bar.segments.map((seg, segIndex) => {
        const result = {
          ...seg,
          segIndex,
          color: seg.color || segmentColors[seg.label],
          offset: currentOffset,
          percentage: total > 0 ? (seg.value / total) * 100 : 0,
        };
        currentOffset += result.percentage;
        return result;
      });

      return {
        label: bar.label,
        barIndex,
        total,
        segments,
      };
    });

    const maxValue = Math.max(...bars.map((b) => b.total), 0);

    return { bars, maxValue, segmentLabels, segmentColors };
  }, [data]);

  const formatValue = (value: number): string => {
    if (Math.abs(value) >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else if (Math.abs(value) >= 1000) {
      return `$${(value / 1000).toFixed(0)}K`;
    }
    return `$${value.toFixed(0)}`;
  };

  if (loading) {
    return (
      <div className="w-full bg-slate-800 rounded-lg p-4 animate-pulse">
        <div className="flex items-end justify-around h-48 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex-1 flex flex-col gap-0.5">
              {[...Array(3)].map((_, j) => (
                <div
                  key={j}
                  className="bg-slate-700 rounded-sm"
                  style={{ height: `${20 + Math.random() * 30}%` }}
                />
              ))}
            </div>
          ))}
        </div>
        <div className="flex justify-around mt-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-3 w-16 bg-slate-700 rounded" />
          ))}
        </div>
        <div className="flex justify-center gap-6 mt-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-slate-700" />
              <div className="h-3 w-12 bg-slate-700 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="w-full h-64 bg-slate-800 rounded-lg flex items-center justify-center">
        <p className="text-slate-400">No data available</p>
      </div>
    );
  }

  const { bars, maxValue, segmentLabels, segmentColors } = chartData;
  const padding = { top: 30, right: 10, bottom: 40, left: 10 };
  const chartWidth = 100;
  const chartHeight = 100;
  const barWidth = (chartWidth - padding.left - padding.right) / bars.length;
  const barPadding = barWidth * 0.25;
  const availableHeight = chartHeight - padding.top - padding.bottom;

  return (
    <div className="w-full bg-slate-800 rounded-lg p-4">
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        className="w-full h-64"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y-axis grid lines */}
        {[0, 25, 50, 75, 100].map((pct) => {
          const y = padding.top + (availableHeight * (100 - pct)) / 100;
          return (
            <g key={pct}>
              <line
                x1={padding.left}
                y1={y}
                x2={chartWidth - padding.right}
                y2={y}
                stroke="#334155"
                strokeWidth="0.2"
                strokeDasharray={pct === 0 ? 'none' : '1,1'}
              />
              <text
                x={padding.left - 1}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-slate-500 text-[2.5px]"
              >
                {formatValue((maxValue * pct) / 100)}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {bars.map((bar, barIndex) => {
          const x = padding.left + barIndex * barWidth + barPadding / 2;
          const width = barWidth - barPadding;
          const barHeight = maxValue > 0 ? (bar.total / maxValue) * availableHeight : 0;
          const barY = padding.top + availableHeight - barHeight;

          return (
            <g key={barIndex}>
              {/* Stacked segments */}
              {bar.segments
                .slice()
                .reverse()
                .map((segment, reversedIndex) => {
                  const originalIndex = bar.segments.length - 1 - reversedIndex;
                  const segmentHeight = (segment.percentage / 100) * barHeight;
                  const offsetHeight =
                    bar.segments
                      .slice(0, originalIndex)
                      .reduce((sum, s) => sum + (s.percentage / 100) * barHeight, 0);
                  const segmentY =
                    padding.top + availableHeight - offsetHeight - segmentHeight;

                  const isHovered =
                    hoveredBar?.barIndex === barIndex &&
                    hoveredBar?.segmentIndex === originalIndex;

                  return (
                    <rect
                      key={originalIndex}
                      x={x}
                      y={segmentY}
                      width={width}
                      height={Math.max(segmentHeight, 0.5)}
                      fill={segment.color}
                      opacity={
                        hoveredBar === null
                          ? 0.85
                          : isHovered
                          ? 1
                          : 0.4
                      }
                      rx="0.5"
                      className="cursor-pointer transition-opacity duration-150"
                      onMouseEnter={() =>
                        setHoveredBar({ barIndex, segmentIndex: originalIndex })
                      }
                      onMouseLeave={() => setHoveredBar(null)}
                      onClick={() => onClick?.(bar.label)}
                    />
                  );
                })}

              {/* Total value label above bar */}
              <text
                x={x + width / 2}
                y={barY - 2}
                textAnchor="middle"
                className="fill-slate-300 text-[3px] font-medium"
              >
                {formatValue(bar.total)}
              </text>

              {/* X-axis label */}
              <text
                x={x + width / 2}
                y={chartHeight - padding.bottom + 6}
                textAnchor="middle"
                className="fill-slate-400 text-[3px]"
              >
                {bar.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mt-4">
        {segmentLabels.map((label, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 cursor-pointer transition-opacity duration-150 ${
              hoveredBar !== null &&
              data[hoveredBar.barIndex]?.segments[hoveredBar.segmentIndex]
                ?.label !== label
                ? 'opacity-50'
                : ''
            }`}
          >
            <div
              className="w-3 h-3 rounded"
              style={{
                backgroundColor:
                  segmentColors[label] ||
                  DEFAULT_COLORS[i % DEFAULT_COLORS.length],
              }}
            />
            <span className="text-xs text-slate-300">{label}</span>
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {hoveredBar !== null && (
        <div className="mt-4 p-3 bg-slate-900/80 rounded-lg border border-slate-700">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium text-white">
              {bars[hoveredBar.barIndex].label}
            </span>
            <span className="text-sm text-slate-400">
              Total: {formatValue(bars[hoveredBar.barIndex].total)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {bars[hoveredBar.barIndex].segments.map((seg, i) => (
              <div
                key={i}
                className={`flex items-center gap-2 ${
                  hoveredBar.segmentIndex === i
                    ? 'text-white'
                    : 'text-slate-400'
                }`}
              >
                <div
                  className="w-2 h-2 rounded"
                  style={{ backgroundColor: seg.color }}
                />
                <span className="text-xs">
                  {seg.label}: {formatValue(seg.value)} ({seg.percentage.toFixed(1)}%)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default StackedBarChart;
