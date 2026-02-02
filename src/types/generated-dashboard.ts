/**
 * TypeScript types for Self-Developing Dashboard Schema
 * These types match the backend Pydantic models in dashboard_schema.py
 */

// =============================================================================
// Enums
// =============================================================================

export type WidgetType =
  | 'line_chart'
  | 'bar_chart'
  | 'horizontal_bar'
  | 'stacked_bar'
  | 'donut_chart'
  | 'area_chart'
  | 'kpi_card'
  | 'data_table'
  | 'sparkline'
  | 'filter_control'
  | 'time_range_selector'
  | 'text_block'
  | 'bridge_chart';

export type AggregationType = 'sum' | 'average' | 'min' | 'max' | 'count' | 'last' | 'first';

export type TimeGranularity = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';

export type InteractionType = 'drill_down' | 'filter' | 'highlight' | 'tooltip' | 'navigate';

export type ComparisonType = 'prior_period' | 'prior_year' | 'budget' | 'target' | 'custom';

// =============================================================================
// Data Binding Types
// =============================================================================

export interface MetricBinding {
  metric: string;
  alias?: string;
  aggregation?: AggregationType;
  format?: string;
  color?: string;
}

export interface DimensionBinding {
  dimension: string;
  alias?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  limit?: number;
}

export interface TimeBinding {
  period: string;
  granularity: TimeGranularity;
  comparison?: ComparisonType;
  comparison_period?: string;
}

export interface DataBinding {
  metrics: MetricBinding[];
  dimensions: DimensionBinding[];
  time?: TimeBinding;
  filters: Record<string, any>;
}

// =============================================================================
// Widget Configuration Types
// =============================================================================

export interface ChartConfig {
  show_legend: boolean;
  show_grid: boolean;
  show_labels: boolean;
  stacked: boolean;
  show_trend_line: boolean;
  animate: boolean;
  color_palette?: string[];
}

export interface KPIConfig {
  show_trend: boolean;
  show_sparkline: boolean;
  trend_period: string;
  thresholds?: Record<string, number>;
  inverse_status: boolean;
}

export interface TableConfig {
  show_totals: boolean;
  sortable: boolean;
  paginated: boolean;
  page_size: number;
  row_click_action?: string;
}

export interface FilterConfig {
  filter_type: string;
  multi_select: boolean;
  show_all_option: boolean;
  linked_widgets: string[];
}

export interface BridgeConfig {
  start_label: string;
  end_label: string;
  start_period?: string;
  end_period?: string;
  show_totals: boolean;
  show_labels: boolean;
  positive_color: string;
  negative_color: string;
  total_color: string;
}

// =============================================================================
// Interaction Types
// =============================================================================

export interface DrillDownConfig {
  target_dimension: string;
  query_template: string;
}

export interface FilterPropagation {
  source_widget: string;
  target_widgets: string[];
  dimension: string;
}

export interface InteractionConfig {
  type: InteractionType;
  enabled: boolean;
  drill_down?: DrillDownConfig;
  filter_propagation?: FilterPropagation;
}

// =============================================================================
// Layout Types
// =============================================================================

export interface GridPosition {
  column: number;
  row: number;
  col_span: number;
  row_span: number;
}

export interface LayoutConfig {
  columns: number;
  row_height: number;
  gap: number;
  padding: number;
}

// =============================================================================
// Widget Type
// =============================================================================

export interface Widget {
  id: string;
  type: WidgetType;
  title: string;
  description?: string;
  data: DataBinding;
  position: GridPosition;
  chart_config?: ChartConfig;
  kpi_config?: KPIConfig;
  table_config?: TableConfig;
  filter_config?: FilterConfig;
  bridge_config?: BridgeConfig;
  interactions: InteractionConfig[];
  style: Record<string, any>;
}

// =============================================================================
// Dashboard Schema Type
// =============================================================================

export interface DashboardSchema {
  id: string;
  title: string;
  description?: string;
  source_query: string;
  layout: LayoutConfig;
  widgets: Widget[];
  time_range?: TimeBinding;
  refresh_interval: number;
  confidence: number;
  version: number;
  conversation_id?: string;
  refinement_history: string[];
}

// =============================================================================
// API Response Types
// =============================================================================

export interface DashboardGenerationResponse {
  success: boolean;
  dashboard?: DashboardSchema;
  widget_data?: Record<string, WidgetData>;
  error?: string;
  query: string;
  intent_detected: string;
  confidence: number;
  suggestions: string[];
}

export interface DashboardRefinementRequest {
  dashboard_id: string;
  refinement_query: string;
  conversation_id?: string;
}

export interface DashboardRefinementResponse {
  success: boolean;
  dashboard?: DashboardSchema;
  widget_data?: Record<string, WidgetData>;
  error?: string;
  changes_made: string[];
  confidence: number;
}

// =============================================================================
// Widget Data Types (for rendering)
// =============================================================================

export interface ChartDataPoint {
  label: string;
  value: number;
  formatted_value?: string;
}

export interface ChartDataSeries {
  name: string;
  data: ChartDataPoint[];
  color?: string;
}

export interface BridgeDataPoint {
  label: string;
  value: number;
  formatted_value?: string;
  type: 'start' | 'end' | 'positive' | 'negative';
  running_total?: number;
}

export interface WidgetData {
  loading: boolean;
  error?: string;
  value?: number | string;
  formatted_value?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    percent_change: number;
    comparison_label: string;
  };
  sparkline_data?: number[];
  series?: ChartDataSeries[];
  categories?: string[];
  rows?: Record<string, any>[];
  // Bridge chart specific data
  bridge_data?: BridgeDataPoint[];
  start_value?: number;
  end_value?: number;
}
