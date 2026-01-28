import React from 'react';

interface ConfidenceIndicatorProps {
  value: number;  // 0-1
  showPercentage?: boolean;
  size?: 'sm' | 'md';
}

export const ConfidenceIndicator: React.FC<ConfidenceIndicatorProps> = ({
  value,
  showPercentage = true,
  size = 'sm'
}) => {
  // Clamp value between 0 and 1
  const clampedValue = Math.max(0, Math.min(1, value));
  const percentage = Math.round(clampedValue * 100);

  // Determine confidence level
  // High (>0.8): green, Medium (0.5-0.8): yellow, Low (<0.5): red
  const level = clampedValue > 0.8
    ? 'high'
    : clampedValue >= 0.5
      ? 'medium'
      : 'low';

  const colorConfig = {
    high: {
      dot: 'bg-green-400',
      text: 'text-green-400',
      label: 'High'
    },
    medium: {
      dot: 'bg-yellow-400',
      text: 'text-yellow-400',
      label: 'Medium'
    },
    low: {
      dot: 'bg-red-400',
      text: 'text-red-400',
      label: 'Low'
    }
  };

  const config = colorConfig[level];

  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5';
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <span
      className={`inline-flex items-center gap-1.5 ${textSize}`}
      title={`Confidence: ${percentage}% (${config.label})`}
    >
      <span
        className={`${dotSize} rounded-full ${config.dot}`}
        aria-hidden="true"
      />
      {showPercentage && (
        <span className={`font-medium ${config.text}`}>
          {percentage}%
        </span>
      )}
    </span>
  );
};

export default ConfidenceIndicator;
