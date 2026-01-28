import React, { useMemo } from 'react';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  showDot?: boolean;
  strokeWidth?: number;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 80,
  height = 24,
  color = '#3B82F6',
  showDot = true,
  strokeWidth = 1.5
}) => {
  const pathData = useMemo(() => {
    if (!data || data.length < 2) return null;

    const padding = 2;
    const effectiveWidth = width - padding * 2;
    const effectiveHeight = height - padding * 2;

    const minValue = Math.min(...data);
    const maxValue = Math.max(...data);
    const range = maxValue - minValue || 1; // Avoid division by zero

    // Calculate points
    const points = data.map((value, index) => {
      const x = padding + (index / (data.length - 1)) * effectiveWidth;
      const y = padding + effectiveHeight - ((value - minValue) / range) * effectiveHeight;
      return { x, y };
    });

    // Create SVG path
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

  if (!pathData) {
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
      aria-label={`Sparkline showing trend with ${data.length} data points`}
    >
      {/* Main line */}
      <path
        d={pathData.path}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Last value dot */}
      {showDot && (
        <circle
          cx={pathData.lastPoint.x}
          cy={pathData.lastPoint.y}
          r={2.5}
          fill={color}
        />
      )}
    </svg>
  );
};

export default Sparkline;
