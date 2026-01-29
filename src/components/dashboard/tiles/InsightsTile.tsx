import React from 'react';
import { InsightCard } from '../shared/InsightCard';

export interface InsightItem {
  id: string;
  type: 'warning' | 'positive' | 'declining' | 'improving' | 'anomaly';
  text: string;
  query: string; // Full NLQ query when clicked
  confidence?: number;
  timestamp?: string;
}

export interface InsightsTileProps {
  insights: InsightItem[];
  onInsightClick: (query: string) => void;
  loading?: boolean;
  maxItems?: number;
  enhanced?: boolean;
}

interface InsightIconProps {
  type: InsightItem['type'];
}

// Helper function to extract first sentence for headline
const getHeadline = (text: string): string => {
  const sentenceMatch = text.match(/^[^.!?]*[.!?]/);
  if (sentenceMatch) {
    return sentenceMatch[0].trim();
  }
  // Fallback to first 100 characters if no sentence ending found
  return text.length > 100 ? text.substring(0, 100) + '...' : text;
};

const InsightIcon: React.FC<InsightIconProps> = ({ type }) => {
  const iconConfig = {
    warning: {
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-yellow-400',
    },
    anomaly: {
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-yellow-400',
    },
    positive: {
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-green-400',
    },
    declining: {
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 10.293a1 1 0 010 1.414l-6 6a1 1 0 01-1.414 0l-6-6a1 1 0 111.414-1.414L9 14.586V3a1 1 0 012 0v11.586l4.293-4.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-red-400',
    },
    improving: {
      icon: (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M3.293 9.707a1 1 0 010-1.414l6-6a1 1 0 011.414 0l6 6a1 1 0 01-1.414 1.414L11 5.414V17a1 1 0 11-2 0V5.414L4.707 9.707a1 1 0 01-1.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: 'text-green-400',
    },
  };

  const config = iconConfig[type];

  return <span className={config.color}>{config.icon}</span>;
};

const LoadingSkeleton: React.FC<{ count: number }> = ({ count }) => {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 py-2 px-3 animate-pulse"
        >
          <div className="w-4 h-4 bg-slate-700 rounded" />
          <div className="flex-1 h-4 bg-slate-700 rounded" style={{ width: `${70 + Math.random() * 20}%` }} />
        </div>
      ))}
    </div>
  );
};

export const InsightsTile: React.FC<InsightsTileProps> = ({
  insights,
  onInsightClick,
  loading = false,
  maxItems = 5,
  enhanced = false,
}) => {
  const displayedInsights = insights.slice(0, maxItems);

  return (
    <div className={enhanced ? '' : 'bg-slate-800 rounded-xl p-4'}>
      {/* Header */}
      {!enhanced && (
        <div className="flex items-center gap-2 mb-4">
          <svg
            className="w-5 h-5 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          <h3 className="text-slate-200 font-semibold text-sm">Quick Insights</h3>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <LoadingSkeleton count={maxItems} />
      ) : displayedInsights.length === 0 ? (
        <div className="text-slate-500 text-sm text-center py-4">
          No insights available
        </div>
      ) : enhanced ? (
        // Enhanced mode: render InsightCard components
        <div className="space-y-3">
          {displayedInsights.map((insight) => (
            <InsightCard
              key={insight.id}
              id={insight.id}
              type={insight.type}
              headline={getHeadline(insight.text)}
              explanation={insight.text}
              query={insight.query}
              confidence={insight.confidence ?? 0.85}
              timestamp={insight.timestamp}
              onClick={onInsightClick}
            />
          ))}
        </div>
      ) : (
        // Basic mode: render list items (backward compatible)
        <div className="space-y-1">
          {displayedInsights.map((insight) => (
            <button
              key={insight.id}
              onClick={() => onInsightClick(insight.query)}
              className="w-full flex items-start gap-3 py-2 px-3 rounded-lg text-left transition-colors duration-150 hover:bg-slate-700/50 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <span className="flex-shrink-0 mt-0.5">
                <InsightIcon type={insight.type} />
              </span>
              <span className="text-slate-200 text-sm leading-snug">
                {insight.text}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default InsightsTile;
