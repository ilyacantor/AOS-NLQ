/**
 * TypeScript types for Galaxy View visualization.
 * These match the backend IntentMapResponse and IntentNode models.
 */

export type MatchType = 'exact' | 'potential' | 'hypothesis';
export type Domain = 'finance' | 'growth' | 'ops' | 'product';

export type AmbiguityType =
  | 'none'
  | 'incomplete'
  | 'vague_metric'
  | 'casual'
  | 'yes_no'
  | 'broad'
  | 'implied'
  | 'judgment'
  | 'shorthand'
  | 'context'
  | 'comparison'
  | 'summary'
  | 'not_applicable';

export interface IntentNode {
  id: string;
  metric: string;
  display_name: string;
  match_type: MatchType;
  domain: Domain;
  confidence: number;        // 0-1 -> Circle size
  data_quality: number;      // 0-1 -> Arc completion
  freshness: string;         // "2h", "24h" -> Dot color
  value?: number | string | null;
  formatted_value?: string | null;
  period?: string | null;
  rationale?: string | null;
  semantic_label?: string | null;
}

export interface IntentMapResponse {
  query: string;
  query_type: string;
  ambiguity_type?: AmbiguityType | null;
  persona?: string | null;
  overall_confidence: number;
  overall_data_quality: number;
  node_count: number;
  nodes: IntentNode[];
  primary_node_id?: string | null;
  primary_answer?: string | null;
  text_response: string;
  needs_clarification: boolean;
  clarification_prompt?: string | null;
}

// Ring configuration
export interface RingConfig {
  radius: number;
  matchType: MatchType;
  label: string;
  strokeColor: string;
}

export const RING_CONFIG: Record<'inner' | 'middle' | 'outer', RingConfig> = {
  inner: {
    radius: 120,
    matchType: 'exact',
    label: 'Exact Match',
    strokeColor: 'rgba(59, 130, 246, 0.3)'
  },
  middle: {
    radius: 220,
    matchType: 'potential',
    label: 'Potential',
    strokeColor: 'rgba(156, 163, 175, 0.2)'
  },
  outer: {
    radius: 320,
    matchType: 'hypothesis',
    label: 'Hypothesis',
    strokeColor: 'rgba(156, 163, 175, 0.1)'
  }
};

// Domain colors for circle fill
export const DOMAIN_COLORS: Record<Domain, string> = {
  finance: '#3B82F6',   // Blue
  growth: '#EC4899',    // Pink
  ops: '#10B981',       // Green
  product: '#8B5CF6'    // Purple
};

// Freshness colors for indicator dot
export const FRESHNESS_COLORS = {
  fresh: '#22C55E',   // Green  (<=6h)
  stale: '#EAB308',   // Yellow (6-24h)
  old: '#EF4444'      // Red    (>24h)
};

/**
 * Get freshness color based on hours string.
 */
export function getFreshnessColor(freshness: string): string {
  if (freshness === 'N/A') return '#6B7280';  // Gray
  const hours = parseInt(freshness.replace('h', '')) || 999;
  if (hours <= 6) return FRESHNESS_COLORS.fresh;
  if (hours <= 24) return FRESHNESS_COLORS.stale;
  return FRESHNESS_COLORS.old;
}

/**
 * Calculate circle radius based on confidence.
 * Higher confidence = larger circle.
 */
export function getCircleRadius(confidence: number, isPrimary: boolean): number {
  const baseRadius = isPrimary ? 45 : 32;
  const minScale = 0.5;
  // confidence 1.0 -> 100% of base, confidence 0.0 -> 50% of base
  const scale = minScale + (confidence * (1 - minScale));
  return baseRadius * scale;
}

/**
 * Generate SVG arc path for data quality indicator.
 * Arc wraps around the node circle.
 */
export function getArcPath(
  cx: number,
  cy: number,
  radius: number,
  dataQuality: number
): string {
  if (dataQuality <= 0) return '';

  const startAngle = -Math.PI / 2;
  const endAngle = startAngle + (dataQuality * 2 * Math.PI);

  const startX = cx + radius * Math.cos(startAngle);
  const startY = cy + radius * Math.sin(startAngle);
  const endX = cx + radius * Math.cos(endAngle);
  const endY = cy + radius * Math.sin(endAngle);

  const largeArcFlag = dataQuality > 0.5 ? 1 : 0;

  if (dataQuality >= 1) {
    // Full circle - need two arcs
    return `M ${cx} ${cy - radius} A ${radius} ${radius} 0 1 1 ${cx - 0.01} ${cy - radius}`;
  }

  return `M ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY}`;
}
