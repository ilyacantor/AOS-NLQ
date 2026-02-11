import React, { useState, useMemo, useCallback } from 'react';

export interface ScenarioAdjustments {
  headcountChange: number;
  revenueGrowth: number;
  pricingChange: number;
  smSpendChange: number;
}

export interface ScenarioModelingPanelProps {
  isOpen: boolean;
  onToggle: () => void;
  baseMetrics: {
    revenue: number;
    revenueGrowthPct: number;
    grossMarginPct: number;
    operatingMarginPct: number;
    netIncomePct: number;
    headcount: number;
    opex: number;
  };
  onApply?: (adjustments: ScenarioAdjustments) => void;
}

interface SliderConfig {
  id: keyof ScenarioAdjustments;
  label: string;
  min: number;
  max: number;
  defaultValue: number;
  step: number;
}

const SLIDER_CONFIGS: SliderConfig[] = [
  { id: 'revenueGrowth', label: 'Revenue Growth', min: -10, max: 40, defaultValue: 15, step: 1 },
  { id: 'pricingChange', label: 'Pricing / Mix', min: -10, max: 15, defaultValue: 0, step: 1 },
  { id: 'headcountChange', label: 'Headcount', min: -10, max: 30, defaultValue: 0, step: 1 },
  { id: 'smSpendChange', label: 'OpEx Change', min: -20, max: 30, defaultValue: 0, step: 1 },
];

const DEFAULT_ADJUSTMENTS: ScenarioAdjustments = {
  headcountChange: 0,
  revenueGrowth: 15,
  pricingChange: 0,
  smSpendChange: 0,
};

const formatPercent = (value: number): string => {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value}%`;
};

const formatCurrency = (value: number): string => {
  if (Math.abs(value) >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const formatNumber = (value: number, decimals: number = 1): string => {
  return value.toFixed(decimals);
};

interface ImpactMetric {
  label: string;
  baseValue: number;
  projectedValue: number;
  format: 'currency' | 'percent' | 'number';
  invertImpact?: boolean;
}

export const ScenarioModelingPanel: React.FC<ScenarioModelingPanelProps> = ({
  isOpen,
  onToggle,
  baseMetrics,
  onApply,
}) => {
  const [adjustments, setAdjustments] = useState<ScenarioAdjustments>(DEFAULT_ADJUSTMENTS);

  const handleSliderChange = useCallback((id: keyof ScenarioAdjustments, value: number) => {
    setAdjustments(prev => ({ ...prev, [id]: value }));
  }, []);

  const handleReset = useCallback(() => {
    setAdjustments(DEFAULT_ADJUSTMENTS);
  }, []);

  const handleApply = useCallback(() => {
    onApply?.(adjustments);
  }, [adjustments, onApply]);

  const projectedMetrics = useMemo(() => {
    const revenueMultiplier = 1 + adjustments.revenueGrowth / 100;
    const pricingMultiplier = 1 + adjustments.pricingChange / 100;

    const projectedRevenue = baseMetrics.revenue * revenueMultiplier * pricingMultiplier;
    const projectedRevenueGrowth = baseMetrics.revenueGrowthPct + adjustments.revenueGrowth;

    const cogsImpact = adjustments.pricingChange * -0.1;
    const projectedGrossMargin = baseMetrics.grossMarginPct + cogsImpact;

    const headcountCostImpact = adjustments.headcountChange * 0.3;
    const opexImpact = adjustments.smSpendChange * 0.4;
    const revenueEfficiency = adjustments.revenueGrowth * 0.2;
    const projectedOperatingMargin = baseMetrics.operatingMarginPct - headcountCostImpact - opexImpact + revenueEfficiency;

    const projectedNetIncome = projectedOperatingMargin * 0.75;

    return {
      revenue: projectedRevenue,
      revenueGrowthPct: projectedRevenueGrowth,
      grossMarginPct: Math.max(0, projectedGrossMargin),
      operatingMarginPct: projectedOperatingMargin,
      netIncomePct: projectedNetIncome,
    };
  }, [adjustments, baseMetrics]);

  const impactMetrics: ImpactMetric[] = useMemo(() => [
    {
      label: 'Revenue',
      baseValue: baseMetrics.revenue,
      projectedValue: projectedMetrics.revenue,
      format: 'currency',
    },
    {
      label: 'Growth',
      baseValue: baseMetrics.revenueGrowthPct,
      projectedValue: projectedMetrics.revenueGrowthPct,
      format: 'percent',
    },
    {
      label: 'Gross Margin',
      baseValue: baseMetrics.grossMarginPct,
      projectedValue: projectedMetrics.grossMarginPct,
      format: 'percent',
    },
    {
      label: 'Op. Margin',
      baseValue: baseMetrics.operatingMarginPct,
      projectedValue: projectedMetrics.operatingMarginPct,
      format: 'percent',
    },
  ], [baseMetrics, projectedMetrics]);

  const formatMetricValue = (value: number, format: ImpactMetric['format']): string => {
    switch (format) {
      case 'currency':
        return formatCurrency(value);
      case 'percent':
        return `${formatNumber(value, 1)}%`;
      case 'number':
        return formatNumber(value, 1);
      default:
        return formatNumber(value, 1);
    }
  };

  const getImpactColor = (base: number, projected: number, invertImpact?: boolean): string => {
    const diff = projected - base;
    const isPositive = invertImpact ? diff < 0 : diff > 0;
    const isNegative = invertImpact ? diff > 0 : diff < 0;
    
    if (Math.abs(diff) < 0.01) return 'text-slate-400';
    if (isPositive) return 'text-green-400';
    if (isNegative) return 'text-red-400';
    return 'text-slate-400';
  };

  const getImpactBgColor = (base: number, projected: number, invertImpact?: boolean): string => {
    const diff = projected - base;
    const isPositive = invertImpact ? diff < 0 : diff > 0;
    const isNegative = invertImpact ? diff > 0 : diff < 0;
    
    if (Math.abs(diff) < 0.01) return 'bg-slate-700/30';
    if (isPositive) return 'bg-green-500/10';
    if (isNegative) return 'bg-red-500/10';
    return 'bg-slate-700/30';
  };

  const getChangeIndicator = (base: number, projected: number, _invertImpact?: boolean): string => {
    const diff = projected - base;
    const percentChange = base !== 0 ? ((diff / base) * 100) : 0;
    
    if (Math.abs(percentChange) < 0.1) return '';
    
    const sign = percentChange > 0 ? '↑' : '↓';
    return `${sign} ${Math.abs(percentChange).toFixed(1)}%`;
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 transition-opacity duration-300"
          onClick={onToggle}
        />
      )}

      <div
        className={`
          fixed top-0 right-0 h-full w-96 z-50
          bg-slate-900 border-l border-slate-700
          shadow-2xl shadow-black/50
          transform transition-transform duration-300 ease-out
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
          flex flex-col
        `}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0bcad9]/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-[#0bcad9]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-100">Scenario Modeling</h2>
              <p className="text-xs text-slate-500">What-if analysis</p>
            </div>
          </div>
          <button
            onClick={onToggle}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            aria-label="Close panel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="p-5">
            <h3 className="text-sm font-medium text-slate-300 mb-4 flex items-center gap-2">
              <svg className="w-4 h-4 text-[#0bcad9]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              Adjust Variables
            </h3>
            
            <div className="space-y-6">
              {SLIDER_CONFIGS.map((config) => (
                <div key={config.id} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm text-slate-400">{config.label}</label>
                    <span className="text-sm font-medium text-[#0bcad9]">
                      {formatPercent(adjustments[config.id])}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={config.min}
                    max={config.max}
                    step={config.step}
                    value={adjustments[config.id]}
                    onChange={(e) => handleSliderChange(config.id, Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none cursor-pointer
                      bg-slate-700
                      [&::-webkit-slider-thumb]:appearance-none
                      [&::-webkit-slider-thumb]:w-4
                      [&::-webkit-slider-thumb]:h-4
                      [&::-webkit-slider-thumb]:rounded-full
                      [&::-webkit-slider-thumb]:bg-[#0bcad9]
                      [&::-webkit-slider-thumb]:shadow-lg
                      [&::-webkit-slider-thumb]:shadow-[#0bcad9]/30
                      [&::-webkit-slider-thumb]:cursor-pointer
                      [&::-webkit-slider-thumb]:transition-transform
                      [&::-webkit-slider-thumb]:hover:scale-110
                      [&::-moz-range-thumb]:w-4
                      [&::-moz-range-thumb]:h-4
                      [&::-moz-range-thumb]:rounded-full
                      [&::-moz-range-thumb]:bg-[#0bcad9]
                      [&::-moz-range-thumb]:border-0
                      [&::-moz-range-thumb]:shadow-lg
                      [&::-moz-range-thumb]:shadow-[#0bcad9]/30
                      [&::-moz-range-thumb]:cursor-pointer
                    "
                  />
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>{formatPercent(config.min)}</span>
                    <span>{formatPercent(config.max)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="px-5 pb-5">
            <h3 className="text-sm font-medium text-slate-300 mb-4 flex items-center gap-2">
              <svg className="w-4 h-4 text-[#0bcad9]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              KPI Impact Preview
            </h3>
            
            <div className="grid grid-cols-2 gap-3">
              {impactMetrics.map((metric) => {
                const impactColor = getImpactColor(metric.baseValue, metric.projectedValue, metric.invertImpact);
                const impactBg = getImpactBgColor(metric.baseValue, metric.projectedValue, metric.invertImpact);
                const changeIndicator = getChangeIndicator(metric.baseValue, metric.projectedValue, metric.invertImpact);
                
                return (
                  <div
                    key={metric.label}
                    className={`p-3 rounded-lg border border-slate-700/50 ${impactBg} transition-colors duration-200`}
                  >
                    <div className="text-xs text-slate-500 mb-1">{metric.label}</div>
                    <div className={`text-lg font-semibold ${impactColor} transition-colors duration-200`}>
                      {formatMetricValue(metric.projectedValue, metric.format)}
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-xs text-slate-600">
                        was {formatMetricValue(metric.baseValue, metric.format)}
                      </span>
                      {changeIndicator && (
                        <span className={`text-xs font-medium ${impactColor}`}>
                          {changeIndicator}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 px-5 py-4 border-t border-slate-700 bg-slate-900/80 backdrop-blur-sm">
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="flex-1 px-4 py-2.5 rounded-lg
                bg-slate-800 hover:bg-slate-700
                border border-slate-600 hover:border-slate-500
                text-slate-300 text-sm font-medium
                transition-colors duration-150
                flex items-center justify-center gap-2
              "
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Reset
            </button>
            <button
              onClick={handleApply}
              className="flex-1 px-4 py-2.5 rounded-lg
                bg-[#0bcad9] hover:bg-[#0ab8c6]
                text-slate-900 text-sm font-semibold
                transition-colors duration-150
                shadow-lg shadow-[#0bcad9]/20
                flex items-center justify-center gap-2
              "
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Apply to Dashboard
            </button>
          </div>
        </div>
      </div>

      <button
        onClick={onToggle}
        className={`
          fixed top-1/3 -translate-y-1/2 z-30
          w-[28px] rounded-l-lg
          bg-slate-800 hover:bg-slate-700
          border border-r-0 border-slate-600
          text-[#0bcad9]
          shadow-lg
          transition-all duration-300
          flex flex-col items-center justify-center gap-1
          px-1 py-3
          ${isOpen ? 'right-96' : 'right-0'}
        `}
        aria-label={isOpen ? 'Close scenario panel' : 'Open scenario panel'}
      >
        <svg
          className={`w-4 h-4 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        <span className="text-[10px] text-[#0bcad9] font-medium" style={{ writingMode: 'vertical-rl' }}>What-If</span>
      </button>
    </>
  );
};

export default ScenarioModelingPanel;
