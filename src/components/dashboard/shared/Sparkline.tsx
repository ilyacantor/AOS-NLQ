import React, { useMemo } from 'react';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  showDot?: boolean;
  strokeWidth?: number;
  chartType?: 'line' | 'bar';
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 120,
  height = 40,
  color = '#0bcad9',
  showDot = true,
  strokeWidth = 1.5,
  chartType = 'bar'
}) => {
  const barData = useMemo(() => {
    if (!data || data.length === 0) return null;

    const padding = 4;
    const effectiveWidth = width - padding * 2;
    const effectiveHeight = height - padding * 2;

    const minValue = Math.min(0, ...data);
    const maxValue = Math.max(...data);
    const range = maxValue - minValue || 1;

    const barCount = Math.min(data.length, 4);
    const lastData = data.slice(-barCount);
    const barWidth = (effectiveWidth / barCount) * 0.7;
    const barGap = (effectiveWidth / barCount) * 0.3;

    const bars = lastData.map((value, index) => {
      const barHeight = ((value - minValue) / range) * effectiveHeight;
      const x = padding + index * (barWidth + barGap) + barGap / 2;
      const y = padding + effectiveHeight - barHeight;
      const isLast = index === lastData.length - 1;
      return { x, y, width: barWidth, height: barHeight, value, isLast };
    });

    return { bars, effectiveHeight, padding };
  }, [data, width, height]);

  const lineData = useMemo(() => {
    if (!data || data.length < 2) return null;

    const padding = 4;
    const effectiveWidth = width - padding * 2;
    const effectiveHeight = height - padding * 2;

    const minValue = Math.min(...data);
    const maxValue = Math.max(...data);
    const range = maxValue - minValue || 1;

    const points = data.map((value, index) => {
      const x = padding + (index / (data.length - 1)) * effectiveWidth;
      const y = padding + effectiveHeight - ((value - minValue) / range) * effectiveHeight;
      return { x, y };
    });

    const pathCommands = points.map((point, index) => {
      return index === 0
        ? `M ${point.x} ${point.y}`
        : `L ${point.x} ${point.y}`;
    });

    return {
      path: pathCommands.join(' '),
      lastPoint: points[points.length - 1]
    };
  }, [data, width, height]);

  if (chartType === 'bar' && barData) {
    return (
      <svg
        width={width}
        height={height}
        className="inline-block"
        role="img"
        aria-label={`Bar chart showing ${data.length} quarters of data`}
      >
        {barData.bars.map((bar, index) => (
          <rect
            key={index}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={Math.max(bar.height, 2)}
            rx={2}
            fill={bar.isLast ? color : `${color}88`}
          />
        ))}
      </svg>
    );
  }

  if (!lineData) {
    return (
      <svg
        width={width}
        height={height}
        className="inline-block"
        role="img"
        aria-label="Insufficient data for sparkline"
      >
        <line
          x1={4}
          y1={height / 2}
          x2={width - 4}
          y2={height / 2}
          stroke="#475569"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      </svg>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      className="inline-block"
      role="img"
      aria-label={`Line chart showing trend with ${data.length} data points`}
    >
      <path
        d={lineData.path}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {showDot && (
        <circle
          cx={lineData.lastPoint.x}
          cy={lineData.lastPoint.y}
          r={2.5}
          fill={color}
        />
      )}
    </svg>
  );
};

export default Sparkline;
