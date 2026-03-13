/**
 * Centralized theme configuration for NLQ Dashboard
 *
 * This file contains all color, spacing, and visual constants
 * to ensure consistency across the application and make
 * theme changes easier.
 */

// =============================================================================
// COLOR PALETTE
// =============================================================================

/**
 * Primary brand colors
 */
export const COLORS = {
  // Brand
  primary: '#0BCAD9',     // Cyan - main brand color
  primaryHover: '#09b5c3',
  primaryDark: '#078b96',

  // Semantic colors
  success: '#10B981',     // Green
  warning: '#F59E0B',     // Amber
  error: '#EF4444',       // Red
  info: '#3B82F6',        // Blue

  // Chart palette (for data visualization)
  chart: {
    cyan: '#0BCAD9',
    blue: '#3B82F6',
    pink: '#EC4899',
    green: '#10B981',
    purple: '#8B5CF6',
    orange: '#F97316',
    yellow: '#EAB308',
    teal: '#14B8A6',
  },

  // Slate palette (for UI elements)
  slate: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
    950: '#020617',
  },

  // Status colors
  status: {
    healthy: '#10B981',
    caution: '#F59E0B',
    critical: '#EF4444',
  },

  // Trend colors
  trend: {
    up: '#10B981',
    down: '#EF4444',
    flat: '#94a3b8',
  },
} as const;

/**
 * Chart color palette as array (for recharts, etc.)
 */
export const CHART_COLORS = [
  COLORS.chart.cyan,
  COLORS.chart.blue,
  COLORS.chart.pink,
  COLORS.chart.green,
  COLORS.chart.purple,
  COLORS.chart.orange,
  COLORS.chart.yellow,
  COLORS.chart.teal,
] as const;

/**
 * Expense category colors (specific to finance dashboards)
 */
export const EXPENSE_COLORS = {
  personnel: COLORS.chart.blue,
  infrastructure: COLORS.chart.purple,
  salesMarketing: COLORS.chart.pink,
  rd: COLORS.chart.teal,
  ga: COLORS.chart.orange,
} as const;

// =============================================================================
// TYPOGRAPHY
// =============================================================================

export const FONT_SIZES = {
  xs: '10px',
  sm: '12px',
  base: '14px',
  lg: '16px',
  xl: '18px',
  '2xl': '20px',
  '3xl': '24px',
} as const;

// =============================================================================
// SPACING & LAYOUT
// =============================================================================

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  '2xl': 48,
} as const;

export const BORDER_RADIUS = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '9999px',
} as const;

// =============================================================================
// CHART CONFIGURATION
// =============================================================================

/**
 * Default chart styling for recharts
 */
export const CHART_DEFAULTS = {
  grid: {
    stroke: COLORS.slate[700],
    strokeDasharray: '3 3',
  },
  axis: {
    tick: {
      fill: COLORS.slate[400],
      fontSize: 11,
    },
    line: {
      stroke: COLORS.slate[600],
    },
  },
  tooltip: {
    backgroundColor: COLORS.slate[800],
    borderColor: COLORS.slate[700],
    textColor: COLORS.slate[100],
  },
  cursor: {
    stroke: COLORS.primary,
    strokeWidth: 2,
  },
} as const;

// =============================================================================
// ANIMATION
// =============================================================================

export const TRANSITIONS = {
  fast: '150ms',
  normal: '200ms',
  slow: '300ms',
} as const;

// =============================================================================
// Z-INDEX
// =============================================================================

export const Z_INDEX = {
  dropdown: 100,
  modal: 200,
  tooltip: 300,
  toast: 400,
} as const;

// =============================================================================
// API CONFIGURATION
// =============================================================================

export const API_CONFIG = {
  baseUrl: '/api/v1',
  timeout: 30000,
  retryAttempts: 3,
  retryDelay: 500,
} as const;

// =============================================================================
// SESSION CONFIGURATION
// =============================================================================

export const SESSION_CONFIG = {
  ttlSeconds: 2 * 60 * 60,  // 2 hours
  maxSessions: 1000,
} as const;
