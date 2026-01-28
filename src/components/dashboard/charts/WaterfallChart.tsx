import React, { useState, useMemo } from 'react';

interface WaterfallChartProps {
  data: Array<{
    label: string;
    value: number;
    type: 'increase' | 'decrease' | 'total';
  }>;
  onClick?: (segment: string) => void;
  loading?: boolean;
}

const COLORS = {
  increase: '#10B981',
  decrease: '#EF4444',
  total: '#3B82F6',
};

const WaterfallChart: React.FC<WaterfallChartProps> = ({
  data,
  onClick,
  loading = false,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartData = useMemo(() => {
    if (!data || data.length === 0) return { bars: [], maxValue: 0, minValue: 0 };

    let runningTotal = 0;
    const bars = data.map((item, index) => {
      let start: number;
      let end: number;

      if (item.type === 'total') {
        start = 0;
        end = item.value;
        runningTotal = item.value;
      } else if (item.type === 'increase') {
        start = runningTotal;
        end = runningTotal + item.value;
        runningTotal = end;
      } else {
        start = runningTotal - item.value;
        end = runningTotal;
        runningTotal = start;
      }

      return {
        ...item,
        index,
        start: Math.min(start, end),
        end: Math.max(start, end),
        height: Math.abs(end - start),
      };
    });

    const allValues = bars.flatMap((b) => [b.start, b.end]);
    const maxValue = Math.max(...allValues, 0);
    const minValue = Math.min(...allValues, 0);

    return { bars, maxValue, minValue };
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
      <div className="w-full h-64 bg-slate-800 rounded-lg p-4 animate-pulse">
        <div className="flex items-end justify-around h-48 gap-2">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="bg-slate-700 rounded-t"
              style={{
                width: '14%',
                height: `${30 + Math.random() * 50}%`,
              }}
            />
          ))}
        </div>
        <div className="flex justify-around mt-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-3 w-12 bg-slate-700 rounded" />
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

  const { bars, maxValue, minValue } = chartData;
  const range = maxValue - minValue || 1;
  const padding = { top: 30, right: 20, bottom: 60, left: 20 };
  const chartWidth = 100;
  const chartHeight = 100;
  const barWidth = (chartWidth - padding.left - padding.right) / bars.length;
  const barPadding = barWidth * 0.2;

  const scaleY = (value: number): number => {
    return (
      padding.top +
      ((maxValue - value) / range) * (chartHeight - padding.top - padding.bottom)
    );
  };

  const zeroY = scaleY(0);

  return (
    <div className="w-full bg-slate-800 rounded-lg p-4">
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        className="w-full h-64"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Zero line */}
        <line
          x1={padding.left}
          y1={zeroY}
          x2={chartWidth - padding.right}
          y2={zeroY}
          stroke="#475569"
          strokeWidth="0.3"
          strokeDasharray="1,1"
        />

        {/* Bars */}
        {bars.map((bar, i) => {
          const x = padding.left + i * barWidth + barPadding / 2;
          const width = barWidth - barPadding;
          const y = scaleY(bar.end);
          const height = Math.abs(scaleY(bar.start) - scaleY(bar.end)) || 1;
          const isHovered = hoveredIndex === i;

          return (
            <g key={i}>
              {/* Connector line to previous bar */}
              {i > 0 && bar.type !== 'total' && (
                <line
                  x1={padding.left + (i - 1) * barWidth + barWidth - barPadding / 2}
                  y1={scaleY(bars[i - 1].type === 'decrease' ? bars[i - 1].start : bars[i - 1].end)}
                  x2={x}
                  y2={scaleY(bar.type === 'decrease' ? bar.end : bar.start)}
                  stroke="#64748B"
                  strokeWidth="0.2"
                  strokeDasharray="0.5,0.5"
                />
              )}

              {/* Bar */}
              <rect
                x={x}
                y={y}
                width={width}
                height={height}
                fill={COLORS[bar.type]}
                opacity={isHovered ? 1 : 0.85}
                rx="0.5"
                className="cursor-pointer transition-opacity duration-150"
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => onClick?.(bar.label)}
              />

              {/* Value label */}
              <text
                x={x + width / 2}
                y={y - 2}
                textAnchor="middle"
                className="fill-slate-300 text-[3px] font-medium"
              >
                {bar.type === 'decrease' ? '-' : ''}
                {formatValue(bar.value)}
              </text>

              {/* X-axis label */}
              <text
                x={x + width / 2}
                y={chartHeight - padding.bottom + 8}
                textAnchor="middle"
                className="fill-slate-400 text-[2.5px]"
                transform={`rotate(-45, ${x + width / 2}, ${chartHeight - padding.bottom + 8})`}
              >
                {bar.label.length > 10 ? bar.label.substring(0, 10) + '...' : bar.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex justify-center gap-6 mt-4">
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded"
            style={{ backgroundColor: COLORS.increase }}
          />
          <span className="text-xs text-slate-400">Increase</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded"
            style={{ backgroundColor: COLORS.decrease }}
          />
          <span className="text-xs text-slate-400">Decrease</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded"
            style={{ backgroundColor: COLORS.total }}
          />
          <span className="text-xs text-slate-400">Total</span>
        </div>
      </div>

      {/* Tooltip */}
      {hoveredIndex !== null && (
        <div className="absolute bg-slate-900 border border-slate-700 rounded-lg p-2 shadow-lg pointer-events-none">
          <p className="text-sm font-medium text-white">
            {bars[hoveredIndex].label}
          </p>
          <p className="text-sm text-slate-300">
            {formatValue(bars[hoveredIndex].value)}
          </p>
        </div>
      )}
    </div>
  );
};

export default WaterfallChart;
