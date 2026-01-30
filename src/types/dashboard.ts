/**
 * CFO Dashboard TypeScript Interfaces and Types
 * Comprehensive type definitions for the executive dashboard system
 */

// =============================================================================
// Enums and Union Types
// =============================================================================

/**
 * Time range options for dashboard data filtering
 */
export type TimeRange = 'MTD' | 'QTD' | 'YTD' | 'L12M' | 'Custom';

/**
 * Dashboard personas - determines which KPIs and views are shown
 */
export type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO';

/**
 * Health status for KPI indicators
 */
export type StatusType = 'healthy' | 'caution' | 'critical';

/**
 * Direction of trend movement
 */
export type TrendDirection = 'up' | 'down' | 'flat';

/**
 * Available chart types for visualization tiles
 */
export type ChartType = 'waterfall' | 'bar' | 'donut' | 'line' | 'stacked-bar' | 'horizontal-bar' | 'predictive-line';

/**
 * Data format types for KPI display
 */
export type DataFormat = 'currency' | 'percent' | 'number' | 'months';

/**
 * Insight classification types
 */
export type InsightType = 'warning' | 'positive' | 'declining' | 'improving';

/**
 * Tile size variants for responsive layouts
 */
export type TileSize = 'small' | 'medium' | 'large' | 'full-width';

// =============================================================================
// Core Tile Interfaces
// =============================================================================

/**
 * Threshold configuration for KPI status determination
 */
export interface Thresholds {
  /** Value threshold for healthy/green status */
  green: string;
  /** Value threshold for caution/yellow status */
  yellow: string;
  /** Value threshold for critical/red status */
  red: string;
}

/**
 * KPI Tile configuration - defines a key performance indicator tile
 */
export interface KPITile {
  /** Unique identifier for the tile */
  id: string;
  /** Display label for the KPI */
  label: string;
  /** NLQ query to fetch the primary value */
  primaryQuery: string;
  /** NLQ query template for drill-down on click */
  clickQuery: string;
  /** Display format for the value */
  format: DataFormat;
  /** Whether to show sparkline chart */
  showSparkline: boolean;
  /** Whether to show trend indicator */
  showTrend: boolean;
  /** Optional threshold configuration for status colors */
  thresholds?: Thresholds;
}

/**
 * Chart specification - defines a visualization chart tile
 */
export interface ChartSpec {
  /** Unique identifier for the chart */
  id: string;
  /** Type of chart visualization */
  type: ChartType;
  /** Display title for the chart */
  title: string;
  /** NLQ query to fetch chart data */
  query: string;
  /** Template for generating drill-down queries on click */
  clickTemplate: string;
  /** Dimension fields for the chart (categorical axes) */
  dimensions: string[];
  /** Measure fields for the chart (numeric values) */
  measures: string[];
}

/**
 * Insight item - an AI-generated insight or alert
 */
export interface InsightItem {
  /** Unique identifier for the insight */
  id: string;
  /** Classification type of the insight */
  type: InsightType;
  /** Human-readable insight text */
  text: string;
  /** NLQ query for additional context on click */
  query: string;
}

// =============================================================================
// Tile Position and Configuration
// =============================================================================

/**
 * Grid position for tile placement
 */
export interface TilePosition {
  /** Column start position (1-based) */
  column: number;
  /** Row start position (1-based) */
  row: number;
  /** Number of columns to span */
  colSpan: number;
  /** Number of rows to span */
  rowSpan: number;
}

/**
 * Insights panel configuration
 */
export interface InsightsConfig {
  /** Query to fetch insights */
  query: string;
  /** Maximum number of items to display */
  maxItems: number;
  /** Panel title */
  title?: string;
}

/**
 * Tile configuration - combines tile content with layout position
 */
export interface TileConfig {
  /** Unique identifier for the tile */
  id: string;
  /** Type of tile content */
  type: 'kpi' | 'chart' | 'insights' | 'custom';
  /** KPI configuration (if type is 'kpi') */
  kpi?: KPITile;
  /** Chart configuration (if type is 'chart') */
  chart?: ChartSpec;
  /** Insights configuration (if type is 'insights') */
  insights?: InsightsConfig;
  /** Grid position and size */
  position: TilePosition;
  /** Optional size variant */
  size?: TileSize;
  /** Whether tile is visible */
  visible: boolean;
  /** Custom CSS class names */
  className?: string;
  /** Refresh interval in milliseconds (0 = no auto-refresh) */
  refreshInterval?: number;
}

// =============================================================================
// Data Types
// =============================================================================

/**
 * Sparkline data point for mini trend charts
 */
export interface SparklineDataPoint {
  /** Period label (e.g., 'Jan', 'Q1') */
  period: string;
  /** Numeric value for the period */
  value: number;
}

/**
 * Trend data for KPI indicators
 */
export interface TrendData {
  /** Direction of the trend */
  direction: TrendDirection;
  /** Percentage change value */
  percentChange: number;
  /** Period comparison label (e.g., 'vs last month') */
  comparisonPeriod: string;
  /** Whether positive direction is favorable */
  positiveIsGood: boolean;
}

/**
 * Data returned for each tile
 */
export interface TileData {
  /** Primary display value */
  value: number | string | null;
  /** Formatted display string */
  formattedValue: string;
  /** Trend information */
  trend?: TrendData;
  /** Sparkline data points */
  sparklineData?: SparklineDataPoint[];
  /** Current status based on thresholds */
  status: StatusType;
  /** AI confidence score (0-1) */
  confidence: number;
  /** Whether data is currently loading */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Timestamp of last successful fetch */
  lastUpdated: Date | null;
  /** Raw data from query response */
  rawData?: unknown;
  /** Insight items (for insights tile) */
  insights?: InsightItem[];
}

/**
 * Chart data series for visualization
 */
export interface ChartDataSeries {
  /** Series name/label */
  name: string;
  /** Data points in the series */
  data: ChartDataPoint[];
  /** Optional color for the series */
  color?: string;
}

/**
 * Individual chart data point
 */
export interface ChartDataPoint {
  /** Category/dimension label */
  label: string;
  /** Numeric value */
  value: number;
  /** Optional formatted display value */
  formattedValue?: string;
  /** Optional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Chart data container
 */
export interface ChartData {
  /** Data series for the chart */
  series: ChartDataSeries[];
  /** Category labels for axes */
  categories: string[];
  /** Total/summary value if applicable */
  total?: number;
  /** Loading state */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** AI confidence score */
  confidence: number;
}

// =============================================================================
// Component Props
// =============================================================================

/**
 * Props for the KPI Tile component
 */
export interface KPITileProps {
  /** KPI configuration */
  config: KPITile;
  /** Current data for the tile */
  data: TileData;
  /** Selected time range */
  timeRange: TimeRange;
  /** Click handler for drill-down */
  onClick?: (query: string) => void;
  /** Additional CSS class names */
  className?: string;
  /** Whether tile is in compact mode */
  compact?: boolean;
  /** Whether to animate value changes */
  animate?: boolean;
}

/**
 * Props for Chart Tile components
 */
export interface ChartTileProps {
  /** Chart configuration */
  config: ChartSpec;
  /** Current chart data */
  data: ChartData;
  /** Selected time range */
  timeRange: TimeRange;
  /** Click handler for drill-down (receives dimension value) */
  onClick?: (dimensionValue: string, query: string) => void;
  /** Additional CSS class names */
  className?: string;
  /** Chart height in pixels */
  height?: number;
  /** Whether to show legend */
  showLegend?: boolean;
  /** Whether to show data labels */
  showDataLabels?: boolean;
  /** Custom color palette */
  colorPalette?: string[];
}

/**
 * Props for the Insights Panel component
 */
export interface InsightsPanelProps {
  /** List of insight items to display */
  insights: InsightItem[];
  /** Whether insights are loading */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Click handler for insight drill-down */
  onInsightClick?: (insight: InsightItem) => void;
  /** Handler to dismiss an insight */
  onDismiss?: (insightId: string) => void;
  /** Maximum number of insights to show */
  maxVisible?: number;
  /** Whether panel is collapsible */
  collapsible?: boolean;
  /** Initial collapsed state */
  defaultCollapsed?: boolean;
  /** Additional CSS class names */
  className?: string;
}

// =============================================================================
// Dashboard Configuration
// =============================================================================

/**
 * Custom time range specification
 */
export interface CustomTimeRange {
  /** Start date for the range */
  startDate: Date;
  /** End date for the range */
  endDate: Date;
  /** Display label for the range */
  label: string;
}

/**
 * Dashboard filter configuration
 */
export interface DashboardFilters {
  /** Selected time range */
  timeRange: TimeRange;
  /** Custom time range details (if timeRange is 'Custom') */
  customRange?: CustomTimeRange;
  /** Selected business units */
  businessUnits?: string[];
  /** Selected regions */
  regions?: string[];
  /** Selected products */
  products?: string[];
  /** Currency for display */
  currency?: string;
  /** Additional custom filters */
  customFilters?: Record<string, string | string[]>;
}

/**
 * Dashboard layout configuration
 */
export interface DashboardLayout {
  /** Number of columns in the grid */
  columns: number;
  /** Row height in pixels */
  rowHeight: number;
  /** Gap between tiles in pixels */
  gap: number;
  /** Breakpoints for responsive design */
  breakpoints?: {
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
}

/**
 * Dashboard theme configuration
 */
export interface DashboardTheme {
  /** Primary brand color */
  primaryColor: string;
  /** Color for healthy/positive status */
  successColor: string;
  /** Color for caution/warning status */
  warningColor: string;
  /** Color for critical/error status */
  errorColor: string;
  /** Background color */
  backgroundColor: string;
  /** Card/tile background color */
  cardBackground: string;
  /** Primary text color */
  textColor: string;
  /** Secondary text color */
  textSecondary: string;
  /** Border color */
  borderColor: string;
  /** Chart color palette */
  chartColors: string[];
}

/**
 * Full dashboard configuration
 */
export interface DashboardConfig {
  /** Unique identifier for the dashboard */
  id: string;
  /** Dashboard display name */
  name: string;
  /** Dashboard description */
  description?: string;
  /** Target persona for this dashboard */
  persona: Persona;
  /** Version number for configuration */
  version: string;
  /** KPI tile configurations */
  kpis: KPITile[];
  /** Chart tile configurations */
  charts: ChartSpec[];
  /** Full tile configurations with positions */
  tiles: TileConfig[];
  /** Layout configuration */
  layout: DashboardLayout;
  /** Theme configuration */
  theme?: DashboardTheme;
  /** Default filters */
  defaultFilters: DashboardFilters;
  /** Auto-refresh interval in milliseconds (0 = disabled) */
  refreshInterval: number;
  /** Whether dashboard is editable by user */
  editable: boolean;
  /** Created timestamp */
  createdAt?: Date;
  /** Last modified timestamp */
  updatedAt?: Date;
  /** Creator user ID */
  createdBy?: string;
}

// =============================================================================
// State and Context Types
// =============================================================================

/**
 * Dashboard state for state management
 */
export interface DashboardState {
  /** Current dashboard configuration */
  config: DashboardConfig | null;
  /** Current filter selections */
  filters: DashboardFilters;
  /** Data for all tiles keyed by tile ID */
  tileData: Record<string, TileData>;
  /** Chart data keyed by chart ID */
  chartData: Record<string, ChartData>;
  /** Current insights list */
  insights: InsightItem[];
  /** Global loading state */
  loading: boolean;
  /** Global error state */
  error: string | null;
  /** Whether dashboard is in edit mode */
  editMode: boolean;
  /** Currently selected/focused tile ID */
  selectedTileId: string | null;
}

/**
 * Dashboard context actions
 */
export interface DashboardActions {
  /** Load a dashboard configuration */
  loadDashboard: (dashboardId: string) => Promise<void>;
  /** Update filter selections */
  setFilters: (filters: Partial<DashboardFilters>) => void;
  /** Refresh data for a specific tile */
  refreshTile: (tileId: string) => Promise<void>;
  /** Refresh all dashboard data */
  refreshAll: () => Promise<void>;
  /** Execute a drill-down query */
  executeDrillDown: (query: string) => Promise<void>;
  /** Toggle edit mode */
  toggleEditMode: () => void;
  /** Update tile position */
  updateTilePosition: (tileId: string, position: TilePosition) => void;
  /** Save dashboard configuration */
  saveDashboard: () => Promise<void>;
  /** Reset to default configuration */
  resetToDefault: () => void;
}

/**
 * Full dashboard context type
 */
export interface DashboardContextType extends DashboardState, DashboardActions {}

// =============================================================================
// API Response Types
// =============================================================================

/**
 * API response wrapper for dashboard data
 */
export interface DashboardApiResponse<T> {
  /** Response data */
  data: T;
  /** Whether request was successful */
  success: boolean;
  /** Error message if failed */
  error?: string;
  /** AI confidence score for the response */
  confidence?: number;
  /** Response timestamp */
  timestamp: string;
  /** Query execution time in ms */
  executionTime?: number;
}

/**
 * NLQ query request payload
 */
export interface NLQQueryRequest {
  /** Natural language query string */
  query: string;
  /** Context filters to apply */
  filters?: DashboardFilters;
  /** Target persona for query interpretation */
  persona?: Persona;
  /** Maximum results to return */
  limit?: number;
}

/**
 * NLQ query response
 */
export interface NLQQueryResponse {
  /** Interpreted SQL or structured query */
  interpretedQuery: string;
  /** Query result data */
  data: unknown;
  /** AI confidence in interpretation */
  confidence: number;
  /** Alternative query suggestions */
  suggestions?: string[];
  /** Explanation of query interpretation */
  explanation?: string;
}

// =============================================================================
// Utility Types
// =============================================================================

/**
 * Type guard for KPI tile config
 */
export function isKPITile(tile: TileConfig): tile is TileConfig & { kpi: KPITile } {
  return tile.type === 'kpi' && tile.kpi !== undefined;
}

/**
 * Type guard for Chart tile config
 */
export function isChartTile(tile: TileConfig): tile is TileConfig & { chart: ChartSpec } {
  return tile.type === 'chart' && tile.chart !== undefined;
}

/**
 * Type guard for Insights tile config
 */
export function isInsightsTile(tile: TileConfig): tile is TileConfig & { insights: InsightsConfig } {
  return tile.type === 'insights' && tile.insights !== undefined;
}

/**
 * Partial tile data for updates
 */
export type PartialTileData = Partial<TileData>;

/**
 * Tile data update callback
 */
export type TileDataUpdater = (prevData: TileData) => TileData;

/**
 * Dashboard config without IDs (for creation)
 */
export type NewDashboardConfig = Omit<DashboardConfig, 'id' | 'createdAt' | 'updatedAt'>;

/**
 * Props with children for wrapper components
 */
export interface WithChildren {
  children: React.ReactNode;
}

/**
 * Dashboard provider props
 */
export interface DashboardProviderProps extends WithChildren {
  /** Initial dashboard ID to load */
  initialDashboardId?: string;
  /** Initial persona selection */
  initialPersona?: Persona;
}
