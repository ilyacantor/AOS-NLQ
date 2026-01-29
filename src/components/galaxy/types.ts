/**
 * TypeScript types for Galaxy View visualization.
 * These match the backend IntentMapResponse and IntentNode models.
 */

export type MatchType = 'exact' | 'potential' | 'hypothesis';
export type Domain = 'finance' | 'growth' | 'ops' | 'product' | 'people';

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
    label: 'Core',
    strokeColor: 'rgba(79, 172, 254, 0.25)'
  },
  middle: {
    radius: 220,
    matchType: 'potential',
    label: 'Inner',
    strokeColor: 'rgba(79, 172, 254, 0.25)'
  },
  outer: {
    radius: 340,
    matchType: 'hypothesis',
    label: 'Outer',
    strokeColor: 'rgba(79, 172, 254, 0.25)'
  }
};

// Domain colors for circle fill (per spec cluster colors)
export const DOMAIN_COLORS: Record<Domain, string> = {
  finance: '#4facfe',   // Blue - CFO
  growth: '#f093fb',    // Pink - CRO
  ops: '#43e97b',       // Green - COO
  product: '#fa709a',   // Pink/Red - CTO
  people: '#fee140'     // Yellow - People
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
 * Calculate circle radius based on confidence (per spec).
 * Formula: 14 + (confidence * 32) pixels
 */
export function getCircleRadius(confidence: number, isPrimary: boolean): number {
  const baseRadius = 14 + (confidence * 32);
  return isPrimary ? baseRadius * 1.15 : baseRadius;
}

/**
 * Get data quality ring radius (per spec).
 * Formula: 18 + (confidence * 38) pixels
 */
export function getQualityRingRadius(confidence: number): number {
  return 18 + (confidence * 38);
}

/**
 * Get inner highlight radius (per spec).
 * Formula: 7 + (confidence * 16) pixels
 */
export function getInnerHighlightRadius(confidence: number): number {
  return 7 + (confidence * 16);
}

/**
 * Get node type styling (per spec).
 */
export function getTypeStyle(matchType: MatchType, isPrimary: boolean): { strokeWidth: number; dashArray: string; opacity: number } {
  if (isPrimary) {
    return { strokeWidth: 3, dashArray: 'none', opacity: 1.0 };
  }
  switch (matchType) {
    case 'exact':
      return { strokeWidth: 2, dashArray: 'none', opacity: 0.9 };
    case 'potential':
      return { strokeWidth: 2, dashArray: '4,2', opacity: 0.85 };
    case 'hypothesis':
      return { strokeWidth: 1, dashArray: '2,2', opacity: 0.70 };
    default:
      return { strokeWidth: 1, dashArray: 'none', opacity: 0.7 };
  }
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
