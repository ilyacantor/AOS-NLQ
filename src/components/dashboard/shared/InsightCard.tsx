import React from 'react';
import { ConfidenceIndicator } from './ConfidenceIndicator';

export interface InsightCardProps {
  id: string;
  type: 'warning' | 'positive' | 'declining' | 'improving' | 'anomaly';
  headline: string;
  explanation: string;
  query: string;
  confidence: number;
  timestamp?: string;
  onClick: (query: string) => void;
}

interface IconConfig {
  icon: React.ReactNode;
  color: string;
  bgGradient: string;
  borderColor: string;
  accentColor: string;
}

const getIconConfig = (type: InsightCardProps['type']): IconConfig => {
  const configs: Record<InsightCardProps['type'], IconConfig> = {
    warning: {
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-amber-400',
      bgGradient: 'from-amber-500/10 to-amber-600/5',
      borderColor: 'border-amber-500/20',
      accentColor: 'amber-500',
    },
    anomaly: {
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-amber-400',
      bgGradient: 'from-amber-500/10 to-amber-600/5',
      borderColor: 'border-amber-500/20',
      accentColor: 'amber-500',
    },
    positive: {
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-green-400',
      bgGradient: 'from-green-500/10 to-green-600/5',
      borderColor: 'border-green-500/20',
      accentColor: 'green-500',
    },
    improving: {
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M3.293 9.707a1 1 0 010-1.414l6-6a1 1 0 011.414 0l6 6a1 1 0 01-1.414 1.414L11 5.414V17a1 1 0 11-2 0V5.414L4.707 9.707a1 1 0 01-1.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-green-400',
      bgGradient: 'from-green-500/10 to-green-600/5',
      borderColor: 'border-green-500/20',
      accentColor: 'green-500',
    },
    declining: {
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 10.293a1 1 0 010 1.414l-6 6a1 1 0 01-1.414 0l-6-6a1 1 0 111.414-1.414L9 14.586V3a1 1 0 012 0v11.586l4.293-4.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-red-400',
      bgGradient: 'from-red-500/10 to-red-600/5',
      borderColor: 'border-red-500/20',
      accentColor: 'red-500',
    },
  };
  return configs[type];
};

const formatTimestamp = (timestamp?: string): string | null => {
  if (!timestamp) return null;
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  } catch {
    return null;
  }
};

export const InsightCard: React.FC<InsightCardProps> = ({
  id,
  type,
  headline,
  explanation,
  query,
  confidence,
  timestamp,
  onClick,
}) => {
  const config = getIconConfig(type);
  const formattedTime = formatTimestamp(timestamp);

  return (
    <div
      id={id}
      className={`bg-gradient-to-br ${config.bgGradient} border ${config.borderColor} rounded-lg p-4 backdrop-blur-sm transition-all duration-200 hover:shadow-lg hover:border-opacity-30`}
    >
      {/* Header with Icon and Headline */}
      <div className="flex items-start gap-3 mb-3">
        <span className={`flex-shrink-0 mt-0.5 ${config.color}`}>
          {config.icon}
        </span>
        <h3 className="text-slate-100 font-semibold text-sm leading-tight flex-1">
          {headline}
        </h3>
      </div>

      {/* Explanation - AI-generated storytelling */}
      <p className="text-slate-300 text-sm leading-relaxed mb-4 ml-8">
        {explanation}
      </p>

      {/* Footer with Metadata and Action */}
      <div className="flex items-center justify-between gap-3 ml-8">
        {/* Confidence and Timestamp */}
        <div className="flex items-center gap-4 text-xs">
          <ConfidenceIndicator
            value={confidence}
            showPercentage={true}
            size="sm"
          />
          {formattedTime && (
            <span className="text-slate-500">{formattedTime}</span>
          )}
        </div>

        {/* Ask NLQ Button */}
        <button
          onClick={() => onClick(query)}
          className="flex-shrink-0 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          title="Ask NLQ to drill down into this insight"
        >
          Ask NLQ
        </button>
      </div>
    </div>
  );
};

export default InsightCard;
