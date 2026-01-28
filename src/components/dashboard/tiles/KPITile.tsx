import React from 'react';
import { TrendIndicator } from '../shared/TrendIndicator';
import { StatusBadge } from '../shared/StatusBadge';
import { ConfidenceIndicator } from '../shared/ConfidenceIndicator';
import { Sparkline } from '../shared/Sparkline';

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
}

/**
 * Formats a number value based on the specified format type
 */
const formatValue = (
  value: number | string,
  format: KPITileProps['format'],
  suffix?: string
): string => {
  if (typeof value === 'string') {
    return suffix ? `${value}${suffix}` : value;
  }

  let formattedValue: string;

  switch (format) {
    case 'currency':
      if (Math.abs(value) >= 1_000_000_000) {
        formattedValue = `$${(value / 1_000_000_000).toFixed(1)}B`;
      } else if (Math.abs(value) >= 1_000_000) {
        formattedValue = `$${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        formattedValue = `$${(value / 1_000).toFixed(0)}K`;
      } else {
        formattedValue = `$${value.toFixed(0)}`;
      }
      break;

    case 'percent':
      formattedValue = `${value.toFixed(1)}%`;
      break;

    case 'months':
      formattedValue = `${Math.round(value)} month${Math.round(value) !== 1 ? 's' : ''}`;
      break;

    case 'number':
    default:
      if (Math.abs(value) >= 1_000_000) {
        formattedValue = `${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        formattedValue = `${(value / 1_000).toFixed(1)}K`;
      } else {
        formattedValue = value.toLocaleString();
      }
      break;
  }

  return suffix ? `${formattedValue}${suffix}` : formattedValue;
};

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
}) => {
  if (loading) {
    return <LoadingSkeleton />;
  }

  const formattedValue = formatValue(value, format, suffix);

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
      {/* Header row with label, period, and confidence indicator */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <span className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            {label}
          </span>
          {period && (
            <span className="text-xs text-slate-500 ml-2">{period}</span>
          )}
        </div>
        {confidence !== undefined && (
          <ConfidenceIndicator value={confidence} />
        )}
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
