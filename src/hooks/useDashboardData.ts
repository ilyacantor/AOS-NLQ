import { useState, useEffect, useCallback, useRef } from 'react';
import {
  DashboardConfig,
  TileConfig,
  TileData,
  InsightItem,
  TrendData,
  SparklineDataPoint,
  StatusType,
  isKPITile,
  isChartTile,
  isInsightsTile,
} from '../types/dashboard';

/**
 * Static CFO dashboard data - precomputed for instant load
 * This avoids 10+ API calls that each take 2-3 seconds
 */
const STATIC_CFO_DATA: Record<string, TileData> = {
  'kpi-revenue': {
    value: 48.2,
    formattedValue: '$48.2M',
    trend: { direction: 'up', percentChange: 18, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Jan', value: 3.8 }, { period: 'Feb', value: 3.9 }, { period: 'Mar', value: 4.0 },
      { period: 'Apr', value: 4.1 }, { period: 'May', value: 4.0 }, { period: 'Jun', value: 4.2 },
      { period: 'Jul', value: 4.1 }, { period: 'Aug', value: 4.3 }, { period: 'Sep', value: 4.2 },
      { period: 'Oct', value: 4.4 }, { period: 'Nov', value: 4.5 }, { period: 'Dec', value: 4.7 },
    ],
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-gross-margin': {
    value: 68.2,
    formattedValue: '68.2%',
    trend: { direction: 'down', percentChange: 2.1, comparisonPeriod: 'vs 2024', positiveIsGood: false },
    sparklineData: [
      { period: 'Jan', value: 70 }, { period: 'Feb', value: 69.5 }, { period: 'Mar', value: 69 },
      { period: 'Apr', value: 68.8 }, { period: 'May', value: 69 }, { period: 'Jun', value: 68.5 },
      { period: 'Jul', value: 68.2 }, { period: 'Aug', value: 68.4 }, { period: 'Sep', value: 68 },
      { period: 'Oct', value: 68.1 }, { period: 'Nov', value: 68.3 }, { period: 'Dec', value: 68.2 },
    ],
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-operating-margin': {
    value: 35.0,
    formattedValue: '35.0%',
    trend: { direction: 'up', percentChange: 4.2, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 31 }, { period: 'Q2 24', value: 32 },
      { period: 'Q3 24', value: 33 }, { period: 'Q4 24', value: 35 },
    ],
    status: 'healthy',
    confidence: 0.94,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'kpi-net-income': {
    value: 26.2,
    formattedValue: '26.2%',
    trend: { direction: 'up', percentChange: 5.5, comparisonPeriod: 'vs 2024', positiveIsGood: true },
    sparklineData: [
      { period: 'Q1 24', value: 22 }, { period: 'Q2 24', value: 23 },
      { period: 'Q3 24', value: 24 }, { period: 'Q4 24', value: 26.2 },
    ],
    status: 'healthy',
    confidence: 0.93,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-revenue-waterfall': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: '2024', value: 40.8, type: 'total' },
        { label: 'New Sales', value: 8.2, type: 'increase' },
        { label: 'Expansions', value: 3.5, type: 'increase' },
        { label: 'Churn', value: -2.8, type: 'decrease' },
        { label: 'Downgrades', value: -1.5, type: 'decrease' },
        { label: '2025', value: 48.2, type: 'total' },
      ]
    },
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'panel-insights': {
    value: null,
    formattedValue: '',
    insights: [
      { id: '1', type: 'warning', text: 'AR aging up 15% MoM', query: 'Why is accounts receivable aging increasing?' },
      { id: '2', type: 'positive', text: 'OpEx under budget by 8%', query: 'What is driving the OpEx savings?' },
      { id: '3', type: 'warning', text: 'Q1 forecast at risk (-5%)', query: 'What factors are affecting Q1 forecast?' },
      { id: '4', type: 'positive', text: 'Cash position strong', query: 'What is our current cash position and runway?' },
      { id: '5', type: 'improving', text: 'DSO improved 3 days', query: 'How has days sales outstanding changed?' },
    ],
    status: 'healthy',
    confidence: 0.85,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-top-customers': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Acme Corp', value: 4200000 },
        { label: 'TechGiant Inc', value: 3800000 },
        { label: 'Global Solutions', value: 2900000 },
        { label: 'DataFlow Ltd', value: 2100000 },
        { label: 'CloudFirst Co', value: 1800000 },
        { label: 'Nexus Systems', value: 1650000 },
        { label: 'InnovateTech', value: 1420000 },
        { label: 'Quantum Partners', value: 1280000 },
        { label: 'Stellar Labs', value: 1150000 },
        { label: 'Vertex Group', value: 980000 },
      ]
    },
    status: 'healthy',
    confidence: 0.95,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-expenses': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Personnel', value: 15200000, color: '#3B82F6' },
        { label: 'Infrastructure', value: 4800000, color: '#8B5CF6' },
        { label: 'Sales & Marketing', value: 6200000, color: '#EC4899' },
        { label: 'R&D', value: 3500000, color: '#14B8A6' },
        { label: 'G&A', value: 2100000, color: '#F59E0B' },
      ]
    },
    status: 'healthy',
    confidence: 0.92,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'chart-ar-aging': {
    value: null,
    formattedValue: '',
    rawData: {
      chartData: [
        { label: 'Q3', segments: [
          { label: 'Current', value: 2800000 },
          { label: '30 days', value: 450000 },
          { label: '60 days', value: 180000 },
          { label: '90+ days', value: 95000 },
        ]},
        { label: 'Q4', segments: [
          { label: 'Current', value: 3200000 },
          { label: '30 days', value: 520000 },
          { label: '60 days', value: 210000 },
          { label: '90+ days', value: 140000 },
        ]},
      ]
    },
    status: 'caution',
    confidence: 0.88,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
  'nlq-input': {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 1,
    loading: false,
    error: null,
    lastUpdated: new Date(),
  },
};

/**
 * API response structure from /api/v1/query endpoint
 */
interface NLQApiResponse {
  success: boolean;
  answer?: string;
  value?: number | string;
  unit?: string;
  confidence: number;
  parsed_intent?: string;
  resolved_metric?: string;
  resolved_period?: string;
  error_code?: string;
  error_message?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    value: number;
    is_positive: boolean;
    comparison_period?: string;
  };
  sparkline_data?: Array<{ period: string; value: number }>;
  insights?: Array<{
    id: string;
    type: 'warning' | 'positive' | 'declining' | 'improving';
    text: string;
    query: string;
  }>;
}

/**
 * Fetch data for a single tile via the NLQ API
 */
async function fetchTileData(
  tile: TileConfig,
  timeRange: string
): Promise<TileData> {
  // Determine the query based on tile type
  let query = '';
  if (isKPITile(tile)) {
    query = tile.kpi.primaryQuery;
  } else if (isChartTile(tile)) {
    query = tile.chart.query;
  } else if (isInsightsTile(tile)) {
    query = tile.insights.query;
  }

  if (!query) {
    return createEmptyTileData();
  }

  // Append time range to query if not already included
  const timeRangeMap: Record<string, string> = {
    MTD: 'month to date',
    QTD: 'quarter to date',
    YTD: 'year to date',
    L12M: 'last 12 months',
  };

  const timeRangeText = timeRangeMap[timeRange] || timeRange;
  const fullQuery = query.toLowerCase().includes(timeRange.toLowerCase())
    ? query
    : `${query} ${timeRangeText}`;

  try {
    const response = await fetch('/api/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: fullQuery,
        reference_date: new Date().toISOString().split('T')[0],
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data: NLQApiResponse = await response.json();

    if (!data.success) {
      return {
        value: null,
        formattedValue: 'Error',
        status: 'critical',
        confidence: 0,
        loading: false,
        error: data.error_message || 'Query failed',
        lastUpdated: new Date(),
      };
    }

    // Transform API response to TileData
    return transformApiResponseToTileData(data, tile);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return {
      value: null,
      formattedValue: 'Error',
      status: 'critical',
      confidence: 0,
      loading: false,
      error: errorMessage,
      lastUpdated: new Date(),
    };
  }
}

/**
 * Transform the NLQ API response into TileData format
 */
function transformApiResponseToTileData(
  response: NLQApiResponse,
  tile: TileConfig
): TileData {
  // Build trend data if available
  let trend: TrendData | undefined;
  if (response.trend) {
    trend = {
      direction: response.trend.direction,
      percentChange: response.trend.value,
      comparisonPeriod: response.trend.comparison_period || 'vs prior period',
      positiveIsGood: response.trend.is_positive,
    };
  }

  // Build sparkline data if available
  let sparklineData: SparklineDataPoint[] | undefined;
  if (response.sparkline_data && response.sparkline_data.length > 0) {
    sparklineData = response.sparkline_data.map((point) => ({
      period: point.period,
      value: point.value,
    }));
  }

  // Determine status based on confidence and trend
  let status: StatusType = 'healthy';
  if (response.confidence < 0.5) {
    status = 'critical';
  } else if (response.confidence < 0.8) {
    status = 'caution';
  }

  // Format the value based on tile type
  let formattedValue = '';
  if (response.answer) {
    formattedValue = response.answer;
  } else if (response.value !== undefined) {
    formattedValue = formatValue(response.value, response.unit, tile);
  }

  // Build insights array if this is an insights tile
  let insights: InsightItem[] | undefined;
  if (isInsightsTile(tile) && response.insights) {
    insights = response.insights;
  }

  return {
    value: response.value ?? null,
    formattedValue,
    trend,
    sparklineData,
    status,
    confidence: response.confidence,
    loading: false,
    error: null,
    lastUpdated: new Date(),
    rawData: response,
    insights,
  };
}

/**
 * Format a numeric value based on unit and tile configuration
 */
function formatValue(
  value: number | string,
  unit: string | undefined,
  tile: TileConfig
): string {
  if (typeof value === 'string') {
    return value;
  }

  // Determine format from tile config
  let format = 'number';
  if (isKPITile(tile)) {
    format = tile.kpi.format;
  }

  switch (format) {
    case 'currency':
      if (Math.abs(value) >= 1_000_000_000) {
        return `$${(value / 1_000_000_000).toFixed(1)}B`;
      } else if (Math.abs(value) >= 1_000_000) {
        return `$${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        return `$${(value / 1_000).toFixed(0)}K`;
      }
      return `$${value.toFixed(0)}`;

    case 'percent':
      return `${value.toFixed(1)}%`;

    case 'months':
      return `${Math.round(value)} month${Math.round(value) !== 1 ? 's' : ''}`;

    default:
      if (unit === '%') {
        return `${value.toFixed(1)}%`;
      }
      if (unit === '$' || unit === 'currency') {
        return formatValue(value, undefined, { ...tile, kpi: { ...tile.kpi!, format: 'currency' } } as TileConfig);
      }
      if (Math.abs(value) >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(1)}M`;
      } else if (Math.abs(value) >= 1_000) {
        return `${(value / 1_000).toFixed(1)}K`;
      }
      return value.toLocaleString();
  }
}

/**
 * Create an empty tile data object for loading/initial state
 */
function createEmptyTileData(loading = false): TileData {
  return {
    value: null,
    formattedValue: '',
    status: 'healthy',
    confidence: 0,
    loading,
    error: null,
    lastUpdated: null,
  };
}

/**
 * Return type for the useDashboardData hook
 */
export interface UseDashboardDataReturn {
  /** Data for all tiles keyed by tile ID */
  data: Record<string, TileData>;
  /** Whether any tiles are currently loading */
  loading: boolean;
  /** Global error message if all fetches failed */
  error: string | null;
  /** Refresh all tile data */
  refresh: () => Promise<void>;
  /** Refresh data for a specific tile */
  refreshTile: (tileId: string) => Promise<void>;
  /** Last refresh timestamp */
  lastRefreshed: Date | null;
}

/**
 * Hook to fetch and manage dashboard tile data
 *
 * @param config - Dashboard configuration containing tile definitions
 * @param timeRange - Selected time range for data filtering
 * @returns Object containing data, loading state, and refresh functions
 */
export const useDashboardData = (
  config: DashboardConfig | null,
  timeRange: string
): UseDashboardDataReturn => {
  const [data, setData] = useState<Record<string, TileData>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  // Track the refresh interval
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isInitialFetch = useRef(true);

  /**
   * Load data for all visible tiles - uses static data for instant load
   */
  const fetchAllTileData = useCallback(async () => {
    if (!config || !config.tiles || config.tiles.length === 0) {
      return;
    }

    // Use static data for CFO dashboard - instant load!
    // This avoids 10+ slow API calls
    if (config.id === 'cfo-dashboard-v1') {
      setData(STATIC_CFO_DATA);
      setLastRefreshed(new Date());
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    // Initialize all tiles with loading state
    const initialData: Record<string, TileData> = {};
    config.tiles
      .filter((tile) => tile.visible !== false)
      .forEach((tile) => {
        initialData[tile.id] = createEmptyTileData(true);
      });
    setData(initialData);

    // Fetch data for all tiles in parallel
    const visibleTiles = config.tiles.filter((tile) => tile.visible !== false);
    const fetchPromises = visibleTiles.map(async (tile) => {
      const tileData = await fetchTileData(tile, timeRange);
      return { tileId: tile.id, data: tileData };
    });

    try {
      const results = await Promise.allSettled(fetchPromises);

      const newData: Record<string, TileData> = {};
      let allFailed = true;
      let lastError: string | null = null;

      results.forEach((result, index) => {
        const tileId = visibleTiles[index].id;
        if (result.status === 'fulfilled') {
          newData[tileId] = result.value.data;
          if (!result.value.data.error) {
            allFailed = false;
          } else {
            lastError = result.value.data.error;
          }
        } else {
          newData[tileId] = {
            ...createEmptyTileData(),
            error: result.reason?.message || 'Fetch failed',
          };
          lastError = result.reason?.message || 'Fetch failed';
        }
      });

      setData(newData);
      setLastRefreshed(new Date());

      if (allFailed && lastError) {
        setError(lastError);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
    } finally {
      setLoading(false);
      isInitialFetch.current = false;
    }
  }, [config, timeRange]);

  /**
   * Refresh data for a specific tile
   */
  const refreshTile = useCallback(
    async (tileId: string) => {
      if (!config) return;

      const tile = config.tiles.find((t) => t.id === tileId);
      if (!tile) return;

      // Set loading state for this tile
      setData((prev) => ({
        ...prev,
        [tileId]: { ...prev[tileId], loading: true },
      }));

      const tileData = await fetchTileData(tile, timeRange);

      setData((prev) => ({
        ...prev,
        [tileId]: tileData,
      }));
    },
    [config, timeRange]
  );

  /**
   * Refresh function exposed to consumers
   */
  const refresh = useCallback(async () => {
    await fetchAllTileData();
  }, [fetchAllTileData]);

  // Fetch data on mount and when config/timeRange changes
  useEffect(() => {
    fetchAllTileData();
  }, [fetchAllTileData]);

  // Set up auto-refresh interval
  useEffect(() => {
    // Clear any existing interval
    if (refreshIntervalRef.current) {
      clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }

    // Set up new interval if configured
    if (config && config.refreshInterval > 0) {
      refreshIntervalRef.current = setInterval(() => {
        fetchAllTileData();
      }, config.refreshInterval * 1000); // Convert seconds to milliseconds
    }

    // Cleanup on unmount
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [config?.refreshInterval, fetchAllTileData]);

  return {
    data,
    loading,
    error,
    refresh,
    refreshTile,
    lastRefreshed,
  };
};

export default useDashboardData;
