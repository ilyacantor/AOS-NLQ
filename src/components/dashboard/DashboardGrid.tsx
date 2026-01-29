import React from 'react';
import {
  DashboardConfig,
  TileConfig,
  TileData,
  isKPITile,
  isChartTile,
  isInsightsTile,
} from '../../types/dashboard';
import { KPITile } from './tiles/KPITile';
import { InsightsTile } from './tiles/InsightsTile';
import { ChartTile } from './tiles/ChartTile';

/**
 * Props for the DashboardGrid component
 */
export interface DashboardGridProps {
  /** Dashboard configuration containing layout and tile definitions */
  config: DashboardConfig;
  /** Data for all tiles keyed by tile ID */
  data: Record<string, TileData>;
  /** Whether tiles are currently loading */
  loading: boolean;
  /** Click handler for tile interactions - triggers NLQ drill-down query */
  onTileClick: (clickQuery: string, context?: Record<string, string>) => void;
}

/**
 * Get CSS grid styles for a tile based on its position configuration
 */
function getTileGridStyles(tile: TileConfig): React.CSSProperties {
  const { position } = tile;
  return {
    gridColumn: `${position.column} / span ${position.colSpan}`,
    gridRow: `${position.row} / span ${position.rowSpan}`,
  };
}

/**
 * Loading skeleton for tiles
 */
const TileSkeleton: React.FC<{ height?: number }> = ({ height = 160 }) => (
  <div
    className="bg-slate-800 rounded-xl animate-pulse"
    style={{ minHeight: height }}
  >
    <div className="p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="h-4 w-24 bg-slate-700 rounded" />
        <div className="h-4 w-4 bg-slate-700 rounded-full" />
      </div>
      <div className="h-8 w-32 bg-slate-700 rounded mb-3" />
      <div className="flex items-center gap-3">
        <div className="h-4 w-20 bg-slate-700 rounded" />
        <div className="h-5 w-16 bg-slate-700 rounded-full" />
      </div>
    </div>
  </div>
);

/**
 * Error display for tiles that failed to load
 */
const TileError: React.FC<{ error: string; onRetry?: () => void }> = ({
  error,
  onRetry,
}) => (
  <div className="bg-slate-800 rounded-xl p-5 h-full flex flex-col items-center justify-center text-center">
    <div className="text-red-400 mb-2">
      <svg
        className="w-8 h-8 mx-auto"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
    </div>
    <p className="text-slate-400 text-sm mb-3">{error}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 rounded-md text-slate-300 transition-colors"
      >
        Retry
      </button>
    )}
  </div>
);

/**
 * Render a single tile based on its type
 */
const RenderTile: React.FC<{
  tile: TileConfig;
  data: TileData | undefined;
  loading: boolean;
  onTileClick: (clickQuery: string, context?: Record<string, string>) => void;
}> = ({ tile, data, loading, onTileClick }) => {
  // Show skeleton while loading and no data available
  if (loading && !data) {
    return <TileSkeleton />;
  }

  // Show error if data fetch failed
  if (data?.error && !data.loading) {
    return <TileError error={data.error} />;
  }

  // Render KPI tile
  if (isKPITile(tile)) {
    const tileData = data || {
      value: null,
      formattedValue: '-',
      status: 'healthy' as const,
      confidence: 0,
      loading: true,
      error: null,
      lastUpdated: null,
    };

    return (
      <KPITile
        label={tile.kpi.label}
        value={tileData.value ?? 0}
        format={tile.kpi.format}
        period="2025 YTD"
        trend={
          tileData.trend
            ? {
                direction: tileData.trend.direction,
                value: tileData.trend.percentChange,
                isPositive: tileData.trend.positiveIsGood,
                comparisonPeriod: tileData.trend.comparisonPeriod,
              }
            : undefined
        }
        sparklineData={tileData.sparklineData?.map((p) => p.value)}
        status={tileData.status}
        confidence={tileData.confidence}
        onClick={() => onTileClick(tile.kpi.clickQuery)}
        loading={tileData.loading}
      />
    );
  }

  // Render Chart tile
  if (isChartTile(tile)) {
    const chartData = data?.rawData as any;

    return (
      <ChartTile
        type={tile.chart.type}
        title={tile.chart.title}
        data={chartData}
        onClick={(segment) => {
          const query = tile.chart.clickTemplate.replace('{segment}', segment);
          onTileClick(query, { segment });
        }}
        loading={data?.loading ?? loading}
      />
    );
  }

  // Render Insights tile
  if (isInsightsTile(tile)) {
    const insights = data?.insights || [];

    return (
      <InsightsTile
        insights={insights}
        onInsightClick={(query) => onTileClick(query)}
        loading={data?.loading ?? loading}
        maxItems={tile.insights.maxItems}
      />
    );
  }

  // Fallback for unknown tile types
  return (
    <div className="bg-slate-800 rounded-xl p-5">
      <p className="text-slate-400 text-sm">Unknown tile type: {tile.type}</p>
    </div>
  );
};

/**
 * DashboardGrid - Renders a CSS grid of dashboard tiles
 *
 * This component takes a dashboard configuration and renders tiles
 * in a responsive grid layout. Each tile is positioned based on its
 * position configuration and rendered with the appropriate component
 * based on its type (KPI, Chart, or Insights).
 */
export const DashboardGrid: React.FC<DashboardGridProps> = ({
  config,
  data,
  loading,
  onTileClick,
}) => {
  const { layout, tiles } = config;

  // Filter to only visible tiles
  const visibleTiles = tiles.filter((tile) => tile.visible !== false);

  // Calculate grid template
  const gridStyles: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
    gridAutoRows: `minmax(${layout.rowHeight}px, auto)`,
    gap: `${layout.gap}px`,
  };

  return (
    <div className="dashboard-grid" style={gridStyles}>
      {visibleTiles.map((tile) => (
        <div
          key={tile.id}
          className={`dashboard-tile ${tile.className || ''}`}
          style={getTileGridStyles(tile)}
        >
          <RenderTile
            tile={tile}
            data={data[tile.id]}
            loading={loading}
            onTileClick={onTileClick}
          />
        </div>
      ))}
    </div>
  );
};

export default DashboardGrid;
