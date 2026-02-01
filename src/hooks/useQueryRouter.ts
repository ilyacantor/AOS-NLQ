/**
 * Unified Query Router Hook
 *
 * Single source of truth for routing queries between Galaxy and Dashboard spaces.
 * Eliminates duplicate routing logic and ensures consistent behavior.
 *
 * Architecture:
 * - DASHBOARD SPACE: Build/modify/visualize queries
 * - GALAXY SPACE: Factual/exploratory queries
 *
 * Shared services (history, learning, data gaps) are unaffected - they work
 * the same regardless of which space handles the query.
 */

import { useCallback } from 'react';

export type QueryDestination = 'galaxy' | 'dashboard';

export type QueryType =
  | 'factual'           // "what is revenue" -> Galaxy
  | 'dashboard_create'  // "build me a CFO dashboard" -> Dashboard
  | 'dashboard_refine'  // "add revenue widget" -> Dashboard (if dashboard exists)
  | 'visualization'     // "show me revenue trend" -> Dashboard
  | 'ambiguous';        // Could go either way - stay in current space

export interface QueryRouteResult {
  destination: QueryDestination;
  queryType: QueryType;
  confidence: number;      // 0-1, how confident we are in the routing
  matchedPattern?: string; // For debugging - which pattern triggered
}

// Dashboard trigger patterns - queries that should go to dashboard space
const DASHBOARD_PATTERNS = {
  // Explicit dashboard requests
  dashboardExplicit: /\b(dashboard|kpi\s*dashboard|executive\s*dashboard|overview)\b/i,

  // Build/create commands
  buildCreate: /\b(build|create|generate|make)\s+(me\s+)?(a\s+)?\w*\s*(dashboard|report|view)/i,

  // Year + dashboard/KPI context (e.g., "2025 KPIs", "2025 dashboard")
  yearDashboard: /\b(20\d{2})\s+(kpi|dashboard|overview|metrics|performance)/i,

  // Visualization requests
  visualization: /\b(show\s+me|visualize|chart|graph|trend|plot)\s+.*(over\s+time|by\s+quarter|quarterly|monthly|trend)/i,

  // Widget manipulation (refinement)
  widgetManipulation: /\b(add|remove|delete|hide|show|insert)\s+.*(widget|card|chart|kpi|metric)/i,

  // Layout/arrangement
  layoutArrangement: /\b(resize|move|arrange|reorganize|rearrange)\s+.*widget/i,

  // Add specific metrics (refinement context)
  addMetric: /\badd\s+(a\s+)?(revenue|margin|pipeline|churn|headcount|arr|nrr|cac|ltv|ebitda)/i,

  // Filter/drill operations
  filterDrill: /\b(filter|drill|drill\s*down|breakdown|segment|slice)\s+(by|into|on)/i,

  // Persona dashboard requests
  personaDashboard: /\b(cfo|cro|coo|cto|chro|people|hr|finance|sales|engineering)\s+(dashboard|view|metrics|kpis)/i,
};

// Galaxy trigger patterns - queries that should go to galaxy space
const GALAXY_PATTERNS = {
  // Direct questions
  directQuestion: /^(what|how\s+much|how\s+many|tell\s+me|what's|whats)\s+(is|are|was|were)?\s*/i,

  // Single metric queries (no visualization context)
  singleMetric: /^(revenue|ebitda|margin|arr|nrr|churn|pipeline|headcount|quota|cac|ltv)(\s+(for|in)\s+\d{4})?[?\s]*$/i,

  // Explain/why questions
  explainWhy: /\b(explain|why|what\s+caused|what\s+drove|reason\s+for)\b/i,

  // Comparison without viz (simple text comparison)
  simpleComparison: /\b(vs|versus|compared\s+to|difference\s+between)\b(?!.*(chart|graph|trend|visualize))/i,
};

/**
 * Determines if a query should route to dashboard or galaxy space.
 */
function classifyQuery(query: string, currentView: 'galaxy' | 'dashboard', hasDashboard: boolean): QueryRouteResult {
  const q = query.trim();

  // Check dashboard patterns first (they're more specific)
  for (const [patternName, pattern] of Object.entries(DASHBOARD_PATTERNS)) {
    if (pattern.test(q)) {
      // Determine if it's creation or refinement
      const isRefinement = ['widgetManipulation', 'layoutArrangement', 'addMetric', 'filterDrill'].includes(patternName);

      return {
        destination: 'dashboard',
        queryType: isRefinement && hasDashboard ? 'dashboard_refine' :
                   isRefinement ? 'dashboard_create' :
                   patternName === 'visualization' ? 'visualization' : 'dashboard_create',
        confidence: 0.9,
        matchedPattern: patternName,
      };
    }
  }

  // Check galaxy patterns
  for (const [patternName, pattern] of Object.entries(GALAXY_PATTERNS)) {
    if (pattern.test(q)) {
      return {
        destination: 'galaxy',
        queryType: 'factual',
        confidence: 0.85,
        matchedPattern: patternName,
      };
    }
  }

  // Ambiguous - stay in current space
  return {
    destination: currentView,
    queryType: 'ambiguous',
    confidence: 0.5,
    matchedPattern: 'none (stayed in current space)',
  };
}

/**
 * Hook for unified query routing between Galaxy and Dashboard spaces.
 */
export function useQueryRouter() {
  /**
   * Route a query to the appropriate space.
   *
   * @param query - The user's query text
   * @param currentView - Which space the user is currently in
   * @param hasDashboard - Whether a dashboard currently exists
   * @returns Routing decision with destination and query type
   */
  const routeQuery = useCallback((
    query: string,
    currentView: 'galaxy' | 'dashboard',
    hasDashboard: boolean = false
  ): QueryRouteResult => {
    return classifyQuery(query, currentView, hasDashboard);
  }, []);

  /**
   * Check if a query should trigger navigation to a different space.
   *
   * @param query - The user's query text
   * @param currentView - Which space the user is currently in
   * @param hasDashboard - Whether a dashboard currently exists
   * @returns true if navigation to different space is needed
   */
  const shouldNavigate = useCallback((
    query: string,
    currentView: 'galaxy' | 'dashboard',
    hasDashboard: boolean = false
  ): boolean => {
    const result = classifyQuery(query, currentView, hasDashboard);
    return result.destination !== currentView && result.confidence > 0.7;
  }, []);

  /**
   * Get the target space for a query (useful for pre-flight checks).
   */
  const getTargetSpace = useCallback((
    query: string,
    currentView: 'galaxy' | 'dashboard',
    hasDashboard: boolean = false
  ): QueryDestination => {
    return classifyQuery(query, currentView, hasDashboard).destination;
  }, []);

  return {
    routeQuery,
    shouldNavigate,
    getTargetSpace,
  };
}

// Export patterns for testing
export const _testExports = {
  DASHBOARD_PATTERNS,
  GALAXY_PATTERNS,
  classifyQuery,
};
