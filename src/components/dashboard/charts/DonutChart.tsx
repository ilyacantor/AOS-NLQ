import React, { useState, useMemo } from 'react';

interface DonutChartProps {
  data: Array<{
    label: string;
    value: number;
    color?: string;
  }>;
  onClick?: (segment: string) => void;
  loading?: boolean;
}

const DEFAULT_COLORS = ['#3B82F6', '#8B5CF6', '#EC4899', '#14B8A6', '#F59E0B'];

const DonutChart: React.FC<DonutChartProps> = ({
  data,
  onClick,
  loading = false,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartData = useMemo(() => {
    if (!data || data.length === 0) return { segments: [], total: 0 };

    const total = data.reduce((sum, item) => sum + item.value, 0);
    let currentAngle = -90; // Start from top

    const segments = data.map((item, index) => {
      const percentage = total > 0 ? (item.value / total) * 100 : 0;
      const angle = (percentage / 100) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angle;
      currentAngle = endAngle;

      return {
        ...item,
        index,
        percentage,
        startAngle,
        endAngle,
        color: item.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      };
    });

    return { segments, total };
  }, [data]);

  const formatValue = (value: number): string => {
    if (Math.abs(value) >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else if (Math.abs(value) >= 1000) {
      return `$${(value / 1000).toFixed(0)}K`;
    }
    return `$${value.toFixed(0)}`;
  };

  const polarToCartesian = (
    centerX: number,
    centerY: number,
    radius: number,
    angleInDegrees: number
  ) => {
    const angleInRadians = (angleInDegrees * Math.PI) / 180.0;
    return {
      x: centerX + radius * Math.cos(angleInRadians),
      y: centerY + radius * Math.sin(angleInRadians),
    };
  };

  const describeArc = (
    x: number,
    y: number,
    innerRadius: number,
    outerRadius: number,
    startAngle: number,
    endAngle: number
  ) => {
    const start = polarToCartesian(x, y, outerRadius, endAngle);
    const end = polarToCartesian(x, y, outerRadius, startAngle);
    const innerStart = polarToCartesian(x, y, innerRadius, endAngle);
    const innerEnd = polarToCartesian(x, y, innerRadius, startAngle);

    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    const d = [
      'M',
      start.x,
      start.y,
      'A',
      outerRadius,
      outerRadius,
      0,
      largeArcFlag,
      0,
      end.x,
      end.y,
      'L',
      innerEnd.x,
      innerEnd.y,
      'A',
      innerRadius,
      innerRadius,
      0,
      largeArcFlag,
      1,
      innerStart.x,
      innerStart.y,
      'Z',
    ].join(' ');

    return d;
  };

  if (loading) {
    return (
      <div className="w-full bg-slate-800 rounded-lg p-4 animate-pulse">
        <div className="flex items-center justify-center">
          <div className="relative w-48 h-48">
            <div className="absolute inset-0 rounded-full border-8 border-slate-700" />
            <div className="absolute inset-8 rounded-full bg-slate-800" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-6 w-16 bg-slate-700 rounded" />
            </div>
          </div>
        </div>
        <div className="flex flex-wrap justify-center gap-4 mt-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-slate-700" />
              <div className="h-3 w-16 bg-slate-700 rounded" />
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

  const { segments, total } = chartData;
  const size = 100;
  const center = size / 2;
  const outerRadius = 40;
  const innerRadius = 25;

  return (
    <div className="w-full bg-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-center">
        <svg
          viewBox={`0 0 ${size} ${size}`}
          className="w-48 h-48 md:w-56 md:h-56"
        >
          {segments.map((segment, i) => {
            const isHovered = hoveredIndex === i;
            const hoverScale = isHovered ? 1.05 : 1;
            const adjustedOuterRadius = outerRadius * hoverScale;

            // Handle full circle case
            if (segment.percentage >= 99.9) {
              return (
                <g key={i}>
                  <circle
                    cx={center}
                    cy={center}
                    r={adjustedOuterRadius}
                    fill={segment.color}
                    opacity={isHovered ? 1 : 0.85}
                    className="cursor-pointer transition-all duration-150"
                    onMouseEnter={() => setHoveredIndex(i)}
                    onMouseLeave={() => setHoveredIndex(null)}
                    onClick={() => onClick?.(segment.label)}
                  />
                  <circle
                    cx={center}
                    cy={center}
                    r={innerRadius}
                    fill="#1e293b"
                    className="pointer-events-none"
                  />
                </g>
              );
            }

            // Skip tiny segments
            if (segment.percentage < 0.5) return null;

            return (
              <path
                key={i}
                d={describeArc(
                  center,
                  center,
                  innerRadius,
                  adjustedOuterRadius,
                  segment.startAngle,
                  segment.endAngle
                )}
                fill={segment.color}
                opacity={isHovered ? 1 : 0.85}
                className="cursor-pointer transition-all duration-150"
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => onClick?.(segment.label)}
              />
            );
          })}

          {/* Center text */}
          <text
            x={center}
            y={center - 3}
            textAnchor="middle"
            className="fill-slate-400 text-[4px] font-medium"
          >
            Total
          </text>
          <text
            x={center}
            y={center + 5}
            textAnchor="middle"
            className="fill-white text-[6px] font-bold"
          >
            {formatValue(total)}
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mt-4">
        {segments.map((segment, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 cursor-pointer transition-opacity duration-150 ${
              hoveredIndex !== null && hoveredIndex !== i ? 'opacity-50' : ''
            }`}
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => onClick?.(segment.label)}
          >
            <div
              className="w-3 h-3 rounded"
              style={{ backgroundColor: segment.color }}
            />
            <span className="text-xs text-slate-300">
              {segment.label} ({segment.percentage.toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {hoveredIndex !== null && (
        <div className="mt-4 text-center">
          <p className="text-sm font-medium text-white">
            {segments[hoveredIndex].label}
          </p>
          <p className="text-lg font-bold text-white">
            {formatValue(segments[hoveredIndex].value)}
          </p>
          <p className="text-xs text-slate-400">
            {segments[hoveredIndex].percentage.toFixed(1)}% of total
          </p>
        </div>
      )}
    </div>
  );
};

export default DonutChart;
