import React, { useState, useMemo } from 'react';
import { formatCurrency } from '../../../utils/formatters';

interface HorizontalBarChartProps {
  data: Array<{
    label: string;
    value: number;
  }>;
  onClick?: (label: string) => void;
  loading?: boolean;
  maxBars?: number;
}

const DEFAULT_COLOR = '#3B82F6';
const HOVER_COLOR = '#60A5FA';

const HorizontalBarChart: React.FC<HorizontalBarChartProps> = ({
  data,
  onClick,
  loading = false,
  maxBars = 10,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartData = useMemo(() => {
    if (!data || data.length === 0) return { bars: [], maxValue: 0 };

    // Sort by value descending and limit to maxBars
    const sortedData = [...data]
      .sort((a, b) => b.value - a.value)
      .slice(0, maxBars);

    const maxValue = Math.max(...sortedData.map((d) => d.value), 0);

    const bars = sortedData.map((item, index) => ({
      ...item,
      index,
      percentage: maxValue > 0 ? (item.value / maxValue) * 100 : 0,
    }));

    return { bars, maxValue };
  }, [data, maxBars]);


  if (loading) {
    return (
      <div className="w-full bg-slate-800 rounded-lg p-4 animate-pulse">
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-24 h-4 bg-slate-700 rounded" />
              <div className="flex-1 h-6 bg-slate-700 rounded" style={{ width: `${80 - i * 15}%` }} />
              <div className="w-16 h-4 bg-slate-700 rounded" />
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

  const { bars } = chartData;

  return (
    <div className="w-full bg-slate-800 rounded-lg p-4">
      <div className="space-y-3">
        {bars.map((bar, i) => {
          const isHovered = hoveredIndex === i;

          return (
            <div
              key={i}
              className="flex items-center gap-3 cursor-pointer group"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
              onClick={() => onClick?.(bar.label)}
            >
              {/* Label */}
              <div
                className="w-28 flex-shrink-0 text-right"
                title={bar.label}
              >
                <span
                  className={`text-sm truncate block transition-colors duration-150 ${
                    isHovered ? 'text-white' : 'text-slate-400'
                  }`}
                >
                  {bar.label.length > 12
                    ? bar.label.substring(0, 12) + '...'
                    : bar.label}
                </span>
              </div>

              {/* Bar container */}
              <div className="flex-1 h-7 bg-slate-700/50 rounded overflow-hidden relative">
                {/* Bar */}
                <div
                  className="h-full rounded transition-all duration-300 ease-out flex items-center"
                  style={{
                    width: `${Math.max(bar.percentage, 2)}%`,
                    backgroundColor: isHovered ? HOVER_COLOR : DEFAULT_COLOR,
                  }}
                >
                  {/* Value label inside bar if there's enough space */}
                  {bar.percentage > 30 && (
                    <span className="text-xs font-medium text-white px-2 truncate">
                      {formatCurrency(bar.value)}
                    </span>
                  )}
                </div>

                {/* Value label outside bar if not enough space */}
                {bar.percentage <= 30 && (
                  <span
                    className="absolute top-1/2 transform -translate-y-1/2 text-xs font-medium text-slate-300 px-2"
                    style={{ left: `${Math.max(bar.percentage, 2) + 1}%` }}
                  >
                    {formatCurrency(bar.value)}
                  </span>
                )}
              </div>

              {/* Rank indicator */}
              <div
                className={`w-6 text-center text-xs font-medium transition-colors duration-150 ${
                  isHovered ? 'text-blue-400' : 'text-slate-500'
                }`}
              >
                #{i + 1}
              </div>
            </div>
          );
        })}
      </div>

      {/* Show more indicator if data was truncated */}
      {data.length > maxBars && (
        <div className="mt-4 text-center">
          <span className="text-xs text-slate-500">
            Showing top {maxBars} of {data.length} items
          </span>
        </div>
      )}

      {/* Summary stats */}
      <div className="mt-4 pt-4 border-t border-slate-700 flex justify-between text-xs text-slate-400">
        <span>
          Total:{' '}
          <span className="text-white font-medium">
            {formatCurrency(data.reduce((sum, item) => sum + item.value, 0))}
          </span>
        </span>
        <span>
          Avg:{' '}
          <span className="text-white font-medium">
            {formatCurrency(
              data.reduce((sum, item) => sum + item.value, 0) / data.length
            )}
          </span>
        </span>
      </div>
    </div>
  );
};

export default HorizontalBarChart;
