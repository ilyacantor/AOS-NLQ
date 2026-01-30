import React, { useState, useCallback, useMemo } from 'react';
import { Persona, DashboardConfig, TimeRange } from '../../types/dashboard';
import { useDashboardData } from '../../hooks/useDashboardData';
import { DashboardGrid } from './DashboardGrid';
import { TimeRangeSelector } from './shared/TimeRangeSelector';
import { ScenarioModelingPanel } from './shared/ScenarioModelingPanel';

// Import dashboard configurations
import cfoConfigJson from '../../config/dashboards/cfo.json';
import croConfigJson from '../../config/dashboards/cro.json';
import cooConfigJson from '../../config/dashboards/coo.json';
import ctoConfigJson from '../../config/dashboards/cto.json';
import chroConfigJson from '../../config/dashboards/chro.json';

/**
 * Props for the Dashboard component
 */
export interface DashboardProps {
  /** Dashboard persona determines which configuration to load */
  persona: Persona;
  /** Callback when user submits an NLQ query (from tile click or NLQ bar) */
  onNLQQuery: (query: string) => void;
  /** Optional custom dashboard configuration */
  customConfig?: DashboardConfig;
  /** Optional initial time range */
  initialTimeRange?: TimeRange;
}

/**
 * Map persona to their dashboard configuration
 */
const PERSONA_CONFIGS: Record<Persona, DashboardConfig | null> = {
  CFO: transformJsonConfig(cfoConfigJson),
  CRO: transformJsonConfig(croConfigJson),
  COO: transformJsonConfig(cooConfigJson),
  CTO: transformJsonConfig(ctoConfigJson),
  CHRO: transformJsonConfig(chroConfigJson),
};

/**
 * Persona display names and descriptions
 */
const PERSONA_INFO: Record<Persona, { title: string; description: string }> = {
  CFO: { title: 'Finance Overview', description: 'Executive financial health dashboard' },
  CRO: { title: 'Revenue Overview', description: 'Sales and revenue performance' },
  COO: { title: 'Operations Overview', description: 'Operational metrics and efficiency' },
  CTO: { title: 'Technology Overview', description: 'Engineering and product metrics' },
  CHRO: { title: 'People Overview', description: 'HR and workforce dashboard' },
};

/**
 * Transform JSON config to proper DashboardConfig with typed values
 */
function transformJsonConfig(json: any): DashboardConfig {
  // Transform tiles from JSON format to TileConfig format
  const tiles = json.tiles.map((tile: any) => {
    const baseConfig = {
      id: tile.id,
      type: tile.type,
      position: {
        column: tile.position.x + 1, // Convert 0-based to 1-based
        row: tile.position.y + 1,
        colSpan: tile.position.w,
        rowSpan: tile.position.h,
      },
      visible: true,
    };

    // Add type-specific config
    if (tile.type === 'kpi') {
      return {
        ...baseConfig,
        kpi: {
          id: tile.id,
          label: tile.config.label,
          primaryQuery: tile.config.query,
          clickQuery: tile.config.clickQuery,
          format: tile.config.format === 'percentage' ? 'percent' : tile.config.format,
          showSparkline: tile.config.showSparkline ?? false,
          showTrend: tile.config.showTrend ?? false,
        },
      };
    }

    if (tile.type === 'chart') {
      return {
        ...baseConfig,
        chart: {
          id: tile.id,
          type: mapChartType(tile.config.chartType),
          title: tile.config.title,
          query: tile.config.query,
          clickTemplate: tile.config.clickQuery || '',
          dimensions: [],
          measures: [],
        },
      };
    }

    if (tile.type === 'insights') {
      return {
        ...baseConfig,
        insights: {
          query: tile.config.query,
          maxItems: tile.config.maxItems ?? 5,
          title: tile.config.title,
        },
      };
    }

    // NLQ bar or other types
    return {
      ...baseConfig,
      visible: tile.type !== 'nlq', // Hide NLQ bar from grid, we render it separately
    };
  });

  return {
    id: json.id,
    name: json.name,
    description: json.description,
    persona: json.persona as Persona,
    version: '1.0',
    kpis: tiles.filter((t: any) => t.type === 'kpi').map((t: any) => t.kpi),
    charts: tiles.filter((t: any) => t.type === 'chart').map((t: any) => t.chart),
    tiles: tiles.filter((t: any) => t.visible !== false),
    layout: {
      columns: json.layout.columns,
      rowHeight: json.layout.rowHeight,
      gap: 16,
    },
    defaultFilters: {
      timeRange: json.timeRangeDefault as TimeRange,
    },
    refreshInterval: json.refreshInterval ?? 300,
    editable: false,
  };
}

/**
 * Map chart type from JSON config to ChartType
 */
function mapChartType(chartType: string): 'waterfall' | 'bar' | 'donut' | 'line' | 'stacked-bar' | 'horizontal-bar' {
  const mapping: Record<string, 'waterfall' | 'bar' | 'donut' | 'line' | 'stacked-bar' | 'horizontal-bar'> = {
    waterfall: 'waterfall',
    bar: 'bar',
    donut: 'donut',
    line: 'line',
    stackedBar: 'stacked-bar',
    horizontalBar: 'horizontal-bar',
  };
  return mapping[chartType] || 'bar';
}

/**
 * Refresh icon component
 */
const RefreshIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
    />
  </svg>
);

/**
 * Dashboard - Main dashboard container component
 *
 * This component serves as the primary container for persona-based dashboards.
 * It handles:
 * - Loading the appropriate dashboard configuration based on persona
 * - Managing time range selection
 * - Coordinating data fetching via useDashboardData hook
 * - Rendering the dashboard header with controls
 * - Passing tile click events to the parent for NLQ processing
 */
export const Dashboard: React.FC<DashboardProps> = ({
  persona,
  onNLQQuery,
  customConfig,
  initialTimeRange,
}) => {
  // Get dashboard configuration for the persona
  const config = useMemo(() => {
    if (customConfig) return customConfig;
    const personaConfig = PERSONA_CONFIGS[persona];
    return personaConfig;
  }, [persona, customConfig]);

  // Time range state
  const [timeRange, setTimeRange] = useState<TimeRange>(
    initialTimeRange || config?.defaultFilters.timeRange || 'YTD'
  );

  // Scenario panel visibility state
  const [scenarioOpen, setScenarioOpen] = useState(false);

  // Base metrics for scenario modeling (profitable company metrics for CFO)
  const baseMetrics = {
    revenue: 150000000,
    revenueGrowthPct: 18,
    grossMarginPct: 65,
    operatingMarginPct: 30,
    netIncomePct: 22,
    headcount: 350,
    opex: 45000000,
  };

  // Fetch dashboard data using the hook
  const { data, loading, error, refresh, lastRefreshed } = useDashboardData(
    config,
    timeRange
  );

  // Handle tile click - triggers NLQ query
  const handleTileClick = useCallback(
    (clickQuery: string, context?: Record<string, string>) => {
      // Replace any placeholders in the query with context values
      let query = clickQuery;
      if (context) {
        Object.entries(context).forEach(([key, value]) => {
          query = query.replace(`{${key}}`, value);
        });
      }
      onNLQQuery(query);
    },
    [onNLQQuery]
  );

  // Handle time range change
  const handleTimeRangeChange = useCallback((newRange: string) => {
    setTimeRange(newRange as TimeRange);
  }, []);

  // Handle refresh button click
  const handleRefresh = useCallback(() => {
    refresh();
  }, [refresh]);

  // Handle scenario panel toggle
  const handleToggleScenario = useCallback(() => {
    setScenarioOpen(prev => !prev);
  }, []);

  // Handle scenario apply
  const handleScenarioApply = useCallback((adjustments: { headcountChange: number; revenueGrowth: number; pricingChange: number; smSpendChange: number }) => {
    console.log('Scenario adjustments applied:', adjustments);
  }, []);

  // Get persona info
  const personaInfo = PERSONA_INFO[persona];

  // Show error state if no config
  if (!config) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-slate-950 text-slate-400 p-8">
        <svg
          className="w-16 h-16 mb-4 text-slate-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1}
            d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <h2 className="text-xl font-semibold text-slate-200 mb-2">
          Dashboard Not Available
        </h2>
        <p className="text-sm text-center max-w-md">
          The {persona} dashboard configuration is not yet available.
          Please check back later or contact support.
        </p>
      </div>
    );
  }

  // Format last refreshed time
  const formatLastRefreshed = (date: Date | null): string => {
    if (!date) return '';
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="dashboard flex flex-col h-full bg-slate-950">
      {/* Dashboard Header */}
      <header className="flex-shrink-0 px-6 py-4 border-b border-slate-800">
        <div className="flex items-center justify-between">
          {/* Title and Description */}
          <div>
            <h1 className="text-xl font-bold text-slate-200">
              {config.name || personaInfo.title}
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {config.description || personaInfo.description}
            </p>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-4">
            {/* Last Updated */}
            {lastRefreshed && (
              <span className="text-xs text-slate-500">
                Updated {formatLastRefreshed(lastRefreshed)}
              </span>
            )}

            {/* Time Range Selector */}
            <TimeRangeSelector
              value={timeRange}
              onChange={handleTimeRangeChange}
              options={['MTD', 'QTD', 'YTD', 'L12M']}
              label="Period:"
            />

            {/* Refresh Button */}
            <button
              onClick={handleRefresh}
              disabled={loading}
              className={`
                flex items-center gap-2 px-3 py-1.5
                bg-slate-800 hover:bg-slate-700
                border border-slate-700 hover:border-slate-600
                rounded-md text-slate-300 text-sm
                transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
              title="Refresh dashboard"
            >
              <RefreshIcon
                className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
              />
              <span className="hidden sm:inline">Refresh</span>
            </button>

            {/* Scenario Button - CFO only */}
            {persona === 'CFO' && (
              <button
                onClick={handleToggleScenario}
                className={`
                  flex items-center gap-2 px-3 py-1.5
                  rounded-md text-sm font-medium
                  transition-colors
                  ${scenarioOpen 
                    ? 'bg-[#0bcad9] text-slate-900 hover:bg-[#0ab8c6]' 
                    : 'bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-slate-300'
                  }
                `}
                title="Open scenario modeling panel"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span className="hidden sm:inline">Scenario</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="flex-shrink-0 px-6 py-3 bg-red-900/20 border-b border-red-800/50">
          <p className="text-red-400 text-sm">
            <span className="font-medium">Error loading dashboard:</span> {error}
          </p>
        </div>
      )}

      {/* Dashboard Content */}
      <main className="flex-1 overflow-auto p-6">
        <DashboardGrid
          config={config}
          data={data}
          loading={loading}
          onTileClick={handleTileClick}
        />
      </main>

      {/* Scenario Modeling Panel - CFO only */}
      {persona === 'CFO' && (
        <ScenarioModelingPanel
          isOpen={scenarioOpen}
          onToggle={handleToggleScenario}
          baseMetrics={baseMetrics}
          onApply={handleScenarioApply}
        />
      )}
    </div>
  );
};

export default Dashboard;
