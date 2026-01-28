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
   * Fetch data for all visible tiles in parallel
   */
  const fetchAllTileData = useCallback(async () => {
    if (!config || !config.tiles || config.tiles.length === 0) {
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
