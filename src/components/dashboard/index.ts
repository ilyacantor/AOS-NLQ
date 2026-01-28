/**
 * Dashboard Components
 *
 * This module exports the main dashboard components for building
 * persona-based executive dashboards with NLQ integration.
 */

// Main dashboard components
export { Dashboard } from './Dashboard';
export type { DashboardProps } from './Dashboard';

export { DashboardGrid } from './DashboardGrid';
export type { DashboardGridProps } from './DashboardGrid';

// Tile components
export { KPITile } from './tiles/KPITile';
export { InsightsTile } from './tiles/InsightsTile';
export type { InsightItem, InsightsTileProps } from './tiles/InsightsTile';
export { ChartTile } from './tiles/ChartTile';
export type { ChartTileProps } from './tiles/ChartTile';
export { NLQBar } from './tiles/NLQBar';

// Shared components
export { TimeRangeSelector } from './shared/TimeRangeSelector';
export { TrendIndicator } from './shared/TrendIndicator';
export { StatusBadge } from './shared/StatusBadge';
export { ConfidenceIndicator } from './shared/ConfidenceIndicator';
export { Sparkline } from './shared/Sparkline';
