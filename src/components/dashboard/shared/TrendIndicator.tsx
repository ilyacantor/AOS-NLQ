import React from 'react';

interface TrendIndicatorProps {
  direction: 'up' | 'down' | 'flat';
  value: number;  // percentage change
  isPositive: boolean;  // Is this direction good?
  format?: 'percent' | 'pp';  // percentage points for margins
}

export const TrendIndicator: React.FC<TrendIndicatorProps> = ({
  direction,
  value,
  isPositive,
  format = 'percent'
}) => {
  // Determine if the trend is favorable
  // Green if (up && isPositive) || (down && !isPositive)
  // Red if (up && !isPositive) || (down && isPositive)
  const isFavorable =
    (direction === 'up' && isPositive) ||
    (direction === 'down' && !isPositive);

  const isUnfavorable =
    (direction === 'up' && !isPositive) ||
    (direction === 'down' && isPositive);

  // Color classes
  const colorClass = direction === 'flat'
    ? 'text-slate-400'
    : isFavorable
      ? 'text-green-400'
      : isUnfavorable
        ? 'text-red-400'
        : 'text-slate-400';

  // Arrow indicator
  const arrow = direction === 'up'
    ? '▲'
    : direction === 'down'
      ? '▼'
      : '―';

  // Format the value
  const formattedValue = format === 'pp'
    ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}pp`
    : `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;

  return (
    <span className={`inline-flex items-center gap-1 text-sm font-medium ${colorClass}`}>
      <span className="text-xs">{arrow}</span>
      <span>{formattedValue}</span>
    </span>
  );
};

export default TrendIndicator;
