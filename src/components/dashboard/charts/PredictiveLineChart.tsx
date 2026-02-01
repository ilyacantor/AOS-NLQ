import React from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
  ReferenceLine,
} from 'recharts';
import { formatNumber } from '../../../utils/formatters';

const COLORS = {
  primary: '#0bcad9',
  success: '#22c55e',
  prediction: '#a855f7',
};

interface PredictiveLineChartProps {
  title: string;
  historicalData: Array<{ period: string; value: number }>;
  forecastData?: Array<{ period: string; value: number; confidence?: number }>;
  onClick?: (period: string) => void;
  onChat?: (query: string) => void;
  chatQuery?: string;
  height?: number;
  showLegend?: boolean;
  metricName?: string;
}

interface CombinedDataPoint {
  period: string;
  historical?: number;
  forecast?: number;
  confidence?: number;
  isForecast: boolean;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    dataKey: string;
    value: number;
    payload: CombinedDataPoint;
  }>;
  label?: string;
  metricName?: string;
}

const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label, metricName }) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0]?.payload;
  const historicalValue = data?.historical;
  const forecastValue = data?.forecast;
  const confidence = data?.confidence;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl">
      <p className="text-slate-400 text-xs mb-2">{label}</p>
      {historicalValue !== undefined && (
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.primary }} />
          <span className="text-slate-300 text-sm">
            {metricName || 'Actual'}: <span className="font-semibold text-white">{formatNumber(historicalValue)}</span>
          </span>
        </div>
      )}
      {forecastValue !== undefined && (
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.prediction }} />
          <span className="text-slate-300 text-sm">
            Forecast: <span className="font-semibold text-white">{formatNumber(forecastValue)}</span>
          </span>
          {confidence !== undefined && (
            <span className="text-slate-500 text-xs ml-2">
              ({Math.round(confidence * 100)}% conf.)
            </span>
          )}
        </div>
      )}
    </div>
  );
};

interface ForecastDotProps {
  cx?: number;
  cy?: number;
  payload?: CombinedDataPoint;
}

const ForecastDot: React.FC<ForecastDotProps> = ({ cx, cy, payload }) => {
  if (!cx || !cy || !payload?.forecast) return null;

  const confidence = payload.confidence ?? 1;
  const radius = 4 + (1 - confidence) * 3;
  const opacity = 0.5 + confidence * 0.5;

  return (
    <circle
      cx={cx}
      cy={cy}
      r={radius}
      fill={COLORS.prediction}
      fillOpacity={opacity}
      stroke={COLORS.prediction}
      strokeWidth={1.5}
      strokeOpacity={0.8}
    />
  );
};

export const PredictiveLineChart: React.FC<PredictiveLineChartProps> = ({
  title,
  historicalData,
  forecastData,
  onClick,
  onChat,
  chatQuery,
  height = 300,
  showLegend = true,
  metricName,
}) => {
  const combinedData: CombinedDataPoint[] = React.useMemo(() => {
    const result: CombinedDataPoint[] = [];

    historicalData.forEach((item) => {
      result.push({
        period: item.period,
        historical: item.value,
        isForecast: false,
      });
    });

    if (forecastData && forecastData.length > 0) {
      const lastHistorical = historicalData[historicalData.length - 1];
      if (lastHistorical) {
        const existingIndex = result.findIndex((d) => d.period === lastHistorical.period);
        if (existingIndex >= 0) {
          result[existingIndex].forecast = lastHistorical.value;
        }
      }

      forecastData.forEach((item) => {
        const existingIndex = result.findIndex((d) => d.period === item.period);
        if (existingIndex >= 0) {
          result[existingIndex].forecast = item.value;
          result[existingIndex].confidence = item.confidence;
          result[existingIndex].isForecast = true;
        } else {
          result.push({
            period: item.period,
            forecast: item.value,
            confidence: item.confidence,
            isForecast: true,
          });
        }
      });
    }

    return result;
  }, [historicalData, forecastData]);

  const lastHistoricalPeriod = historicalData[historicalData.length - 1]?.period;
  const hasForecast = forecastData && forecastData.length > 0;

  const handleClick = (data: { activeLabel?: string | number | null }) => {
    if (onClick && data?.activeLabel !== undefined && data?.activeLabel !== null) {
      onClick(String(data.activeLabel));
    }
  };

  if (!historicalData || historicalData.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl p-4" style={{ height }}>
        <h3 className="text-slate-200 font-semibold text-sm mb-4">{title}</h3>
        <div className="flex items-center justify-center h-32 text-slate-500 text-sm">
          No data available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl p-4" style={{ minHeight: height }}>
      <div className="flex items-center justify-between gap-2 mb-4">
        <h3 className="text-slate-200 font-semibold text-sm">{title}</h3>
        {onChat && chatQuery && (
          <button
            onClick={() => onChat(chatQuery)}
            className="px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-700/50 transition-all duration-200 rounded-md flex items-center gap-1.5 focus:outline-none flex-shrink-0"
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#0bcad9';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'rgb(148, 163, 184)';
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow = '0 0 0 2px rgba(11, 202, 217, 0.5), 0 0 0 4px rgba(1, 6, 23, 1)';
              e.currentTarget.style.outlineStyle = 'none';
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            title="Ask questions about this chart"
            aria-label="Chat about this chart"
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
            <span>Chat</span>
          </button>
        )}
      </div>

      <ResponsiveContainer width="100%" height={height - 80}>
        <ComposedChart
          data={combinedData}
          onClick={handleClick}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="historicalGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.4} />
              <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={COLORS.prediction} stopOpacity={0.25} />
              <stop offset="95%" stopColor={COLORS.prediction} stopOpacity={0.02} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#334155" strokeOpacity={0.5} />

          <XAxis
            dataKey="period"
            tick={{ fill: '#94a3b8', fontSize: 12 }}
            tickLine={{ stroke: '#475569' }}
            axisLine={{ stroke: '#475569' }}
          />

          <YAxis
            tick={{ fill: '#94a3b8', fontSize: 12 }}
            tickLine={{ stroke: '#475569' }}
            axisLine={{ stroke: '#475569' }}
            tickFormatter={formatNumber}
          />

          <Tooltip content={<CustomTooltip metricName={metricName} />} />

          {showLegend && (
            <Legend
              wrapperStyle={{ paddingTop: '10px' }}
              formatter={(value: string) => (
                <span className="text-slate-300 text-xs">{value}</span>
              )}
            />
          )}

          {lastHistoricalPeriod && hasForecast && (
            <ReferenceLine
              x={lastHistoricalPeriod}
              stroke="#64748b"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: 'Today',
                position: 'top',
                fill: '#94a3b8',
                fontSize: 11,
                fontWeight: 500,
              }}
            />
          )}

          <Area
            type="monotone"
            dataKey="historical"
            stroke="none"
            fill="url(#historicalGradient)"
            connectNulls={false}
          />

          <Line
            type="monotone"
            dataKey="historical"
            name={metricName || 'Actual'}
            stroke={COLORS.primary}
            strokeWidth={2.5}
            dot={{ fill: COLORS.primary, strokeWidth: 0, r: 3 }}
            activeDot={{ r: 5, fill: COLORS.primary, stroke: '#fff', strokeWidth: 2 }}
            connectNulls={false}
          />

          {hasForecast && (
            <>
              <Area
                type="monotone"
                dataKey="forecast"
                stroke="none"
                fill="url(#forecastGradient)"
                connectNulls={true}
              />

              <Line
                type="monotone"
                dataKey="forecast"
                name="Forecast"
                stroke={COLORS.prediction}
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={<ForecastDot />}
                activeDot={{ r: 6, fill: COLORS.prediction, stroke: '#fff', strokeWidth: 2 }}
                connectNulls={true}
              />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PredictiveLineChart;
