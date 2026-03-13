/**
 * ForecastComparison — shows a table comparing current vs adjusted forecast
 * after a What-If scenario is applied.
 */

export interface ForecastRow {
  metric: string;
  current: number;
  adjusted: number;
  format: 'currency' | 'percent';
}

function formatForecastValue(value: number, format: 'currency' | 'percent'): string {
  if (format === 'currency') {
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    return `$${(value / 1e3).toFixed(0)}K`;
  }
  return `${value.toFixed(1)}%`;
}

function formatVariance(current: number, adjusted: number, format: 'currency' | 'percent'): string {
  const diff = adjusted - current;
  if (format === 'currency') {
    const sign = diff >= 0 ? '+' : '';
    if (Math.abs(diff) >= 1e6) return `${sign}$${(diff / 1e6).toFixed(1)}M`;
    return `${sign}$${(diff / 1e3).toFixed(0)}K`;
  }
  // basis points for percentage metrics
  const bps = Math.round((diff) * 100);
  const sign = bps >= 0 ? '+' : '';
  return `${sign}${bps} bps`;
}

export function ForecastComparison({ rows, onDismiss }: { rows: ForecastRow[]; onDismiss: () => void }) {
  return (
    <div className="mx-4 md:mx-6 mb-3 rounded-lg border border-cyan-500/30 bg-slate-900/80 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-800">
        <h3 className="text-xs font-semibold text-white flex items-center gap-1.5">
          <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Forecast Comparison
        </h3>
        <button onClick={onDismiss} className="text-slate-500 hover:text-slate-300 transition-colors">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-800 text-slate-400">
            <th className="text-left px-3 py-1.5 font-medium">Metric</th>
            <th className="text-right px-3 py-1.5 font-medium">Current Forecast</th>
            <th className="text-right px-3 py-1.5 font-medium">Adjusted Forecast</th>
            <th className="text-right px-3 py-1.5 font-medium">Variance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const diff = row.adjusted - row.current;
            const isPositive = diff > 0;
            const isNegative = diff < 0;
            const varColor = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400';
            return (
              <tr key={row.metric} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="px-3 py-1.5 text-slate-200 font-medium">{row.metric}</td>
                <td className="px-3 py-1.5 text-right text-slate-300">{formatForecastValue(row.current, row.format)}</td>
                <td className="px-3 py-1.5 text-right text-white font-medium">{formatForecastValue(row.adjusted, row.format)}</td>
                <td className={`px-3 py-1.5 text-right font-medium ${varColor}`}>
                  {formatVariance(row.current, row.adjusted, row.format)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
