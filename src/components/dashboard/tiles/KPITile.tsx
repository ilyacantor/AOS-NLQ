import React from 'react';
import { TrendIndicator } from '../shared/TrendIndicator';
import { StatusBadge } from '../shared/StatusBadge';
import { ConfidenceIndicator } from '../shared/ConfidenceIndicator';
import { Sparkline } from '../shared/Sparkline';
import { formatValue } from '../../../utils/formatters';

interface KPITileProps {
  label: string;
  value: number | string;
  format: 'currency' | 'percent' | 'number' | 'months';
  suffix?: string;
  period?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    value: number;
    isPositive: boolean;
    comparisonPeriod?: string;
  };
  sparklineData?: number[];
  status?: 'healthy' | 'caution' | 'critical';
  confidence?: number;
  onClick: () => void;
  loading?: boolean;
  onChat?: (query: string) => void;
  chatQuery?: string;
}

/**
 * Loading skeleton component for the KPI tile
 */
const LoadingSkeleton: React.FC = () => (
  <div className="p-5 bg-slate-800 rounded-xl animate-pulse">
    <div className="flex items-start justify-between mb-3">
      <div className="h-4 w-24 bg-slate-700 rounded" />
      <div className="h-4 w-4 bg-slate-700 rounded-full" />
    </div>
    <div className="h-8 w-32 bg-slate-700 rounded mb-3" />
    <div className="flex items-center gap-3">
      <div className="h-4 w-20 bg-slate-700 rounded" />
      <div className="h-5 w-16 bg-slate-700 rounded-full" />
    </div>
    <div className="mt-4 h-10 w-full bg-slate-700 rounded" />
  </div>
);

/**
 * KPITile - Main KPI card component for the dashboard
 *
 * Displays key performance indicators with formatting, trends,
 * sparklines, status badges, and confidence indicators.
 */
export const KPITile: React.FC<KPITileProps> = ({
  label,
  value,
  format,
  suffix,
  period,
  trend,
  sparklineData,
  status,
  confidence,
  onClick,
  loading = false,
  onChat,
  chatQuery,
}) => {
  if (loading) {
    return <LoadingSkeleton />;
  }

  const formattedValue = formatValue(value, { format, suffix });

  return (
    <div
      onClick={onClick}
      className="
        p-5
        bg-slate-800
        rounded-xl
        cursor-pointer
        transition-all
        duration-200
        ease-out
        hover:bg-slate-700
        hover:shadow-lg
        hover:shadow-slate-900/50
        hover:-translate-y-0.5
        active:translate-y-0
        active:shadow-md
      "
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {/* Header row with label, period, confidence indicator, and chat button */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <span className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            {label}
          </span>
          {period && (
            <span className="text-xs text-slate-500 ml-2">{period}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {onChat && chatQuery && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onChat(chatQuery);
              }}
              className="
                p-1.5
                text-slate-400
                transition-colors
                duration-200
                rounded-md
                hover:bg-slate-700/50
                focus:outline-none
                focus:ring-2
                focus:ring-offset-2
                focus:ring-offset-slate-800
              "
              style={{
                '--chat-hover-color': '#0bcad9',
                '--chat-ring-color': '#0bcad9',
              } as React.CSSProperties & { '--chat-hover-color': string; '--chat-ring-color': string }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = '#0bcad9';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = 'rgb(148, 163, 184)';
              }}
              onFocus={(e) => {
                e.currentTarget.style.boxShadow = '0 0 0 2px rgba(11, 202, 217, 0.5), 0 0 0 4px rgba(1, 6, 23, 1)';
              }}
              onBlur={(e) => {
                e.currentTarget.style.boxShadow = 'none';
              }}
              title="Chat about this metric"
              aria-label="Chat about this metric"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </button>
          )}
          {confidence !== undefined && (
            <ConfidenceIndicator value={confidence} />
          )}
        </div>
      </div>

      {/* Main value display */}
      <div className="text-2xl font-bold text-slate-200 mb-2">
        {formattedValue}
      </div>

      {/* Trend and status row */}
      <div className="flex items-center gap-2 flex-wrap text-xs">
        {trend && (
          <>
            <TrendIndicator
              direction={trend.direction}
              value={trend.value}
              isPositive={trend.isPositive}
            />
            {trend.comparisonPeriod && (
              <span className="text-slate-500">{trend.comparisonPeriod}</span>
            )}
          </>
        )}
        {status && (
          <StatusBadge status={status} />
        )}
      </div>

      {/* Sparkline chart */}
      {sparklineData && sparklineData.length > 0 && (
        <div className="mt-4">
          <Sparkline
            data={sparklineData}
            height={40}
            color={
              status === 'critical' ? '#ef4444' :
              status === 'caution' ? '#f59e0b' :
              '#22c55e'
            }
          />
        </div>
      )}
    </div>
  );
};

export default KPITile;
